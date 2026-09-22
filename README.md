# StudyLens

**Domain chosen (Phase 1 Problem Statement, option 2): Lecture Notes Q&A.**

Students upload course PDFs/slides and ask questions about the material. Answers are grounded in the uploaded documents, with page-level citations, and the assistant explicitly says so when an answer isn't in the material rather than guessing.

Architecture, tech stack, API reference, and evaluation results will be filled in as each stage is built. This section is kept current after every milestone, not written at the end.

**Detailed, self-study notes for every milestone** (problem → first principles → implementation → real verified output → known limitations → self-check Q&A) live in [`docs/milestones/`](docs/milestones/) — start at [`01-repo-health.md`](docs/milestones/01-repo-health.md).

## Current status

- [x] Milestone 1: Backend scaffold + `/health`
- [x] Milestone 2: PDF ingestion
- [x] Milestone 3: Chunking
- [x] Milestone 4: Embeddings
- [x] Milestone 5: FAISS retrieval
- [x] Milestone 6: LCEL RAG chain
- [x] Milestone 7: Query routing / decomposition
- [x] Milestone 8: Re-ranking
- [ ] Milestone 9: RAGAS evaluation
- [ ] Milestone 10: Source attribution
- [ ] Milestone 11: Frontend
- [ ] Milestone 12: Tests
- [ ] Milestone 13: Full documentation
- [ ] Milestone 14: Deployment

## Setup (backend, so far)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Verify: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`

Upload a PDF and get page-aware extraction (page count + per-page char counts; full text logged server-side):
```bash
curl -F "file=@data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf" http://127.0.0.1:8000/api/upload
```

The upload response also includes `chunk_count` and per-chunk metadata (`chunk_id`, `page`, `char_count`) — chunking runs automatically on every upload. Tune via `.env`: `CHUNK_TARGET_TOKENS` (default 650) and `CHUNK_OVERLAP_RATIO` (default 0.125). Note: chunks never cross a page boundary (see Milestone 3 notes) and this sample document's pages are all shorter than the default target size, so at defaults you'll see exactly one chunk per page — lower `CHUNK_TARGET_TOKENS` (e.g. to 150) to see a page actually split into multiple overlapping chunks.

Every chunk is embedded locally via `sentence-transformers/all-MiniLM-L6-v2` (no API key, configurable via `EMBEDDING_MODEL`) and added to a persistent FAISS index as part of the upload pipeline — the response includes `index_total_chunks` (running total across all uploads so far). Real semantic-similarity proof (not toy examples) against the sample document:
```bash
python scripts/embedding_similarity_demo.py
```
This embeds every chunk and ranks them by cosine similarity against three test queries — one phrased with completely different words than the source text, one naming a specific concept, and one entirely out of domain — showing genuine semantic matching (top score ~0.51) clearly separated from the out-of-domain query (top score ~0.14).

Query the persisted index directly:
```bash
curl -X POST http://127.0.0.1:8000/api/query -H "Content-Type: application/json" \
  -d '{"question": "How does round robin scheduling work?", "k": 3}'
```
Returns ranked results (`chunk_id`, `source`, `page`, `score`, `snippet`). The index survives server restarts (persisted to `data/index/`, gitignored — regenerate by re-uploading).

**Known limitation:** no deduplication — re-uploading the same file adds a second copy of all its chunks to the index rather than replacing the first. Fine for this project's scope (single upload per document in the demo flow); a real product would need a "replace existing chunks for this filename" step before adding.

### Ask a grounded question (full LCEL chain: retrieve → augment → generate)

```bash
curl -u studylens:studylens-demo-2026 -X POST http://127.0.0.1:8000/api/ask -H "Content-Type: application/json" \
  -d '{"question": "What is round robin scheduling and how does the time quantum affect it?"}'
```
Returns `{"question", "answer", "sources"}` — `sources` are the exact chunks retrieved and fed to the LLM (not something parsed out of its reply), so every citation is independently verifiable. Ask something plausible but genuinely outside the uploaded material (e.g. "What is a deadlock and how can it be prevented?" — not covered by the CPU-scheduling excerpt) and the assistant explicitly says it couldn't find that in the uploaded material, rather than answering from general knowledge.

