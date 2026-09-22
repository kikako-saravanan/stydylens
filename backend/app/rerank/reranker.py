import logging
import os
from functools import lru_cache

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder(RERANKER_MODEL_NAME)


def rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    """Re-score FAISS candidates against the ORIGINAL question with a
    cross-encoder, and return the best top_k.

    Bi-encoder (FAISS/embeddings) vs. cross-encoder, the core distinction:
    a bi-encoder embeds the query and each chunk SEPARATELY, with no
    interaction between them until the vectors are compared afterward —
    fast (chunk vectors are precomputed once), but approximate, since the
    model never actually looks at the query and a specific chunk together.
    A cross-encoder feeds (query, chunk) into the model as ONE input, so it
    can directly attend to how specific words in the question relate to
    specific words in that exact chunk — slower (can't precompute; must
    run once per candidate), but more precise. Hence the two-stage
    pattern: FAISS casts a cheap, wide net; the cross-encoder spends more
    compute only on the smaller candidate set FAISS already narrowed down.
    """
    if not chunks:
        return []

    pairs = [(query, c["text"]) for c in chunks]
    scores = get_reranker().predict(pairs)

    reranked = [
        {**c, "rerank_score": float(score)} for c, score in zip(chunks, scores)
    ]
    reranked.sort(key=lambda c: c["rerank_score"], reverse=True)

    logger.info(
        "[rerank] query=%r: pre-rerank order=%s",
        query, [(c["chunk_id"], round(c["score"], 4)) for c in chunks],
    )
    logger.info(
        "[rerank] query=%r: post-rerank order=%s",
        query,
        [(c["chunk_id"], round(c["rerank_score"], 4)) for c in reranked[:top_k]],
    )

    return reranked[:top_k]
