import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is importable as `app.*`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point Settings at a throwaway temp directory BEFORE anything imports settings,
# so tests never touch the real data/ directory.
_TMP = tempfile.mkdtemp(prefix="jarvis_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"

from app.database.db import Base, engine, SessionLocal  # noqa: E402


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
