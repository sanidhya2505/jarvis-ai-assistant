from app.rag.chunking import chunk_text


def test_chunk_text_splits_long_text():
    paragraph = "Sentence about the project. " * 50
    text = "\n\n".join([paragraph] * 3)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.text.strip()


def test_chunk_text_empty_input():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_detects_page_numbers():
    text = "[Page 1]\nIntro paragraph.\n\n[Page 2]\nSecond page paragraph."
    chunks = chunk_text(text, chunk_size=20, overlap=0)
    pages = [c.page_number for c in chunks]
    assert 1 in pages or 2 in pages
