import os
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it.

    Loading a sentence-transformers model reads model weights off disk
    (or downloads them once, then caches) — doing that on every request
    would add real, avoidable latency to every single upload/query.
    lru_cache(maxsize=1) makes this a process-wide singleton: the first
    call loads it, every later call reuses the same in-memory model.
    """
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of texts into L2-normalized vectors.

    Normalizing to unit length means cosine similarity between two
    embeddings reduces to a plain dot product — the similarity metric
    FAISS's IndexFlatIP computes natively and efficiently, without it
    needing to know anything about "cosine similarity" as a concept.
    """
    model = get_model()
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
