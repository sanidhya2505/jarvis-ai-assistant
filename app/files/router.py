from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import KnowledgeFile
from app.config.settings import get_settings
from app.files.ingestion import ingest_file, remove_file
from app.rag.vector_store import semantic_search

router = APIRouter(prefix="/api/files", tags=["knowledge_base"])
settings = get_settings()


def _serialize(f: KnowledgeFile) -> dict:
    return {
        "id": f.id,
        "filename": f.filename,
        "file_type": f.file_type,
        "date_added": f.date_added.isoformat() if f.date_added else None,
        "last_updated": f.last_updated.isoformat() if f.last_updated else None,
        "status": f.status.value,
        "num_chunks": f.num_chunks,
        "num_pages_or_records": f.num_pages_or_records,
        "error_message": f.error_message,
    }


@router.get("")
def list_files(db: Session = Depends(get_db)):
    return [_serialize(f) for f in db.query(KnowledgeFile).order_by(KnowledgeFile.date_added.desc()).all()]


@router.post("/upload")
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.knowledge_dir / file.filename
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    record = ingest_file(db, dest)
    return _serialize(record)


@router.post("/{file_id}/reindex")
def reindex_file(file_id: str, db: Session = Depends(get_db)):
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if not record:
        raise HTTPException(404, "File not found")
    record.content_hash = None  # force re-processing
    db.commit()
    updated = ingest_file(db, Path(record.file_path))
    return _serialize(updated)


@router.delete("/{file_id}")
def delete_file(file_id: str, delete_from_disk: bool = False, db: Session = Depends(get_db)):
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if not record:
        raise HTTPException(404, "File not found")
    path = Path(record.file_path)
    ok = remove_file(db, file_id)
    if delete_from_disk and path.exists():
        path.unlink()
    return {"deleted": ok}


@router.get("/search")
def search_knowledge_base(query: str, top_k: int = 5):
    return semantic_search(query, top_k=top_k)
