# Milestone 12 — Testing

## What problem are we solving?

Every claim made in Milestones 1-11 so far — "retrieval changes per question," "reranking really reorders results," "the system refuses to hallucinate" — was verified by manually running a command and reading the output. That's real evidence, but it's not *repeatable* evidence: nothing stops a future change from quietly breaking one of these properties without anyone noticing until a demo goes wrong. Automated tests turn "I checked this once" into "this is checked every time."

## Why does this problem exist — and why isn't "just add tests" a single, uniform answer?

Different parts of this system have fundamentally different testing needs, because they have different cost/speed/determinism profiles:

```
Pure functions (chunk_text's overlap math, make_snippet's boundary logic)
  -> deterministic, instant, free -> UNIT TESTS, no I/O at all

Local ML components (embeddings, FAISS, cross-encoder reranker)
  -> deterministic-ish, fast, free (runs on your own machine)
  -> INTEGRATION TESTS against the real thing -- no reason to mock
     something free and local, and mocking it would hide exactly what
     the assignment's grading criteria wants to see proven real

External paid LLM calls (routing classification, answer generation)
  -> non-deterministic, slow (network), costs real money per call
  -> the code AROUND the LLM call (merge logic, citation building,
     failure-fallback behavior) can and should be tested with the LLM
     boundary mocked -- fast, free, deterministic
  -> whether the LLM ITSELF behaves well is a separate question,
     answered by a small number of explicitly-gated real tests, or by
     RAGAS's evaluation (Milestone 9) -- not by every routine test run
```

This is also the practical answer to the classic "unit vs. integration vs. evaluation tests" distinction:
- **Unit tests** verify one function's logic in isolation.
- **Integration tests** verify multiple real components actually work together correctly (here: the real PDF parser, the real embedding model, the real FAISS index, the real reranker — none faked).
- **Evaluation tests** (RAGAS, Milestone 9) don't check "is this output exactly X" — they *score* output quality against criteria (faithfulness, relevancy, precision) using an LLM judge, because there's no single correct string for a generated answer to equal.

## What we implemented, where

`backend/tests/` — 29 tests across 7 files:
- `conftest.py` — shared fixtures, most importantly `isolated_faiss`: points the FAISS store at a fresh `tmp_path` per test and resets its cached in-memory state, so tests never touch (or get polluted by) a developer's real local index.
- `test_health.py`, `test_auth.py` — the two "does the API layer behave correctly" checks: `/health` open, everything else authenticated, with a helpful rejection message.
- `test_ingestion.py`, `test_chunking.py`, `test_embeddings.py` — unit/integration tests against real components: the real sample PDF, the real embedding model.
- `test_retrieval.py`, `test_reranking.py` — **never mocked**. Real FAISS index, real cross-encoder. `test_rerank_promotes_the_real_priority_scheduling_chunk` directly re-runs and asserts the exact before/after case documented in Milestone 8 (page 15 promoted from FAISS-rank-6 to rerank-rank-1) — a manual finding turned into a permanent regression check.
- `test_routing_and_chain.py` — the LLM boundary is mocked here, and only here, for three fast/free/deterministic tests (citation-from-retrieval property, multi-part merge logic, router failure fallback) — plus two real, live-LLM tests gated behind `RUN_LIVE_LLM_TESTS=1`.

## Why mocking the LLM here is not the same mistake as mocking retrieval/reranking

This distinction is worth being precise about, since "don't mock the important stuff" could be misread as "never mock anything." The assignment's own guidance is specific: mocks should not hide the *real retrieval/reranking implementation* — because that's the component whose genuine behavior is being graded (does retrieval really change per question; is reranking really reordering results). The LLM call inside routing/generation is different in kind: it's a paid, external, non-deterministic dependency, and the thing actually worth unit-testing around it — "does our merge-by-sub-question logic work," "do citations come from what was retrieved, not from parsed LLM text," "does a router failure degrade safely" — is orthogonal to whether the LLM itself reasons well on any given call. Those three tests would pass or fail identically no matter which LLM answered, because they're testing *our* code, not the model. Whether the *model* reasons well is answered elsewhere: by the real, recorded evidence in `docs/milestones/06` and `07`, by RAGAS (Milestone 9), and by the two real, explicitly-gated tests at the bottom of `test_routing_and_chain.py`.

