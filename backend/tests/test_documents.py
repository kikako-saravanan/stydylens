"""Tests for the uploaded-documents list, duplicate-upload protection,
per-document scoped retrieval and question history. Retrieval/reranking are
real; only the LLM boundary is mocked."""

from app.rag import chain as chain_module
from app.rag.router import RoutedQuery


def _mock_llm(monkeypatch):
    monkeypatch.setattr(
        chain_module,
        "route_query",
        lambda q: RoutedQuery(query_type="single_fact", sub_questions=[q]),
    )
    monkeypatch.setattr(chain_module, "generate", lambda messages: "mocked answer")


def test_documents_requires_auth(client):
    assert client.get("/api/documents").status_code == 401


def test_documents_lists_uploaded_pdf(indexed_client, auth_headers, sample_pdf_path):
    docs = indexed_client.get("/api/documents", headers=auth_headers).json()["documents"]
    assert [d["source"] for d in docs] == [sample_pdf_path.name]
    assert docs[0]["chunk_count"] > 0
    assert docs[0]["page_count"] > 0
    assert docs[0]["uploaded_at"]
    assert docs[0]["questions"] == []


def test_duplicate_upload_is_rejected_and_not_reindexed(
    indexed_client, auth_headers, sample_pdf_path, isolated_faiss
):
    before = isolated_faiss.count()
    with sample_pdf_path.open("rb") as f:
        res = indexed_client.post(
            "/api/upload",
            files={"file": (sample_pdf_path.name, f, "application/pdf")},
            headers=auth_headers,
        )
    assert res.status_code == 409
    assert isolated_faiss.count() == before


def test_ask_records_question_history_for_selected_document(
    indexed_client, auth_headers, sample_pdf_path, monkeypatch
):
    _mock_llm(monkeypatch)
    res = indexed_client.post(
        "/api/ask",
        json={"question": "What is round robin scheduling?", "source": sample_pdf_path.name},
        headers=auth_headers,
    )
    assert res.status_code == 200

    doc = indexed_client.get("/api/documents", headers=auth_headers).json()["documents"][0]
    assert [q["question"] for q in doc["questions"]] == ["What is round robin scheduling?"]
    assert doc["questions"][0]["query_type"] == "single_fact"


def test_retrieval_is_scoped_to_selected_document(isolated_faiss, sample_pdf_path):
    from app.chunking.chunker import Chunk, chunk_pages
    from app.ingestion.pdf_loader import extract_pages

    isolated_faiss.add_chunks(chunk_pages(extract_pages(sample_pdf_path)))
    isolated_faiss.add_chunks(
        [Chunk(chunk_id="other-1", source="other.pdf", page=1, text="Photosynthesis in plants.")]
    )

    scoped = isolated_faiss.query_index("What is round robin scheduling?", 5, "other.pdf")
    assert [r["source"] for r in scoped] == ["other.pdf"]

    unscoped = isolated_faiss.query_index("What is round robin scheduling?", 5)
    assert unscoped[0]["source"] == sample_pdf_path.name
