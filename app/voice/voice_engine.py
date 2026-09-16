"""
Voice interaction (spec section 9).

Modular by design:
  - STT_PROVIDER: "whisper_local" (openai-whisper running on-device, fully
    offline) or "azure" (stub — see _stt_azure).
  - TTS_PROVIDER: "pyttsx3" (offline, uses SAPI5 on Windows) or "azure"/
    "elevenlabs" (stubs for higher-quality cloud voices).

Every entry point catches its own exceptions and returns None/False rather
than raising, so a broken microphone or missing model never takes down the
rest of JARVIS (spec section 22).
"""
from __future__ import annotations

import threading
import time

from app.config.settings import get_settings
from app.core.logging_config import get_logger

logger = get_logger("jarvis.voice")
settings = get_settings()


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

def speak(text: str) -> bool:
    if not text:
        return False
    try:
        if settings.tts_provider == "pyttsx3":
            return _tts_pyttsx3(text)
        logger.warning("TTS provider '%s' not implemented, falling back to pyttsx3", settings.tts_provider)
        return _tts_pyttsx3(text)
    except Exception as exc:
        logger.error("TTS failed: %s", exc)
        return False


def _tts_pyttsx3(text: str) -> bool:
    import pyttsx3
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    return True


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------

def transcribe_from_microphone(timeout_seconds: int = 8) -> str | None:
    """Push-to-talk: records one utterance from the default mic and returns the transcript."""
    try:
        import speech_recognition as sr
    except Exception as exc:
        logger.error("speech_recognition not available: %s", exc)
        return None

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout_seconds, phrase_time_limit=15)
    except Exception as exc:
        logger.error("Microphone capture failed: %s", exc)
        return None

    return _run_stt(recognizer, audio)


def _run_stt(recognizer, audio) -> str | None:
    if settings.stt_provider == "whisper_local":
        return _stt_whisper_local(recognizer, audio)
    logger.warning("STT provider '%s' not implemented, falling back to whisper_local", settings.stt_provider)
    return _stt_whisper_local(recognizer, audio)


def _stt_whisper_local(recognizer, audio) -> str | None:
    try:
        return recognizer.recognize_whisper(audio, model="base")
    except Exception as exc:
        logger.error("Local whisper transcription failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Wake word ("Hey JARVIS")
# ---------------------------------------------------------------------------

class WakeWordListener:
    """
    Runs a background thread that listens for the configured wake word,
    then calls `on_activation(transcribed_command)` for whatever the user
    says immediately after. Uses simple continuous STT rather than a
    dedicated wake-word model (e.g. Porcupine) to keep the stack fully
    offline/dependency-light; swapping in a dedicated wake-word engine
    later only requires replacing `_listen_loop`.
    """

    def __init__(self, on_activation):
        self.on_activation = on_activation
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("Wake-word listener started (phrase: '%s')", settings.wake_word)

    def stop(self) -> None:
        self._stop_event.set()

    def _listen_loop(self) -> None:
        try:
            import speech_recognition as sr
        except Exception as exc:
            logger.error("Wake-word listener disabled — speech_recognition unavailable: %s", exc)
            return

        recognizer = sr.Recognizer()
        while not self._stop_event.is_set():
            try:
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)
                text = (_run_stt(recognizer, audio) or "").lower()
                if settings.wake_word in text:
                    remainder = text.split(settings.wake_word, 1)[-1].strip()
                    if remainder:
                        self.on_activation(remainder)
                    else:
                        follow_up = transcribe_from_microphone()
                        if follow_up:
                            self.on_activation(follow_up)
            except Exception:
                # Timeouts and transient mic errors are expected in a loop; keep going.
                time.sleep(0.2)
                continue
