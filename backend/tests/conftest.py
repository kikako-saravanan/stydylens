import base64
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PDF = ROOT / "data" / "sample_pdfs" / "os-concepts-ch5-cpu-scheduling-excerpt.pdf"

AUTH_USERNAME = os.getenv("AUTH_USERNAME", "studylens")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "studylens-demo-2026")


@pytest.fixture
def sample_pdf_path() -> Path:
    assert SAMPLE_PDF.exists(), f"Sample PDF fixture missing: {SAMPLE_PDF}"
    return SAMPLE_PDF


@pytest.fixture
def auth_headers() -> dict:
    token = base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def isolated_faiss(tmp_path, monkeypatch):
    """Point the FAISS store at an empty tmp directory for this test only,
    and reset its cached in-memory state before and after — so tests never
    read or write the real data/index/ a developer might be using locally,
    and never leak index state between tests."""
    from app.retrieval import faiss_store

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    monkeypatch.setattr(faiss_store, "DATA_DIR", index_dir)
    monkeypatch.setattr(faiss_store, "INDEX_PATH", index_dir / "faiss.index")
    monkeypatch.setattr(faiss_store, "METADATA_PATH", index_dir / "metadata.json")
    faiss_store.reset()
    yield faiss_store
    faiss_store.reset()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def indexed_client(client, isolated_faiss, sample_pdf_path, auth_headers):
    """A TestClient whose isolated FAISS index already has the real sample
    PDF's chunks in it — for tests that need something to retrieve/rerank
    against without re-uploading in every single test."""
    with sample_pdf_path.open("rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": (sample_pdf_path.name, f, "application/pdf")},
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    return client
