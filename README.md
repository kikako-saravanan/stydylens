# StudyLens

**Domain chosen (Phase 1 Problem Statement, option 2): Lecture Notes Q&A.**

Students upload course PDFs/slides and ask questions about the material. Answers are grounded in the uploaded documents, with page-level citations, and the assistant explicitly says so when an answer isn't in the material rather than guessing.

Architecture, tech stack, API reference, and evaluation results will be filled in as each stage is built (see `docs/`). This section is kept current after every milestone, not written at the end.

## Current status

- [x] Milestone 1: Backend scaffold + `/health`
- [x] Milestone 2: PDF ingestion
- [x] Milestone 3: Chunking
- [ ] Milestone 4: Embeddings
- [ ] Milestone 5: FAISS retrieval
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

### Sample document

`data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf` is a 24-page excerpt (see `data/sample_pdfs/SOURCE.md` for exact provenance) used as the realistic test document throughout this project — not lorem-ipsum filler. The full source textbook it's drawn from is kept out of this repo (copyright); regenerate the excerpt yourself via `python scripts/extract_sample_excerpt.py` if you have a copy of the source.

**Note if you're on a corporate network that intercepts TLS** (you'll see `pip install` fail with `CERTIFICATE_VERIFY_FAILED`): point pip at your organization's CA bundle, e.g. `pip install --cert /path/to/corporate-ca-bundle.pem -r requirements.txt`, or set it once via `pip config set global.cert /path/to/bundle.pem`. This is a local machine/network fix, not something the repo can ship — nothing here or in `.gitignore`d files depends on it.
