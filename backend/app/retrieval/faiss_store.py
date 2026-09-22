import json
import threading
from pathlib import Path

import faiss
import numpy as np

from app.chunking.chunker import Chunk
from app.embeddings.embedder import embed_texts

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "index"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = DATA_DIR / "faiss.index"
METADATA_PATH = DATA_DIR / "metadata.json"

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2's fixed output size

_lock = threading.Lock()
_index: faiss.Index | None = None
_metadata: list[dict] | None = None


def _load() -> None:
    """Load the persisted index + metadata into memory, or start empty.

    FAISS itself only stores vectors and their integer position — it has
    no concept of "page number" or "source filename". We keep a parallel
    list where position i describes the vector at FAISS position i; the
    two are kept in lockstep by always appending to both together.
    """
    global _index, _metadata
    if INDEX_PATH.exists() and METADATA_PATH.exists():
        _index = faiss.read_index(str(INDEX_PATH))
        _metadata = json.loads(METADATA_PATH.read_text())
    else:
        _index = faiss.IndexFlatIP(EMBEDDING_DIM)
        _metadata = []


def _ensure_loaded() -> None:
    if _index is None:
        _load()


def _persist() -> None:
    faiss.write_index(_index, str(INDEX_PATH))
    METADATA_PATH.write_text(json.dumps(_metadata))


def add_chunks(chunks: list[Chunk]) -> int:
    """Embed and add chunks to the index, persisting to disk. Returns the new total count."""
    if not chunks:
        return count()

    embeddings = embed_texts([c.text for c in chunks])

    with _lock:
        _ensure_loaded()
        _index.add(np.asarray(embeddings, dtype=np.float32))
        _metadata.extend(
            {"chunk_id": c.chunk_id, "source": c.source, "page": c.page, "text": c.text}
            for c in chunks
        )
        _persist()
        return _index.ntotal


def count() -> int:
    with _lock:
        _ensure_loaded()
        return _index.ntotal


def query_index(question: str, k: int = 5) -> list[dict]:
    """Embed the question and return the top-k most similar chunks.

    Scores are cosine similarity (both sides are unit-length vectors, so
    FAISS's inner product IS the cosine similarity here — no separate
    normalization step needed at query time).
    """
    with _lock:
        _ensure_loaded()
        if _index.ntotal == 0:
            return []
        query_vector = embed_texts([question]).astype(np.float32)
        k = min(k, _index.ntotal)
        scores, indices = _index.search(query_vector, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            meta = _metadata[idx]
            results.append({**meta, "score": float(score)})
        return results
