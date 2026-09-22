# Milestone 5 — FAISS Retrieval

## What problem are we solving?

We can embed a question and embed a chunk, and compare them with a dot product. But a real course could have hundreds or thousands of chunks across multiple PDFs. Comparing a query against every single chunk vector by hand (as the Milestone 4 demo script did, in a Python loop) works at 24 chunks; it needs to be systematic, persistent, and fast at scale.

## Why does this problem exist?

Two separate needs appear once embeddings are real:
1. **Persistence** — embeddings are expensive-ish to compute (running the model). Recomputing every chunk's embedding on every server restart, for every query, would be wasteful and slow. We need to embed once and store the result.
2. **Search** — "find the top-k closest vectors to this query vector" is a distinct operation from "compute one similarity score." At small scale it's just a loop and a sort; at scale it needs a data structure built for exactly this. FAISS (Facebook AI Similarity Search) is a library purpose-built for fast nearest-neighbor search over vector collections.

## First principles

```
Many chunks, each with a 384-dim vector
        |
   need: given a query vector, find the k vectors most similar to it,
   without linearly comparing against every single one by hand each time
        |
   a VECTOR INDEX is a data structure organized specifically for this
   "find nearest neighbors" operation
        |
   FAISS's IndexFlatIP: the simplest possible index -- it still compares
   the query against every stored vector (a full/"flat" scan), but does
   it as a single optimized batched matrix multiply in C++, not a Python
   loop -- correct and fast enough at the scale of one course's worth
   of chunks (hundreds to low thousands)
        |
   FAISS only stores VECTORS and their integer position -- it has no
   concept of "page 12" or "source filename" -- so we keep a PARALLEL
   metadata list, position-for-position, alongside the index
```

`IndexFlatIP` ("IP" = inner product) was chosen specifically because our embeddings are already L2-normalized (Milestone 4) — inner product on unit vectors *is* cosine similarity, with no extra math needed. The alternative, `IndexFlatL2`, compares by Euclidean distance instead; for normalized vectors the two produce the same *ranking* (closer in angle also means closer in Euclidean distance on the unit sphere), but inner product directly matches how we already reasoned about "similarity" in Milestone 4, so we kept the two consistent.

"Flat" here means no approximation — every query is compared against every stored vector, guaranteeing exact results. FAISS also offers approximate indexes (e.g. `IndexIVFFlat`, `IndexHNSW`) that trade a small amount of accuracy for much better speed at millions of vectors — irrelevant at this project's scale (a handful of course PDFs), so `IndexFlatIP` is the right, simplest choice, not a placeholder for something fancier.

## What we implemented, where

