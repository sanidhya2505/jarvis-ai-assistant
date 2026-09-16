from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.database.models import KnowledgeFile, FileStatus, DocumentChunk
from app.files.parsers import extract_text, FileParsingError
from app.rag.chunking import chunk_text
from app.rag import vector_store
from app.core.logging_config import get_logger

logger = get_logger("jarvis.files")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def ingest_file(db: Session, path: Path) -> KnowledgeFile:
    """
    Full pipeline for one file: register/update metadata row, extract text,
    chunk it, embed it, and upsert into the vector store. Never raises —
    on failure the file is marked FAILED with an error message so the rest
    of ingestion (and the whole app) keeps running.
    """
    content_hash = _hash_file(path)
    record = db.query(KnowledgeFile).filter(KnowledgeFile.file_path == str(path)).first()

    if record and record.content_hash == content_hash:
        return record  # unchanged, nothing to do

    is_update = record is not None
    if not record:
        record = KnowledgeFile(
            filename=path.name,
            file_type=path.suffix.lower().lstrip("."),
            file_path=str(path),
            status=FileStatus.PROCESSING,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    else:
        record.status = FileStatus.PROCESSING
        db.commit()

    try:
        text, page_count = extract_text(path)
        chunks = chunk_text(text)

        if is_update:
            vector_store.delete_by_file_id(record.id)
            db.query(DocumentChunk).filter(DocumentChunk.file_id == record.id).delete()

        vector_ids = [f"{record.id}::{c.index}" for c in chunks]
        vector_store.add_chunks(
            ids=vector_ids,
            texts=[c.text for c in chunks],
            metadatas=[
                {
                    "file_id": record.id,
                    "filename": record.filename,
                    "chunk_index": c.index,
                    "page_number": c.page_number or -1,
                }
                for c in chunks
            ],
        )

        for c, vid in zip(chunks, vector_ids):
            db.add(DocumentChunk(
                file_id=record.id,
                chunk_index=c.index,
                page_number=c.page_number,
                section_title=c.section_title,
                text=c.text,
                vector_store_id=vid,
            ))

        record.status = FileStatus.UPDATED if is_update else FileStatus.INDEXED
        record.num_chunks = len(chunks)
        record.num_pages_or_records = page_count
        record.content_hash = content_hash
        record.last_updated = datetime.utcnow()
        record.error_message = None
        db.commit()
        logger.info("Indexed %s (%d chunks)", path.name, len(chunks))

    except FileParsingError as exc:
        record.status = FileStatus.FAILED
        record.error_message = str(exc)
        db.commit()
        logger.error("Failed to index %s: %s", path.name, exc)
    except Exception as exc:  # belt-and-braces: never let ingestion crash the app
        record.status = FileStatus.FAILED
        record.error_message = f"Unexpected error: {exc}"
        db.commit()
        logger.exception("Unexpected failure indexing %s", path.name)

    db.refresh(record)
    return record


def remove_file(db: Session, file_id: str) -> bool:
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if not record:
        return False
    vector_store.delete_by_file_id(file_id)
    db.query(DocumentChunk).filter(DocumentChunk.file_id == file_id).delete()
    db.delete(record)
    db.commit()
    return True