## What happened — real output, both configurations

**Default run** (`python -m pytest tests/`):
```
27 passed, 2 skipped in 68.10s
```
The 2 skips are exactly the live-LLM tests, skipped with a clear reason (`Set RUN_LIVE_LLM_TESTS=1 to run tests that make real, billed LLM calls.`) — not silently disabled, not failing, explicitly opted out of by default.

**With live tests enabled** (`RUN_LIVE_LLM_TESTS=1 python -m pytest tests/test_routing_and_chain.py`):
```
5 passed in 61.16s
```
Including `test_live_grounded_answer_is_actually_grounded` and `test_live_out_of_scope_question_is_honestly_refused` — real, billed calls to the actual Claude API, actually passing, actually verified in this session rather than left as an unverified "should work in theory" gate.

## What can go wrong

- **The mocked-LLM tests could pass while the real LLM genuinely misbehaves** — they only prove our merge/citation/fallback code is correct, never that the model's actual output is good. This is a real, deliberate limitation of that specific test file, mitigated by the live-gated tests and RAGAS, not eliminated.
- **`isolated_faiss`'s tmp-directory isolation depends on correctly monkeypatching every module-level path constant** — if `faiss_store.py` grew a new hardcoded path in the future without updating the fixture, a test could silently start touching the real `data/index/` again. Worth remembering if that module changes.
- **Real, live-LLM tests are inherently a little flaky** — a model's phrasing varies, so `test_live_out_of_scope_question_is_honestly_refused` checks for one of several plausible refusal phrases rather than an exact string match, and could in principle need updating if the model's refusal phrasing style changes.
- **29 tests is a meaningful start, not exhaustive coverage** — edge cases like a zero-byte PDF upload, a question with no text at all, or concurrent uploads racing on the FAISS lock aren't covered here.

## Self-check questions

1. Why does `test_retrieval.py` never mock FAISS or the embedding model, while `test_routing_and_chain.py` mocks the LLM in 3 of its 5 tests?
2. `test_citations_come_from_retrieval_not_from_llm_text` mocks the LLM to return an answer that mentions nothing real, then asserts the sources are still populated with real chunks. What specific bug would this test have caught, that a test only checking "the answer contains an accurate citation" would have missed?
3. Why are the two live-LLM tests gated behind an explicit environment variable instead of just being slower tests that always run?

<details><summary>Answers</summary>

1. FAISS and the embedding model are local, free, and (for a fixed model + fixed input) effectively deterministic — there's no cost or speed reason to fake them, and the assignment's grading criteria specifically wants their *real* behavior demonstrated. The LLM call is a paid, external, network-dependent, non-deterministic dependency; mocking it in most tests lets those tests check the deterministic code *around* the call (merge logic, citation building) quickly and for free, while a small number of separate tests still exercise the real call end to end.
2. If citations were instead built by scanning the LLM's answer text for something citation-like (e.g., looking for page numbers mentioned in the prose, or asking the LLM to output its own source list), this test would have caught that regression immediately — the mocked answer mentions no sources at all, so any citation-extraction-from-text approach would produce zero or garbage citations here, while the real (correct) approach of building sources from what was actually retrieved keeps working regardless of what the answer text says.
3. Because they cost real money and introduce non-determinism into what would otherwise be a fast, deterministic, free test run. A developer (or CI system) running the test suite dozens of times a day while iterating shouldn't be forced to spend API credit or wait on network latency every single time; explicitly opting in when full end-to-end confidence is actually needed (e.g., before a release, or after changing the prompt/model) is the standard, deliberate trade-off for tests with a real external dependency.
</details>