- `backend/app/retrieval/faiss_store.py`:
  - `add_chunks(chunks)` — embeds a list of `Chunk`s, adds their vectors to the FAISS index, appends parallel metadata, persists both to disk.
  - `query_index(question, k)` — embeds the question, searches the index, returns the top-k chunks with scores.
  - `count()` — total chunks currently indexed.
  - Persistence: `data/index/faiss.index` (FAISS's own binary format via `faiss.write_index`/`read_index`) and `data/index/metadata.json` (a plain list, position `i` describing the vector at FAISS position `i`).
- `backend/app/main.py` — `/api/upload` now calls `add_chunks()` instead of just computing embeddings and discarding them; a new `POST /api/query` endpoint accepts `{"question": str, "k": int}` and returns ranked results with scores and snippets.

## Code walkthrough

```python
def _load() -> None:
    global _index, _metadata
    if INDEX_PATH.exists() and METADATA_PATH.exists():
        _index = faiss.read_index(str(INDEX_PATH))
        _metadata = json.loads(METADATA_PATH.read_text())
    else:
        _index = faiss.IndexFlatIP(EMBEDDING_DIM)
        _metadata = []
```
Lazy singleton loading, same pattern as the embedding model in Milestone 4: load once, reuse across requests, persist changes back to disk immediately after every write (`_persist()`), so a server crash right after an upload doesn't silently lose that upload's chunks from the next server start.

```python
scores, indices = _index.search(query_vector, k)
results = [{**_metadata[idx], "score": float(score)} for score, idx in zip(scores[0], indices[0])]
```
`_index.search()` is FAISS's actual nearest-neighbor search — it returns parallel arrays of scores and positions. `_metadata[idx]` is the lookup that turns "this is vector position 14" back into "this is `os-concepts.pdf`, page 15" — the whole reason the metadata list is kept in lockstep with the index.

A `threading.Lock()` guards all reads/writes to the module-level `_index`/`_metadata` — FastAPI can handle concurrent requests, and without a lock, two uploads arriving at the same instant could corrupt the in-memory state (e.g. both reading the same `ntotal` before either writes, silently dropping one upload's chunks).

## Why this design vs. alternatives

A production system serving millions of chunks would want an approximate index (`IndexIVFFlat` + a trained quantizer) for speed, and likely a real database (Postgres+pgvector, or a dedicated vector DB) instead of a flat file for metadata, to support concurrent writers safely and query filtering. For this assignment's scale (one to a few course PDFs, dev-stage, single process), `IndexFlatIP` + a JSON sidecar file is honestly simpler, fully exact (no approximation-related recall loss to explain away), and easy to reason about end to end — appropriate scope, not a corner cut.

## What happened at runtime — real numbers

Uploading the sample PDF, then querying live via the API (not the standalone script):

```
POST /api/query {"question": "How does round robin scheduling work?", "k": 3}
  #1 score=0.4408 page=16
  #2 score=0.4404 page=10
  #3 score=0.4357 page=15  <- the actual round-robin section

POST /api/query {"question": "How does the operating system pick which task runs next?", "k": 3}
  #1 score=0.5148 page=1   <- exact match to Milestone 4's brute-force demo
  #2 score=0.4898 page=7
  #3 score=0.4828 page=19
```
The second query's scores are *identical* (0.5148, 0.4898, 0.4828) to Milestone 4's manual numpy dot-product demo — strong evidence FAISS is doing exactly the same math, correctly, via the library instead of by hand.

**Persistence test**: killed the server, restarted it *without* re-uploading, ran the same query — identical scores came back, confirming the index survives a restart via the files on disk, not just in-memory state.

**A real, honest limitation found by testing, not assumed**: uploading the *same* PDF twice took `index_total_chunks` from 24 to 48 — there is no deduplication by filename. Re-uploading the same document doubles its presence in the index (and would double-count it in retrieval, since both copies would independently score high). This is a known gap, not silently hidden: production would need a "delete existing chunks for this filename before re-adding" step, out of scope for Phase 1 but worth stating plainly in the README's limitations section.

## What can go wrong

- **No deduplication** (above) — re-uploading a document silently bloats the index with duplicates.
- **No delete/update path** — there's currently no way to remove a document's chunks from the index once added, short of deleting the index files and re-uploading everything.
- **In-memory index doesn't scale across multiple server processes** — if this were deployed with multiple worker processes (e.g. `uvicorn --workers 4`), each process would have its own in-memory `_index`, and writes in one process wouldn't be visible to others until they reload from disk. Fine for a single-process dev/demo deployment; a real concern for horizontal scaling.
- **`IndexFlatIP` is O(n) per query** — exact but linear in the number of stored vectors. Fine at hundreds-to-thousands of chunks (a few courses' worth); would need an approximate index at a much larger scale.

## Self-check questions

1. Why does FAISS need a separate, parallel metadata list instead of just storing `{"page": 12, "source": "...", "text": "..."}` directly alongside each vector inside the index itself?
2. Why was `IndexFlatIP` chosen over `IndexFlatL2`, given both are "exact, no-approximation" index types?
3. The duplicate-upload test showed the index growing from 24 to 48 chunks with no error. Was this the *correct* behavior for `add_chunks()` given how it's currently written, or a bug? What would need to change to prevent it, and what would that fix cost elsewhere (e.g. re-uploading a corrected version of the same file)?

<details><summary>Answers</summary>

1. FAISS is a specialized, low-level vector-math library — it only understands fixed-size numeric arrays and integer positions internally, not arbitrary structured data like strings or nested objects. Keeping metadata as a separate, position-aligned list lets FAISS do only what it's good at (fast nearest-neighbor math) while ordinary Python/JSON handles the human-meaningful data.
2. Both give the same *ranking* on L2-normalized vectors (closer in angle correlates with closer in Euclidean distance on the unit sphere), but inner product directly matches the cosine-similarity reasoning already established in Milestone 4 with zero extra transformation — using `IndexFlatL2` would work but would be introducing a second, less-directly-connected mental model for no benefit.
3. Correct behavior *for the code as written* — `add_chunks()` has no logic to check "have I seen this source filename before," so it does exactly what it's implemented to do: append. It's a real product gap, not a crash-level bug. Fixing it would mean, before adding new chunks, finding and removing any existing metadata entries (and their corresponding FAISS vectors) with the same `source`, then adding the new ones — FAISS's flat index doesn't support in-place deletion by ID directly, so this would likely mean rebuilding the index from the filtered metadata list. The cost: re-uploading a corrected version of a document becomes a full index rebuild rather than a cheap append, which matters much more at a larger scale than this project's.
</details>
