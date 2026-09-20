# StudyLens

**Domain chosen (Phase 1 Problem Statement, option 2): Lecture Notes Q&A.**

Students upload course PDFs/slides and ask questions about the material. Answers are grounded in the uploaded documents, with page-level citations, and the assistant explicitly says so when an answer isn't in the material rather than guessing.

Architecture, tech stack, API reference, and evaluation results will be filled in as each stage is built (see `docs/`). This section is kept current after every milestone, not written at the end.

## Current status

- [x] Milestone 1: Backend scaffold + `/health`
- [ ] Milestone 2: PDF ingestion
- [ ] Milestone 3: Chunking
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

**Note if you're on a corporate network that intercepts TLS** (you'll see `pip install` fail with `CERTIFICATE_VERIFY_FAILED`): point pip at your organization's CA bundle, e.g. `pip install --cert /path/to/corporate-ca-bundle.pem -r requirements.txt`, or set it once via `pip config set global.cert /path/to/bundle.pem`. This is a local machine/network fix, not something the repo can ship — nothing here or in `.gitignore`d files depends on it.
