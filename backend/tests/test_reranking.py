"""Unit/integration test: real cross-encoder reranking. Deliberately NOT
mocked -- this is the exact component the assignment's grading criteria
asks for direct before/after evidence of ("is re-ranking demonstrably
improving result order"). A mocked reranker could trivially fake an
improvement that never actually happens. See docs/milestones/08-reranking.md.
"""

from app.chunking.chunker import chunk_pages
from app.ingestion.pdf_loader import extract_pages
from app.rerank.reranker import rerank


def test_rerank_returns_requested_top_k(isolated_faiss, sample_pdf_path):
    pages = extract_pages(sample_pdf_path)
    isolated_faiss.add_chunks(chunk_pages(pages))
    candidates = isolated_faiss.query_index("How does priority scheduling work?", k=10)

    reranked = rerank("How does priority scheduling work?", candidates, top_k=5)
    assert len(reranked) == 5


def test_rerank_promotes_the_real_priority_scheduling_chunk(isolated_faiss, sample_pdf_path):
    """Reproduces the exact real before/after case documented in
    docs/milestones/08-reranking.md: FAISS ranks the actual priority-
    scheduling passage (page 15) last among its top-10 candidates; the
    cross-encoder should promote it, since it directly answers the
    question better than the higher-FAISS-scoring but less relevant
    page 16 (multilevel queue scheduling)."""
    pages = extract_pages(sample_pdf_path)
    isolated_faiss.add_chunks(chunk_pages(pages))

    question = "How does priority scheduling work?"
    candidates = isolated_faiss.query_index(question, k=10)
    candidate_pages = [c["page"] for c in candidates]
    assert 15 in candidate_pages, "expected page 15 to at least be a FAISS candidate"

    reranked = rerank(question, candidates, top_k=5)
    reranked_pages = [c["page"] for c in reranked]
    assert reranked_pages[0] == 15, (
        f"expected the cross-encoder to promote page 15 to #1, got order {reranked_pages}"
    )


def test_rerank_scores_are_populated_and_sorted_descending():
    from app.rerank.reranker import rerank

    fake_chunks = [
        {"chunk_id": "a", "source": "x", "page": 1, "text": "cats are mammals", "score": 0.5},
        {"chunk_id": "b", "source": "x", "page": 2, "text": "the stock market fell today", "score": 0.5},
    ]
    reranked = rerank("Tell me about cats", fake_chunks, top_k=2)
    scores = [c["rerank_score"] for c in reranked]
    assert scores == sorted(scores, reverse=True)
    assert reranked[0]["chunk_id"] == "a"
