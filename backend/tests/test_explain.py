"""Tests for the first-principles explanation feature. The LLM boundary is
mocked; these check the endpoint's auth and how it builds the prompt."""

from fastapi.testclient import TestClient

from app.main import app
from app.rag import explain as explain_module

BODY = {
    "question": "What is round robin scheduling?",
    "answer": "Each process gets a fixed time quantum in turn.",
    "excerpts": ["Round-robin assigns each process a time quantum."],
}


def test_explain_requires_auth():
    with TestClient(app) as client:
        assert client.post("/api/explain", json=BODY).status_code == 401


def test_explain_passes_question_answer_and_excerpts_to_llm(auth_headers, monkeypatch):
    seen = {}

    def fake_generate(messages):
        seen["messages"] = messages
        return "step by step explanation"

    monkeypatch.setattr(explain_module, "generate", fake_generate)
    with TestClient(app) as client:
        res = client.post("/api/explain", json=BODY, headers=auth_headers)

    assert res.status_code == 200
    assert res.json() == {"explanation": "step by step explanation"}
    human = seen["messages"][1].content
    assert BODY["question"] in human
    assert BODY["answer"] in human
    assert BODY["excerpts"][0] in human
    assert "first principles" in seen["messages"][0].content
