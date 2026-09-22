# Milestone 16 (bonus) — Live Pipeline Visualization

Added after the original 15 milestones, at the user's explicit request: a way to *watch* routing → retrieval → reranking → generation happen in real time from the browser, rather than only reading the finished JSON response — specifically for learning, not as a required deliverable.

## What problem are we solving?

`/api/ask`'s response already contains every stage's output (`query_type`, `retrieval_trace`, `pre_rerank_order`/`post_rerank_order`, `sources`) — Milestones 7, 8, and 10 made sure of that. But it arrives as one JSON blob after the *entire* pipeline finishes. Reading a finished result and watching a process happen are different learning experiences: the first tells you *what* happened, the second builds an intuition for *how long each stage actually takes* and *that they are genuinely sequential, dependent steps* — routing has to finish before you know what to retrieve for; retrieval has to finish before there's anything to rerank; reranking has to finish before there's a final context to generate from.

## Why does this problem exist?

A plain request/response HTTP call is fundamentally all-or-nothing — the client gets nothing until the server sends the complete response. To observe *intermediate* progress, the server has to proactively push partial information as it becomes available, before the overall request is done. That's what Server-Sent Events (SSE) are for: a single long-lived HTTP response where the server writes multiple small `data: ...` messages over time instead of one message at the end, and the browser reads them as they arrive rather than waiting for the connection to close.

## First principles

```
Normal request/response:
  client -> request -> [server does ALL the work] -> one response -> client

SSE streaming:
  client -> request -> server starts responding immediately, but keeps
  the connection open and writes one small message per real event ->
  client processes each message as it arrives, connection closes only
  once the server is done
```

