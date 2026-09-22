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
- [ ] Milestone 6: LCEL RAG chain
- [ ] Milestone 7: Query routing / decomposition
- [ ] Milestone 8: Re-ranking
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

**Note on this environment:** if `sentence-transformers` model downloads fail with a `Policy: URL Filtering` error, your network's security proxy is blocking Hugging Face's CDN. Try setting `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to your corporate CA bundle and `HF_HUB_DISABLE_XET=1`. Once downloaded, the model is cached in `~/.cache/huggingface` and no further network access is needed (set `HF_HUB_OFFLINE=1` to skip even the startup metadata check).

### Sample document

`data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf` is a 24-page excerpt (see `data/sample_pdfs/SOURCE.md` for exact provenance) used as the realistic test document throughout this project — not lorem-ipsum filler. The full source textbook it's drawn from is kept out of this repo (copyright); regenerate the excerpt yourself via `python scripts/extract_sample_excerpt.py` if you have a copy of the source.

**Note if you're on a corporate network that intercepts TLS** (you'll see `pip install` fail with `CERTIFICATE_VERIFY_FAILED`): point pip at your organization's CA bundle, e.g. `pip install --cert /path/to/corporate-ca-bundle.pem -r requirements.txt`, or set it once via `pip config set global.cert /path/to/bundle.pem`. This is a local machine/network fix, not something the repo can ship — nothing here or in `.gitignore`d files depends on it.
