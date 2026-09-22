# Milestone 14 — Deployment

## What problem are we solving?

The submission guidelines require either a live hosted URL or a GitHub repo precise enough that a stranger can get it running locally in under 15 minutes. Which one is actually the right choice isn't automatic — it depends on what this specific project's stack actually needs to run, not on which option sounds more impressive.

## Why does this problem exist, and why repo-only is the right call here (not just the easy one)

This project's real dependency footprint: PyTorch, `sentence-transformers`, FAISS, and a cross-encoder reranker — roughly 1-2GB installed, all local ML inference, plus a FAISS index persisted to local disk that grows every time a document is uploaded. Most free-tier serverless/hosted platforms have two problems with exactly this profile:

```
Memory: many free tiers cap around 512MB RAM -- loading an embedding
model AND a cross-encoder AND an LLM client library simultaneously
can exceed that on the cheapest tiers

Disk: "free" web-service tiers commonly have EPHEMERAL disk -- every
restart/redeploy wipes anything written to the local filesystem,
including data/index/ -- a deployed demo would silently lose every
uploaded document's index between sessions, which is worse than not
deploying at all, because it LOOKS like it works until someone
refreshes the service and finds an empty index
```

The submission guidelines explicitly name this exact situation ("heavier local infra... that don't deploy cleanly to a free host") as the intended case for Option B. Choosing repo-only here isn't cutting a corner — a hosted deployment that quietly loses data or crashes under memory pressure would be a *less* honest, *less* reliable submission than a repo that's been proven, with real evidence, to work.

## What we did

Rather than assert "the README is good enough, trust it," ran an actual reproducibility test: cloned the real, pushed GitHub repo (`https://github.com/kikako-saravanan/stydylens.git`) fresh into a completely separate directory — not the working copy this project was built in — and followed the README's own setup instructions exactly as written, including its own documented workaround for this network's corporate TLS proxy, timing each real step.

## What happened — real commands, real output, real timings

```
$ git clone https://github.com/kikako-saravanan/stydylens.git repro-test
Cloning into 'repro-test'...
```

**Backend:**
```
$ cd repro-test/backend && python3 -m venv .venv && source .venv/bin/activate
$ pip install --cert /Users/4723859/python-ca-bundle.pem -r requirements.txt
  [installs the full stack: fastapi, sentence-transformers, faiss-cpu,
   langchain-anthropic, ragas, pytest, ...]
START: 17:28:13 -> PIP INSTALL DONE: 17:32:36   (4m 23s)
```
One transient network hiccup during install (`ReadTimeoutError` on a single package), auto-retried by pip and resolved on its own — not a repo issue, a real but self-healing network blip.

```
$ cp <real .env with API keys> .env
$ HF_HUB_OFFLINE=1 uvicorn app.main:app --port 8010
INFO:     Started server process
Loading weights: 100%|██████████| 103/103  # embedding model
Loading weights: 100%|██████████| 105/105  # cross-encoder
INFO:     Application startup complete.
```
Server ready roughly 90 seconds after start (local model loading, no network calls given `HF_HUB_OFFLINE=1` and already-cached models).

```
$ curl http://127.0.0.1:8010/health
{"status":"ok"}

$ curl -u studylens:studylens-demo-2026 -F "file=@data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf" http://127.0.0.1:8010/api/upload
HTTP 200

$ curl -u studylens:studylens-demo-2026 -X POST http://127.0.0.1:8010/api/ask -d '{"question": "What is a time quantum?"}'
HTTP 200
{"answer": "A time quantum (also called a time slice) is a small unit of
time defined for Round-Robin (RR) scheduling. It is generally from 10 to
100 milliseconds in length. ..."}
```
Not just "it installs" — a real, freshly-cloned, freshly-installed server produced a real, correct, grounded answer.

**Frontend:**
```
$ cd repro-test/frontend && npm install
added 365 packages, and audited 366 packages in 9s

$ cp .env.local.example .env.local && npx next build
✓ Compiled successfully
✓ Generating static pages using 5 workers (4/4)
```
Clean build, no errors, no warnings beyond a routine ESLint version notice.

**Cleanup:** the temp clone (including the copied `.env` with real API keys) was deleted immediately after the test — nothing from this reproducibility check was left lying around with live credentials in it.

## Total realistic time, honestly reasoned

Summed real measurements: ~4m 23s (pip install) + ~1m 30s (config + startup) + a few seconds (upload/ask verification) + 9s (npm install) + a few seconds (build) — comfortably under 10 minutes of actual required work, well inside the submission guidelines' 15-minute bar for Option B. This excludes the time to *obtain* an Anthropic API key in the first place, which is a one-time external prerequisite no repo's README can eliminate — the same way any project requiring a paid or free-tier API key has that same, out-of-scope first step.

## What can go wrong

- **A reviewer without an Anthropic API key** can still verify Milestones 1-5 (ingestion, chunking, embeddings, FAISS retrieval via `/api/query`) with zero LLM cost, but `/api/ask` genuinely requires a working key — there's no way around this given the assignment's own requirement for real LLM-backed generation.
- **A reviewer on a different network** won't hit this machine's specific corporate-proxy certificate issue at all — the README's fix for it is conditional ("if you see `CERTIFICATE_VERIFY_FAILED`"), not a mandatory step, so it shouldn't add friction for the common case.
- **First-run model downloads** (if a reviewer's Hugging Face cache is empty) will add real time beyond what was measured here, since this test benefited from already-cached models on this machine. A completely cold-cache run would need to budget for two ~90MB local model downloads.

## Self-check questions

1. Why was the temp clone deleted immediately after the reproducibility test, rather than left in place as ongoing evidence?
2. The reproducibility test copied a real, working `.env` into the fresh clone rather than having the test itself independently obtain new API keys. What exactly does this test prove, and what does it explicitly *not* prove?
3. Why does a "free-tier ephemeral disk" concern specifically make Option A (hosted) worse for *this* project, when many other Phase 1 submissions in the same assignment presumably chose hosted deployment successfully?

<details><summary>Answers</summary>

1. It contained a copy of real, working API credentials (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) — leaving a second copy of live secrets sitting in a temp directory indefinitely would be an unnecessary, avoidable exposure risk, especially given this project's own established pattern this session of treating credential hygiene seriously (the earlier GitHub PAT handling, for instance). The test's *evidence* (the real commands and output shown above) is what's kept, not the live directory itself.
2. It proves the **setup process** — install, configure, start, use — is correct and reproducible from a clean clone, using the exact steps documented in the README. It does *not* prove that a reviewer with zero prior Anthropic account would experience an identical timeline, since creating an account and obtaining a key is a real, if usually quick, external step this test didn't measure (deliberately — that step is outside this repo's control, same as for any project needing a paid or free-tier API key).
3. Not every RAG project depends this heavily on large local ML models running as *inference*, as opposed to calling everything out to external APIs. A project that calls out to hosted embedding/LLM APIs for every step (no local `sentence-transformers`, no local FAISS persisted to disk, no local cross-encoder) has a much lighter, more serverless-friendly footprint and can deploy cleanly to a free host without hitting memory or ephemeral-disk problems — that's likely the profile of Phase 1 submissions that successfully went the hosted route. This project specifically chose *local, free, zero-API-cost* embeddings and reranking (Milestones 4 and 8) as a deliberate architecture decision, which is exactly what makes it heavier to host but also exactly what keeps its per-query cost near zero for anything except the actual LLM generation call.
</details>