The key insight that makes this NOT require rewriting the pipeline: the server-side work is unchanged — routing still calls the LLM, retrieval still queries FAISS, reranking still runs the cross-encoder, generation still calls the LLM. The only difference is *when* results are reported to the client: all at once at the very end (Milestone 6's `/api/ask`), versus incrementally as each stage genuinely completes (`/api/ask/stream`).

## What we implemented, where

**Backend:**
- `app/rag/chain.py` — split `_route_and_retrieve` into two separately-callable stages, `_classify_and_decompose` (routing alone) and `_retrieve_for_subquestions` (retrieval alone), so a caller can observe the boundary between them. `_route_and_retrieve` itself is kept as a thin composer of the two, so `build_chain()`/`answer_question()` (the batch path, Milestones 6-15) are completely unchanged. Added `stream_answer_question()`, a generator that calls the *exact same* stage functions the LCEL chain uses (`_classify_and_decompose`, `_retrieve_for_subquestions`, `rerank`, `_generate_answer`), yielding a `{"stage", "status", ...}` event immediately before and after each one.
- `app/main.py` — `POST /api/ask/stream`, wrapping `stream_answer_question()` in a FastAPI `StreamingResponse` with `media_type="text/event-stream"`, formatting each event as `data: {json}\n\n`. Errors are caught *inside* the generator and emitted as a `{"stage": "error"}` event rather than an HTTP error status — once a streaming response has started with `200`, the status code can no longer change, so a mid-stream failure has to be reported as data, not as an HTTP-level error.

**Frontend:**
- `lib/api.ts` — `streamAsk()`, an async generator consuming the SSE stream. Deliberately not the browser's native `EventSource` API: `EventSource` can only issue unauthenticated `GET` requests, and this needs a `POST` body plus a Basic Auth header — so it uses `fetch()` and manually parses the same `data: ...\n\n` framing a browser's native SSE client would parse for you, a well-known workaround for authenticated/POST SSE.
- `components/PipelinePanel.tsx` — four stage cards (routing, retrieval, reranking, generation), each showing a pending/running/done indicator and, once done, the real data for that stage (query type + sub-questions; candidate count; whether reranking changed the top result; a "generated" confirmation).
- `components/QAPanel.tsx` — a "Show pipeline stages" checkbox. Checked, submitting a question uses `streamAsk()` and renders `PipelinePanel` live, updating state after every received event; unchecked, it uses the original, faster `askQuestion()` (Milestone 11) unchanged.

## Why this doesn't create two divergent implementations of the pipeline

This was the main design risk worth naming: it would be easy to accidentally end up with two subtly-different copies of "how the pipeline works" — one for the normal path, one for the visualization path — that drift apart over time as one gets updated and the other doesn't. Avoided by construction: `stream_answer_question()` calls the identical functions `build_chain()` composes (`_classify_and_decompose`, `_retrieve_for_subquestions`, `rerank`, `_generate_answer`) — it's a different *orchestration* (a generator with `yield`s interspersed, instead of an LCEL `RunnableSequence`), not a second *implementation*. `test_streaming.py::test_stream_answer_question_final_event_matches_batch_answer` directly asserts the two paths produce identical final answers/sources/rerank ordering for the same question — a permanent check that they cannot silently diverge.

## What happened — real output

```
$ curl -N -u studylens:... -X POST .../api/ask/stream -d '{"question": "What is round robin scheduling?"}'

data: {"stage": "routing", "status": "start"}
data: {"stage": "routing", "status": "done", "query_type": "single_fact", "sub_questions": ["What is round robin scheduling?"]}
data: {"stage": "retrieval", "status": "start"}
data: {"stage": "retrieval", "status": "done", "retrieval_trace": [...], "candidate_count": 10}
data: {"stage": "reranking", "status": "start"}
data: {"stage": "reranking", "status": "done", "pre_rerank_order": [...], "post_rerank_order": [...]}
data: {"stage": "generation", "status": "start"}
data: {"stage": "generation", "status": "done", "answer": "...", "sources": [...]}
data: {"stage": "complete", ...full result...}
```
Real, observed event sequence — not simulated. Note the reranking step's real data here: `pre_rerank_order` started with page 16 first; `post_rerank_order` promoted page 15 to first — the same real reordering effect documented in Milestone 8, now visible as it happens rather than only in a finished response.

## What can go wrong

- **A dropped connection mid-stream** leaves the frontend with a partial `pipelineEvents` array and no `complete` event — the UI would show some stages as permanently "done" and later ones stuck at "pending" with no explicit error. Acceptable for a learning feature's current scope; a production version would want a timeout/retry affordance.
- **The two code paths (batch vs. streaming) still have to be kept in sync manually** when a new field is added to a stage's output — the shared-function design (above) prevents *logic* divergence, but each new field still has to be added to both the LCEL chain's final assembly (`answer_question`) and the generator's `yield` dicts by hand. Not automatic.
- **SSE holds a connection open for the whole pipeline's duration** (routing + retrieval + reranking + a full LLM generation call, several seconds total) — fine at this project's scale, a real resource-usage consideration at higher concurrent load.

## Self-check questions

1. Why couldn't the frontend use the browser's built-in `EventSource` API to consume this stream, and what had to be done instead?
2. Why does an error occurring during generation get reported as a `{"stage": "error"}` *event* rather than an HTTP `503`, even though `/api/ask` (the non-streaming endpoint) *does* return a `503` for the identical underlying failure?
3. What specific test in this project directly guards against the streaming and batch code paths silently producing different answers to the same question?

<details><summary>Answers</summary>

1. `EventSource` only supports plain `GET` requests with no custom headers and no request body — this endpoint needs a `POST` with a JSON body (the question) and a `Authorization: Basic ...` header for auth, neither of which `EventSource` can send. The workaround was to use `fetch()` directly (which supports full control over method/headers/body) and manually parse the streamed response body's `data: ...\n\n` chunks the same way `EventSource` would have, using a `ReadableStream` reader and a text decoder.
2. HTTP status codes are set once, at the start of a response, before any body bytes are sent. `StreamingResponse` commits to `200` the moment the first chunk is written — by the time a failure happens partway through generation, the client has already received a `200` and has no way to receive a different status for the same response. The only way to communicate a failure at that point is as data within the stream itself, which is exactly what the `{"stage": "error", "message": ...}` event does.
3. `test_streaming.py::test_stream_answer_question_final_event_matches_batch_answer` — it runs the *same* question through both `answer_question()` (the LCEL/batch path) and `stream_answer_question()` (the generator/streaming path) with the LLM mocked identically, then asserts the answer text, `post_rerank_order`, and source chunk IDs are exactly equal between the two. If a future edit changed one path's logic without the other, this test would fail.
</details>