**LLM provider + fallback:** primary is Claude (`ANTHROPIC_API_KEY`/`LLM_MODEL`, default `claude-sonnet-5`). If Anthropic fails for any reason (credit exhausted, rate limited, timed out — any `langchain_core.exceptions.ModelError`), it automatically falls back to Gemini (`GOOGLE_API_KEY`/`LLM_FALLBACK_MODEL`, free tier at [aistudio.google.com](https://aistudio.google.com/apikey)). If both providers fail, `/api/ask` returns a clean `503` with a helpful message instead of a raw stack trace.

### Query routing & decomposition

Every question is classified before retrieval into `single_fact`, `multi_part`, or `summarization` (a structured-output LLM call — see `docs/milestones/07-query-routing-decomposition.md`). `multi_part` and `summarization` decompose into several sub-questions, each retrieved independently, then merged (deduplicated by chunk id) before generation — so a question like *"What is X and how does it compare to Y?"* gets dedicated retrieval for both X and Y instead of one side dominating a single combined-embedding search. The response now includes `query_type`, `sub_questions`, and `retrieval_trace` (which chunks came from which sub-question) alongside the usual `answer`/`sources`:
```bash
curl -u studylens:studylens-demo-2026 -X POST http://127.0.0.1:8000/api/ask -H "Content-Type: application/json" \
  -d '{"question": "What is round robin scheduling and how does it compare to first-come-first-served scheduling?"}'
```
If routing itself fails for any reason, it degrades to treating the question as `single_fact` (the Milestone 6 behavior) rather than failing the whole request.

### Re-ranking (before/after evidence)

FAISS retrieves `RETRIEVAL_CANDIDATE_K` (default 10) candidates per sub-question — deliberately more than what reaches the LLM — and a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) re-scores all merged candidates against the *original* question, keeping only `RERANK_TOP_K` (default 5). `/api/ask`'s response includes `pre_rerank_order` and `post_rerank_order` (chunk id lists) plus per-source `faiss_score` and `rerank_score`, so the effect is directly inspectable, not just claimed.

**Real example** — `"How does priority scheduling work?"`:

| Rank | Pre-rerank (FAISS) | Post-rerank (cross-encoder) |
|---|---|---|
| 1 | p16 (0.6236) | **p15** (rerank 3.97) — *was ranked #6 by FAISS* |
| 2 | p13 | p14 (rerank 2.40) |
| 3 | p19 | p16 (rerank 1.34) — *dropped from #1* |
| 4 | p14 | p19 |
| 5 | p10 | p18 |
| 6 | **p15 (0.4949)** | — |

Page 15 is the excerpt's actual "priority scheduling with round-robin" section — FAISS's embedding search ranked it *last* among the top-10 candidates (lowest similarity score, 0.4949), but the cross-encoder ranked it *first* (highest relevance score) once it could directly attend to the question and that specific chunk together, rather than comparing two independently-computed vectors. Page 16 (multilevel *queue* scheduling — related vocabulary, less directly on-topic) had the *highest* FAISS similarity but dropped to 3rd after reranking. This is a real, unedited before/after pair, not a constructed example — see `docs/milestones/08-reranking.md` for the full trace and more detail on why bi-encoders and cross-encoders disagree here.

### Authentication

`/api/upload`, `/api/query`, and `/api/ask` require HTTP Basic Auth (`AUTH_USERNAME`/`AUTH_PASSWORD` in `.env`) — enforced at the API level, not just hidden behind a frontend, since these endpoints consume paid LLM credit. `/health` stays open (deployment platforms need to reach it without credentials). Default dev credentials: `studylens` / `studylens-demo-2026` — **change these before any real deployment.** The eventual frontend (Milestone 11) will show a login form and, on failure, a message explaining the app is access-restricted to control API costs, with instructions to email **msaravanan1998@gmail.com** for credentials.

### Error handling & logging

Replaced ad-hoc `print()` with Python's `logging` module (`LOG_LEVEL` in `.env`); a global FastAPI exception handler logs full tracebacks server-side but returns clean, generic JSON errors to clients (never a raw stack trace); malformed uploads (non-PDF, corrupt file) return a `400` with a clear message instead of crashing.

**Note on this environment:** if `sentence-transformers` model downloads fail with a `Policy: URL Filtering` error, your network's security proxy is blocking Hugging Face's CDN. Try setting `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to your corporate CA bundle and `HF_HUB_DISABLE_XET=1`. Once downloaded, the model is cached in `~/.cache/huggingface` and no further network access is needed (set `HF_HUB_OFFLINE=1` to skip even the startup metadata check).

### Sample document

`data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf` is a 24-page excerpt (see `data/sample_pdfs/SOURCE.md` for exact provenance) used as the realistic test document throughout this project — not lorem-ipsum filler. The full source textbook it's drawn from is kept out of this repo (copyright); regenerate the excerpt yourself via `python scripts/extract_sample_excerpt.py` if you have a copy of the source.

**Note if you're on a corporate network that intercepts TLS** (you'll see `pip install` fail with `CERTIFICATE_VERIFY_FAILED`): point pip at your organization's CA bundle, e.g. `pip install --cert /path/to/corporate-ca-bundle.pem -r requirements.txt`, or set it once via `pip config set global.cert /path/to/bundle.pem`. This is a local machine/network fix, not something the repo can ship — nothing here or in `.gitignore`d files depends on it.
