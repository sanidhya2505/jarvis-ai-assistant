"""
File -> plain text extraction for every supported knowledge-base format.

Each extractor returns (full_text, page_count_or_none). Failures raise
FileParsingError with a human-readable message so the caller can mark the
file FAILED instead of crashing the whole ingestion pipeline.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.core.logging_config import get_logger

logger = get_logger("jarvis.files")


class FileParsingError(Exception):
    pass


def extract_text(path: Path) -> tuple[str, int | None]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return _extract_docx(path)
        if suffix in (".txt", ".md"):
            return _extract_plain(path)
        if suffix == ".csv":
            return _extract_csv(path)
        if suffix == ".xlsx":
            return _extract_xlsx(path)
        if suffix == ".pptx":
            return _extract_pptx(path)
        if suffix == ".zip":
            return _extract_zip(path)
        if suffix in (".png", ".jpg", ".jpeg", ".webp"):
            return _extract_image(path)
    except FileParsingError:
        raise
    except Exception as exc:
        raise FileParsingError(f"Failed to parse {path.name}: {exc}") from exc

    raise FileParsingError(f"Unsupported file type: {suffix}")


def _extract_pdf(path: Path) -> tuple[str, int | None]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"\n[Page {i + 1}]\n{text}")
    return "".join(pages), len(reader.pages)


def _extract_docx(path: Path) -> tuple[str, int | None]:
    import docx
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts), None


def _extract_plain(path: Path) -> tuple[str, int | None]:
    return path.read_text(encoding="utf-8", errors="ignore"), None


def _extract_csv(path: Path) -> tuple[str, int | None]:
    import csv
    rows = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(", ".join(row))
    return "\n".join(rows), len(rows)


def _extract_xlsx(path: Path) -> tuple[str, int | None]:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    parts = []
    total_rows = 0
    for sheet in wb.worksheets:
        parts.append(f"\n[Sheet: {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            total_rows += 1
            cells = [str(c) for c in row if c is not None]
            if cells:
                parts.append(", ".join(cells))
    return "\n".join(parts), total_rows


def _extract_pptx(path: Path) -> tuple[str, int | None]:
    from pptx import Presentation
    prs = Presentation(str(path))
    parts = []
    slide_count = 0
    for i, slide in enumerate(prs.slides):
        slide_count += 1
        parts.append(f"\n[Slide {i + 1}]")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs)
                    if text.strip():
                        parts.append(text)
    return "\n".join(parts), slide_count


def _extract_zip(path: Path) -> tuple[str, int | None]:
    """
    Extracts and concatenates text from supported files inside the archive.
    Nested zips and binaries with no text extractor are listed by name only.
    """
    parts = []
    count = 0
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            count += 1
            inner_suffix = Path(name).suffix.lower()
            if inner_suffix in (".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv"):
                try:
                    with zf.open(name) as f:
                        text = f.read().decode("utf-8", errors="ignore")
                    parts.append(f"\n[File: {name}]\n{text}")
                except Exception as exc:
                    logger.warning("Could not read %s inside %s: %s", name, path.name, exc)
            else:
                parts.append(f"\n[File: {name}] (binary/unsupported — not indexed)")
    return "\n".join(parts), count


def _extract_image(path: Path) -> tuple[str, int | None]:
    """
    OCR text from an image where possible; falls back to a filename-only
    placeholder note (still lets the file appear in the knowledge base and
    be linked to tasks, per spec section 2: 'Images where possible').
    """
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(path))
        if text.strip():
            return text, 1
    except Exception as exc:
        logger.warning("OCR unavailable/failed for %s: %s", path.name, exc)
    return f"[Image file: {path.name} — no OCR text extracted]", 1
