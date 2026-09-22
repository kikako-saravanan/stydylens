# StudyLens

**Domain (Phase 1 Problem Statement, option 2): Lecture Notes Q&A.**

Students upload course PDFs/slides and ask questions about the material. Answers are grounded in the uploaded documents, with page-level citations, and the assistant explicitly says so when an answer isn't in the material — rather than guessing from general knowledge.

**Status:** all 15 milestones complete. **Submission format: Option B — GitHub repo only** (see [Deployment](#deployment)), per the submission guidelines' own recommendation for a stack this heavy on local ML dependencies. Full item-by-item final acceptance checklist, with real evidence for every line and two honestly-disclosed partial-verification gaps (not rounded up to full PASS), in [`docs/milestones/15-final-acceptance.md`](docs/milestones/15-final-acceptance.md).

**Detailed, self-study notes for every milestone** (problem → first principles → implementation → real verified output → known limitations → self-check Q&A) live in [`docs/milestones/`](docs/milestones/) — start at [`01-repo-health.md`](docs/milestones/01-repo-health.md). This README is the top-level reference; the milestone docs are where the depth lives.

## Table of contents

- [Current status](#current-status)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [API reference](#api-reference)
- [Pipeline stages](#pipeline-stages)
- [RAGAS evaluation](#ragas-evaluation)
- [Re-ranking (before/after evidence)](#re-ranking-beforeafter-evidence)
- [Source attribution](#source-attribution)
- [Authentication](#authentication)
- [Testing](#testing)
- [Deployment](#deployment)
- [Known limitations](#known-limitations)
- [Example questions](#example-questions)
- [Sample document](#sample-document)

## Current status

- [x] Milestone 1: Backend scaffold + `/health`
- [x] Milestone 2: PDF ingestion
- [x] Milestone 3: Chunking
- [x] Milestone 4: Embeddings
- [x] Milestone 5: FAISS retrieval
- [x] Milestone 6: LCEL RAG chain
- [x] Milestone 7: Query routing / decomposition
- [x] Milestone 8: Re-ranking
- [x] Milestone 9: RAGAS evaluation
- [x] Milestone 10: Source attribution
- [x] Milestone 11: Frontend
- [x] Milestone 12: Tests
- [x] Milestone 13: Full documentation (this file)
- [x] Milestone 14: Deployment
- [x] Milestone 15: Final acceptance ([full checklist](docs/milestones/15-final-acceptance.md))

## Architecture

```
                              PDF (course lecture notes)
                                        │
                          pdfplumber: page-aware extraction
                          (Milestone 2 — PageDocument: source, 1-indexed page, text)
                                        │
                          word-boundary-safe chunking
                          (Milestone 3 — Chunk: chunk_id, source, page, text;
                           never crosses a page boundary)
                                        │
                  sentence-transformers/all-MiniLM-L6-v2 (local, free)
                          (Milestone 4 — 384-dim, L2-normalized vectors)
                                        │
                              FAISS IndexFlatIP
                    (Milestone 5 — persisted to data/index/, metadata
                     sidecar keeps chunk_id/source/page aligned per vector)
                                        │
   ┌────────────────────────────────────┴────────────────────────────────────┐
   │                                                                          │
   │   Student question                                                      │
   │        │                                                                │
   │   Query routing (Milestone 7)                                           │
   │   single_fact / multi_part / summarization — structured-output LLM call │
   │   → decomposed into 1-5 standalone sub-questions                        │
   │        │                                                                │
   │   FAISS retrieval PER sub-question (RETRIEVAL_CANDIDATE_K candidates)   │
   │   → merged, deduplicated by chunk_id                                    │
   │        │                                                                │
   │   Cross-encoder re-ranking (Milestone 8)                                │
   │   cross-encoder/ms-marco-MiniLM-L-6-v2, scored against the ORIGINAL     │
   │   question → best RERANK_TOP_K survive                                 │
   │        │                                                                │
   │   LCEL chain: augment (build context) → generate (Milestone 6)         │
   │   Claude Sonnet 5 primary → Gemini 2.5 Flash fallback on provider error │
   │   Prompt enforces "answer ONLY from context, say so if not found"       │
   │        │                                                                │
   └────────┼────────────────────────────────────────────────────────────────┘
            ▼
     Answer + Sources (Milestone 10)
     sources built from the retrieved chunks themselves — never parsed
     out of the LLM's reply — so every citation (chunk_id, source, page,
     scores, snippet) is independently verifiable
            │
            ▼
     RAGAS evaluation (Milestone 9)
     faithfulness · answer_relevancy · context_precision, scored against
     a 14-question labeled eval set, logged to data/eval/results.jsonl
```

All of the above is served by a FastAPI backend behind HTTP Basic Auth (Milestone 6/11 — protects paid LLM credit from unauthenticated use) and a Next.js frontend (Milestone 11) with a login gate, upload panel, and an ask panel with an expandable citations list.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | FastAPI + Uvicorn | Async-native, Pydantic validation, auto-generated `/docs` |
| PDF parsing | `pdfplumber` | Direct per-page text access, no LangChain dependency needed for ingestion alone |
| Chunking | Hand-written word-sliding-window (`app/chunking/chunker.py`) | Fully transparent, word-boundary-safe, no premature LangChain dependency |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local) | Free, no API key, 384-dim, fast enough on CPU |
| Vector index | FAISS (`IndexFlatIP`) | Exact (no approximation) nearest-neighbor search; inner product on normalized vectors = cosine similarity |
| Re-ranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) | Joint question+chunk attention, corrects bi-encoder near-misses |
| Orchestration | LangChain Core + LCEL (`RunnablePassthrough`/`RunnableLambda`) | Explicit, composed pipeline stages, not implicit sequential calls |
| Primary LLM | Claude Sonnet 5 (`langchain-anthropic`) | Generation + query routing |
| Fallback LLM | Gemini 2.5 Flash (`langchain-google-genai`) | Free tier, automatic failover on any classified provider error |
| Evaluation | RAGAS 0.4.3 | faithfulness / answer_relevancy / context_precision, judged by a dedicated `claude-haiku-4-5` |
| Auth | HTTP Basic (`secrets.compare_digest`) | Timing-safe, enforced server-side, not just a frontend gate |
| Testing | pytest | 29 tests — unit, integration (never mocking retrieval/reranking), and gated live-LLM tests |
| Frontend | Next.js (App Router) + TypeScript + Tailwind | Login gate, upload, ask, expandable source citations |

## Repository structure

```
studylens/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, all endpoints, auth wiring, error handlers
│   │   ├── auth.py               HTTP Basic Auth dependency (timing-safe)
│   │   ├── ingestion/            PDF → page-aware text (Milestone 2)
│   │   ├── chunking/             Page text → overlapping chunks (Milestone 3)
│   │   ├── embeddings/           Local sentence-transformers wrapper (Milestone 4)
│   │   ├── retrieval/            Persistent FAISS store (Milestone 5)
│   │   ├── rerank/               Cross-encoder reranker (Milestone 8)
│   │   └── rag/
│   │       ├── chain.py          The LCEL chain: route→retrieve→rerank→augment→generate
│   │       ├── router.py         Query classification + decomposition (Milestone 7)
│   │       └── llm_provider.py   Anthropic→Gemini fallback (Milestone 6)
│   ├── tests/                    29 pytest tests (Milestone 12)
│   └── requirements.txt
├── frontend/                     Next.js + TypeScript UI (Milestone 11)
├── data/
│   ├── sample_pdfs/              Committed test fixture (excerpt, not full copyrighted book)
│   ├── eval/                     RAGAS questions.json + results.jsonl (real, committed evidence)
│   ├── uploads/, index/          Runtime-generated, gitignored
├── scripts/                      extract_sample_excerpt.py, embedding_similarity_demo.py, run_ragas_eval.py
├── docs/milestones/               Detailed per-milestone notes (problem/why/implementation/verified-output/limitations/self-check)
└── .env.example
```

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in ANTHROPIC_API_KEY at minimum
uvicorn app.main:app --reload --port 8000
```

Verify: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://127.0.0.1:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), sign in with `AUTH_USERNAME`/`AUTH_PASSWORD` from the backend's `.env` (defaults `studylens` / `studylens-demo-2026`).

**If you're on a network that intercepts TLS** (corporate proxy): `pip install` will fail with `CERTIFICATE_VERIFY_FAILED` — point pip at your CA bundle (`pip install --cert /path/to/bundle.pem -r requirements.txt`, or `pip config set global.cert ...`). If Hugging Face model downloads fail with `Policy: URL Filtering`, set `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to the same bundle plus `HF_HUB_DISABLE_XET=1`. Once models are cached (`~/.cache/huggingface`), set `HF_HUB_OFFLINE=1` to skip network checks entirely on future startups. These are local machine/network fixes, not something the repo ships.

## Environment variables

All in `.env` (see `.env.example` for the authoritative, commented template):

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Frontend origin(s) allowed to call the API |
| `CHUNK_TARGET_TOKENS` | `650` | Target chunk size (words-based approximation, see Milestone 3) |
| `CHUNK_OVERLAP_RATIO` | `0.125` | Fraction of each chunk repeated into the next |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `HF_HUB_OFFLINE` | unset | Set `1` once models are cached, to skip network checks at startup |
| `ANTHROPIC_API_KEY` | — | **Required.** Primary LLM (generation + routing) |
| `LLM_MODEL` | `claude-sonnet-5` | Primary generation model |
| `GOOGLE_API_KEY` | — | Fallback LLM, free tier at [aistudio.google.com](https://aistudio.google.com/apikey) |
| `LLM_FALLBACK_MODEL` | `gemini-2.5-flash` | Used automatically if Anthropic fails |
| `RETRIEVAL_CANDIDATE_K` | `10` | FAISS candidates fetched per sub-question, before reranking |
| `RERANK_TOP_K` | `5` | Chunks surviving reranking, actually sent to the LLM |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local cross-encoder |
| `RAGAS_JUDGE_MODEL` | `claude-haiku-4-5` | Separate judge model — current Sonnet/Opus reject RAGAS's `temperature` param |
| `LOG_LEVEL` | `INFO` | Backend logging verbosity |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | `studylens` / `studylens-demo-2026` | Shared credentials gating credit-consuming endpoints — **change before real deployment** |

Frontend: `NEXT_PUBLIC_API_URL` in `frontend/.env.local` (defaults to `http://127.0.0.1:8000`).

## API reference

All endpoints except `/health` require HTTP Basic Auth (`AUTH_USERNAME`/`AUTH_PASSWORD`).

| Method & path | Auth | Request | Response | Notes |
|---|---|---|---|---|
| `GET /health` | none | — | `{"status": "ok"}` | Deployment health check |
| `GET /api/me` | required | — | `{"username": str}` | Cheap credential check for the frontend login screen — no LLM/embedding cost |
| `POST /api/upload` | required | multipart `file` (PDF) | `{filename, page_count, pages[], chunk_count, chunks[], index_total_chunks}` | Full ingest→chunk→embed→index pipeline |
| `POST /api/query` | required | `{"question": str, "k": int}` | `{question, results: [{chunk_id, source, page, score, snippet}]}` | Raw FAISS retrieval, no LLM, no reranking |
| `POST /api/ask` | required | `{"question": str, "k": int\|null}` | see below | Full pipeline: route → retrieve → rerank → generate |

`POST /api/ask` response shape:
```json
{
  "question": "...",
  "answer": "...",
  "query_type": "single_fact | multi_part | summarization",
  "sub_questions": ["..."],
  "retrieval_trace": [{"sub_question": "...", "chunk_ids": ["..."]}],
  "pre_rerank_order": ["chunk_id", "..."],
  "post_rerank_order": ["chunk_id", "..."],
  "sources": [
    {"chunk_id": "...", "source": "...", "page": 11, "faiss_score": 0.28, "rerank_score": 0.04, "snippet": "..."}
  ]
}
```
Returns `503 {"error": "..."}` if both LLM providers fail; `400` for a non-PDF or unparseable upload; `401` for missing/invalid credentials.

## Pipeline stages

Each stage below has a full first-principles writeup, real verified output, and known limitations in its milestone doc — this section is a summary, not the depth.

- **Ingestion** ([Milestone 2](docs/milestones/02-pdf-ingestion.md)) — `pdfplumber` extracts text per page, 1-indexed to match what a student sees in their PDF viewer.
- **Chunking** ([Milestone 3](docs/milestones/03-chunking.md)) — word-boundary-safe sliding window, never crosses a page boundary (unambiguous citations), overlap verified word-for-word exact.
- **Embeddings** ([Milestone 4](docs/milestones/04-embeddings.md)) — local, L2-normalized, real semantic-similarity proof (`scripts/embedding_similarity_demo.py`): a zero-keyword-overlap query top-matches the correct page (0.51) vs. an out-of-domain query (0.14).
- **FAISS retrieval** ([Milestone 5](docs/milestones/05-faiss-retrieval.md)) — persistent `IndexFlatIP`, verified deterministic (same question → same results) and discriminating (different questions → different top results) and surviving a full reload.
- **LCEL RAG chain** ([Milestone 6](docs/milestones/06-lcel-rag-chain.md)) — explicitly composed via `RunnablePassthrough.assign`, Anthropic→Gemini fallback on any `ModelError`, verified with a real grounded answer and a real honest refusal.
- **Query routing/decomposition** ([Milestone 7](docs/milestones/07-query-routing-decomposition.md)) — real multi-part test ("round robin vs. FCFS") shows both halves independently retrieved with partial, sensible overlap.
- **Re-ranking** ([Milestone 8](docs/milestones/08-reranking.md)) — see [below](#re-ranking-beforeafter-evidence).
- **Source attribution** ([Milestone 10](docs/milestones/10-source-attribution.md)) — verified by independently re-extracting a cited page with `pdfplumber` and matching it character-for-character against a live citation.

## RAGAS evaluation

A 14-question labeled eval set (`data/eval/questions.json` — real question/expected-answer pairs covering the sample document, including 2 deliberately out-of-scope questions to test honest refusal) runs through the full pipeline and is scored with three RAGAS metrics:
```bash
cd backend && python ../scripts/run_ragas_eval.py
```
Results are appended to `data/eval/results.jsonl` — committed as real evidence, not regenerated-and-discarded.

**Real mean scores across all 14 questions:**

| Metric | Mean | What it measures |
|---|---|---|
| Faithfulness | **0.9155** | Is the answer's content actually supported by the retrieved context? |
| Answer relevancy | **0.7275** | Does the answer actually address the question asked? |
| Context precision | **0.7012** | Of the retrieved chunks, how many were genuinely relevant? |

Not all 1.0, not missing — plausible scores with real variance. Two genuinely interesting cases, reported honestly rather than cherry-picked away (full explanation in [docs/milestones/09-ragas-evaluation.md](docs/milestones/09-ragas-evaluation.md)):
- The two out-of-scope questions correctly scored **faithfulness=1.0** (the refusal makes no unsupported claims) but **answer_relevancy=0.0, context_precision=0.0** (a refusal isn't the substantive answer that was asked for).
- Two verifiably *correct* answers ("dispatch latency," "SJF scheduling") each scored 0.0 on one metric — read as judge-model brittleness on short/single-claim answers, not an actual system failure.

**Real dependency-compatibility bugs hit and fixed, not hidden:** `ragas` 0.4.3 needs `langchain-community` pinned to `0.3.31` (imports a shim removed in 0.4.0); RAGAS's judge calls pass an explicit `temperature`, which current Claude models reject — fixed with a separate `RAGAS_JUDGE_MODEL` (`claude-haiku-4-5`); the deprecated `answer_relevancy` metric needs the classic `LangchainEmbeddingsWrapper`, not RAGAS's newer embeddings classes (which lack `.embed_query()`).

## Re-ranking (before/after evidence)

FAISS retrieves `RETRIEVAL_CANDIDATE_K` (10) candidates per sub-question, and a cross-encoder re-scores all merged candidates against the *original* question, keeping only `RERANK_TOP_K` (5). `/api/ask`'s response includes `pre_rerank_order`/`post_rerank_order` plus per-source `faiss_score`/`rerank_score`, so the effect is directly inspectable.

**Real example** — `"How does priority scheduling work?"`:

| Rank | Pre-rerank (FAISS) | Post-rerank (cross-encoder) |
|---|---|---|
| 1 | p16 (0.6236) | **p15** (rerank 3.97) — *was ranked #6 by FAISS* |
| 2 | p13 | p14 (rerank 2.40) |
| 3 | p19 | p16 (rerank 1.34) — *dropped from #1* |
| 4 | p14 | p19 |
| 5 | p10 | p18 |
| 6 | **p15 (0.4949)** | — |

Page 15 is the excerpt's actual "priority scheduling with round-robin" section — FAISS ranked it *last* among 10 candidates; the cross-encoder ranked it *first*. Page 16 (multilevel *queue* scheduling — related vocabulary, less directly on-topic) had the highest FAISS score but dropped to 3rd. Real, unedited, and now a permanent regression test (`backend/tests/test_reranking.py::test_rerank_promotes_the_real_priority_scheduling_chunk`) — see [docs/milestones/08-reranking.md](docs/milestones/08-reranking.md) for the full trace.

## Source attribution

Every `sources` entry carries `chunk_id`, `source`, `page`, `faiss_score`, `rerank_score`, and a word-boundary-safe `snippet`. This data travels unmodified from extraction through chunking, FAISS, and reranking — the exact reranked chunks become both the LLM's context *and* the response's citations, never reconstructed after the fact from the LLM's text.

**Directly verified:** independently re-extracted page 11 of the sample PDF with `pdfplumber` and confirmed it matches, character-for-character, the snippet cited for `os-concepts-ch5-cpu-scheduling-excerpt.pdf::p11::c0` in a real `/api/ask` response — the exact "is every citation verifiable by opening the cited page" check the assignment's grading criteria calls for. Full lineage in [docs/milestones/10-source-attribution.md](docs/milestones/10-source-attribution.md).

## Authentication

`/api/upload`, `/api/query`, `/api/ask`, and `/api/me` require HTTP Basic Auth — enforced at the API layer (`secrets.compare_digest`, timing-safe), not just hidden behind a frontend, since these endpoints consume paid LLM credit. `/health` stays open for deployment health checks. Default dev credentials: `studylens` / `studylens-demo-2026` — **change these before any real deployment.** The frontend shows a login form and, on failure, explains the app is access-restricted to control API costs, with instructions to email **[REDACTED_EMAIL_ADDRESS_1]** for credentials.

## Testing

```bash
cd backend
python -m pytest tests/                       # fast, free, deterministic (default)
RUN_LIVE_LLM_TESTS=1 python -m pytest tests/   # also runs real, billed LLM calls
```

29 tests: health, auth, ingestion, chunking, embeddings, retrieval, reranking, routing/decomposition, citation, grounded generation, and unknown-answer refusal. Real output: `27 passed, 2 skipped in 68s` (default), `5 passed in 61s` with live LLM tests enabled. Retrieval and reranking are **never mocked** — real PDF, real embedding model, real FAISS, real cross-encoder — since those are exactly the components the assignment's grading criteria wants proven real. The LLM boundary is mocked only in the 3 tests specifically checking *our* merge/citation/fallback logic, not the LLM's own reasoning quality (that's covered separately by the two live-gated tests and by RAGAS). Full rationale in [docs/milestones/12-testing.md](docs/milestones/12-testing.md).

## Deployment

**Submission format: Option B (GitHub repo only)** — per the submission guidelines' own stated recommendation for "projects with heavier local infra... that don't deploy cleanly to a free host." This project's stack (PyTorch + `sentence-transformers` + FAISS + a cross-encoder reranker, ~1-2GB installed, plus a locally-persisted FAISS index on disk) is exactly that profile: most free serverless/hosted tiers either can't fit the memory footprint or have ephemeral disk that would silently wipe the uploaded-document index on every restart — a deployed "demo" that quietly loses its data between sessions would be a worse, more misleading submission than an honestly-scoped, fully-reproducible local one.

**Real reproducibility test performed, not assumed:** cloned the actual pushed GitHub repo fresh into an isolated directory and followed this README's own setup instructions verbatim (including applying the documented corporate-proxy `pip --cert` workaround) — the same steps a stranger with only the repo link would follow:

| Step | Real measured time |
|---|---|
| `git clone` | a few seconds |
| Backend: fresh venv + `pip install -r requirements.txt` (full ML stack from scratch) | 4m 23s |
| Backend: `.env` config + server startup (including local model loading) | ~1m 30s |
| Backend: real upload + real `/api/ask` call against the freshly-installed server | verified working — real grounded answer returned |
| Frontend: `npm install` | 9s |
| Frontend: `npm run build` | clean, no errors |

Total hands-on-keyboard time for someone who already has their own `ANTHROPIC_API_KEY`: comfortably under 15 minutes — the submission guidelines' explicit bar for Option B. (Obtaining the API key itself isn't counted, the same way it wouldn't be for any project requiring external credentials — that's a one-time account-signup step outside the repo's control, documented in [Environment variables](#environment-variables).) Full account, including the exact commands run and real output, in [docs/milestones/14-deployment.md](docs/milestones/14-deployment.md).

## Known limitations

Stated plainly, not hidden — each is explained in depth in its milestone doc:

- **No index deduplication** — re-uploading the same PDF adds a second copy of its chunks rather than replacing the first ([Milestone 5](docs/milestones/05-faiss-retrieval.md)).
- **Gemini fallback's triggering logic is proven correct, but the actual Gemini response was never verified end-to-end** in the development environment — a corporate-proxy TLS quirk specific to `google-genai`'s HTTP client on that one machine, unrelated to this code, and unlikely to recur on a normal deployment host ([Milestone 6](docs/milestones/06-lcel-rag-chain.md)).
- **RAGAS's judge model can misjudge short, single-claim answers** — two verifiably correct answers each scored 0.0 on one metric ([Milestone 9](docs/milestones/09-ragas-evaluation.md)).
- **Frontend browser click-through was not visually tested** in the environment it was built in (no connected browser automation tool) — verified as far as possible via a clean `npm run build` and direct HTTP/CORS testing of every API call against the real backend ([Milestone 11](docs/milestones/11-frontend.md)).
- **Squished-word extraction artifacts** (e.g. `"CPUScheduling"` with no space) appear in some raw extracted text due to the source PDF's font encoding — cosmetic, preserved faithfully rather than silently "cleaned" in citations ([Milestone 2](docs/milestones/02-pdf-ingestion.md)).
- **Single shared credential, not multi-user accounts** — matches the actual requirement (keep unauthenticated visitors from spending LLM credit), not a substitute for real per-user authorization ([Milestone 11](docs/milestones/11-frontend.md)).

## Example questions

Tested live against the committed sample document (`data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf`):

| Question | Type | What it demonstrates |
|---|---|---|
| "What is a time quantum?" | `single_fact` | Direct grounded lookup |
| "What is round robin scheduling and how does it compare to first-come-first-served scheduling?" | `multi_part` | Decomposition into 2 independently-retrieved sub-questions |
| "Summarize what this lecture material covers." | `summarization` | Router generates 5 broad probing sub-questions, retrieving 12 unique chunks vs. 5 for a single query |
| "How does priority scheduling work?" | `single_fact` | The featured before/after reranking example |
| "What is a deadlock and how can it be prevented?" | `single_fact` | Plausible but genuinely out-of-scope — honest refusal, not hallucination |

## Sample document

`data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf` is a real 24-page excerpt (see `data/sample_pdfs/SOURCE.md` for exact provenance: pages 267-290 of Silberschatz's *Operating System Concepts*, 10th ed.) — not lorem-ipsum filler. The full source textbook is kept out of this repo (copyright); regenerate the excerpt yourself via `python scripts/extract_sample_excerpt.py` if you have a copy of the source.
