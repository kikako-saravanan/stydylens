"""Per-document metadata the FAISS index can't hold: when a PDF was
uploaded and which questions have been asked about it.

Stored as one small JSON file next to the index. Which documents EXIST is
always read from the index itself (faiss_store.list_sources), so this file
can only ever add detail to a document, never make one appear or vanish.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval import faiss_store

MAX_QUESTIONS_PER_DOC = 50

_lock = threading.Lock()


def _path() -> Path:
    # Resolved per call so tests that redirect faiss_store.DATA_DIR to a
    # tmp dir get an isolated history file too.
    return faiss_store.DATA_DIR / "history.json"


def _read() -> dict:
    p = _path()
    return json.loads(p.read_text()) if p.exists() else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_upload(source: str) -> None:
    with _lock:
        data = _read()
        entry = data.setdefault(source, {"questions": []})
        entry["uploaded_at"] = _now()
        _path().write_text(json.dumps(data))


def record_question(source: str, question: str, query_type: str | None) -> None:
    with _lock:
        data = _read()
        entry = data.setdefault(source, {"questions": []})
        entry["questions"].append(
            {"question": question, "query_type": query_type, "asked_at": _now()}
        )
        entry["questions"] = entry["questions"][-MAX_QUESTIONS_PER_DOC:]
        _path().write_text(json.dumps(data))


def list_documents(uploads_dir: Path | None = None) -> list[dict]:
    """Uploaded documents, most recently uploaded first, each with its
    question history (newest first)."""
    with _lock:
        history = _read()

    docs = []
    for src in faiss_store.list_sources():
        entry = history.get(src["source"], {})
        uploaded_at = entry.get("uploaded_at")
        if not uploaded_at and uploads_dir is not None:
            f = uploads_dir / src["source"]
            if f.exists():
                uploaded_at = datetime.fromtimestamp(
                    f.stat().st_mtime, timezone.utc
                ).isoformat(timespec="seconds")
        questions = list(reversed(entry.get("questions", [])))
        docs.append({**src, "uploaded_at": uploaded_at, "questions": questions})

    docs.sort(key=lambda d: d["uploaded_at"] or "", reverse=True)
    return docs
