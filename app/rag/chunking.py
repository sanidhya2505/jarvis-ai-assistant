"""Simple, dependency-free text chunker with overlap, page-aware where possible."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    index: int
    page_number: int | None = None
    section_title: str | None = None


_PAGE_MARK = re.compile(r"\[Page (\d+)\]")
_SLIDE_MARK = re.compile(r"\[Slide (\d+)\]")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[Chunk]:
    """
    Splits on paragraph boundaries first, then packs paragraphs into chunks
    of roughly `chunk_size` characters with `overlap` characters repeated
    between consecutive chunks (helps retrieval when an answer spans a
    chunk boundary).
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buffer = ""
    current_page = None

    def flush(idx: int) -> None:
        nonlocal buffer
        if buffer.strip():
            chunks.append(Chunk(text=buffer.strip(), index=idx, page_number=current_page))
        buffer = ""

    for para in paragraphs:
        page_match = _PAGE_MARK.search(para) or _SLIDE_MARK.search(para)
        if page_match:
            current_page = int(page_match.group(1))

        if len(buffer) + len(para) <= chunk_size:
            buffer += ("\n\n" if buffer else "") + para
        else:
            flush(len(chunks))
            # start new buffer with overlap tail of the previous chunk
            tail = buffer[-overlap:] if len(buffer) > overlap else buffer
            buffer = (tail + "\n\n" + para) if tail else para

    flush(len(chunks))
    return chunks
