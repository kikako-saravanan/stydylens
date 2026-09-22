"""Tests for the pipeline-visualization streaming endpoint (added after
Milestone 15, for the frontend's "show pipeline stages" learning feature).

Same mocking policy as test_routing_and_chain.py: the LLM boundary is
mocked to test OUR event-sequencing logic deterministically and for free;
retrieval/reranking are real.
"""

import json

from app.rag import chain as chain_module


def test_stream_answer_question_yields_stages_in_order(
    isolated_faiss, sample_pdf_path, monkeypatch
):
    from app.chunking.chunker import chunk_pages
    from app.ingestion.pdf_loader import extract_pages

    pages = extract_pages(sample_pdf_path)
    isolated_faiss.add_chunks(chunk_pages(pages))
    monkeypatch.setattr(chain_module, "generate", lambda messages: "mocked answer")

    events = list(chain_module.stream_answer_question("What is round robin scheduling?"))
    stage_status_pairs = [(e["stage"], e.get("status")) for e in events]

    assert stage_status_pairs == [
        ("routing", "start"),
        ("routing", "done"),
        ("retrieval", "start"),
        ("retrieval", "done"),
        ("reranking", "start"),
        ("reranking", "done"),
        ("generation", "start"),
        ("generation", "done"),
        ("complete", None),
    ]


def test_stream_answer_question_final_event_matches_batch_answer(
    isolated_faiss, sample_pdf_path, monkeypatch
):
    """The streaming path and the batch (answer_question/LCEL chain) path
    call the identical underlying stage functions -- this checks they
    actually agree on the final result, not just that each runs without
    crashing."""
    from app.chunking.chunker import chunk_pages
    from app.ingestion.pdf_loader import extract_pages

    pages = extract_pages(sample_pdf_path)
    isolated_faiss.add_chunks(chunk_pages(pages))
    monkeypatch.setattr(chain_module, "generate", lambda messages: "mocked answer")

    question = "What is round robin scheduling?"
    batch_result = chain_module.answer_question(question)

    events = list(chain_module.stream_answer_question(question))
    complete_event = events[-1]

    assert complete_event["answer"] == batch_result["answer"]
    assert complete_event["post_rerank_order"] == batch_result["post_rerank_order"]
    assert [s["chunk_id"] for s in complete_event["sources"]] == [
        s["chunk_id"] for s in batch_result["sources"]
    ]


def test_ask_stream_endpoint_returns_real_sse_events(indexed_client, auth_headers, monkeypatch):
    # Mocks the LLM boundary, same policy as test_routing_and_chain.py --
    # this test verifies the HTTP/SSE plumbing (content-type, event
    # framing, stage ordering over the wire), not the model's real
    # reasoning, so it stays in the free/fast/deterministic test tier.
    monkeypatch.setattr(chain_module, "generate", lambda messages: "mocked answer")

    with indexed_client.stream(
        "POST",
        "/api/ask/stream",
        json={"question": "What is a time quantum?"},
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        raw = "".join(response.iter_text())

    events = [
        json.loads(chunk[len("data: "):])
        for chunk in raw.split("\n\n")
        if chunk.startswith("data: ")
    ]
    stages_seen = [e["stage"] for e in events]
    assert "routing" in stages_seen
    assert "retrieval" in stages_seen
    assert "reranking" in stages_seen
    assert "generation" in stages_seen
    assert stages_seen[-1] == "complete"


def test_ask_stream_requires_auth(client):
    response = client.post("/api/ask/stream", json={"question": "anything"})
    assert response.status_code == 401
