"""
Central configuration for JARVIS.

All secrets/config come from environment variables (.env file), never
hardcoded. See .env.example for the full list of options.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # .../JARVIS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_name: str = "JARVIS"
    user_name: str = "User"
    environment: str = "development"  # development | production

    # --- Paths ---
    data_dir: Path = BASE_DIR / "data"
    knowledge_dir: Path = BASE_DIR / "data" / "knowledge"
    database_dir: Path = BASE_DIR / "data" / "database"
    vector_store_dir: Path = BASE_DIR / "data" / "vector_store"
    memory_dir: Path = BASE_DIR / "data" / "memory"
    logs_dir: Path = BASE_DIR / "logs"

    # --- Database ---
    database_url: str = "sqlite:///./data/database/jarvis.db"

    # --- AI / LLM provider ---
    # "openai" (or any OpenAI-compatible endpoint), "anthropic", or "local"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # --- Web search (optional, off by default per file-first rule) ---
    enable_web_search: bool = False

    # --- Voice ---
    enable_voice: bool = False
    wake_word: str = "hey jarvis"
    tts_provider: str = "pyttsx3"  # modular: pyttsx3 | azure | elevenlabs
    stt_provider: str = "whisper_local"  # modular: whisper_local | azure

    # --- Startup / tray ---
    start_with_windows: bool = True
    minimize_to_tray_on_close: bool = True

    # --- Notifications ---
    default_reminder_minutes_before: int = 15

    # --- API server (used by the desktop UI as its local backend) ---
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.knowledge_dir,
            self.database_dir,
            self.vector_store_dir,
            self.memory_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
