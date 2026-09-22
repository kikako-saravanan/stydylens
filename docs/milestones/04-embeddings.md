# Milestone 4 — Embeddings

## What problem are we solving?

We have text chunks with page numbers. "Does this chunk match the student's question" still isn't computable — comparing two pieces of text for *meaning* isn't something string operations can do. Text needs to become something we can do math on.

## Why does this problem exist?

"Working from home" and "context switching" can be about the same idea while sharing zero characters. Computers don't understand meaning natively — only numbers. The question is how to turn meaning into numbers such that similar meanings produce similar numbers.

## First principles

```
Text (words, sentences -- no inherent numeric structure)
        |
   need a representation where "similar meaning" implies
   "mathematically close" -- so we can compare with arithmetic
        |
   a neural network trained on massive text learns to map text to a
   point in high-dimensional space, such that text used in similar
   contexts ends up at nearby points
        |
   that point is a VECTOR -- a fixed-length list of numbers (384, here)
        |
   that vector is an EMBEDDING
        |
   "similar meaning" is now a geometry question: how close are two
   points in this 384-dimensional space?
```

The training signal: a model trained on huge amounts of real text (masked-word prediction, or contrastive learning on sentence pairs) implicitly learns that words/sentences appearing in similar contexts tend to mean similar things — that regularity becomes the geometry of the vector space, without hand-labeled "these mean the same" pairs.

## What we implemented, where

- `backend/app/embeddings/embedder.py` — `get_model()` (loads `sentence-transformers/all-MiniLM-L6-v2` once, `lru_cache`-cached singleton), `embed_texts()` (list of strings -> matrix of L2-normalized vectors).
- `backend/app/main.py` — model preloaded at server startup via FastAPI `lifespan`, not on the first request; `/api/upload` embeds every chunk.
- `scripts/embedding_similarity_demo.py` — real proof of semantic matching against the actual sample document.

## Code walkthrough

```python
@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)
```
`lru_cache(maxsize=1)` makes this a process-wide singleton — the ~90MB model loads exactly once, no matter how many requests call `get_model()`. Without it, every upload/query would reload the model from disk, adding seconds of avoidable latency per request.

```python
return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
```
`normalize_embeddings=True` rescales every vector to unit length. Cosine similarity is normally `(A·B)/(|A||B|)`; if `|A|=|B|=1`, that collapses to plain `A·B` — the cheapest possible vector operation, and exactly what FAISS's `IndexFlatIP` computes natively (setting this up now means Milestone 5 needs no extra normalization at query time).

## Why this model, why locally

`all-MiniLM-L6-v2` is small (90MB, 384 dims), runs on CPU in reasonable time, and needs no API key — the assignment wants local embeddings at zero cost, not a paid API. Trade-off: a larger model (or a paid embedding API) might capture subtler semantic distinctions, at the cost of money, network dependency, and latency. For a single-course-document assistant, this model's accuracy proved more than sufficient (see results below).

## What happened at runtime — real numbers, real document

```
Query: 'How does the operating system pick which task runs next?'
  (zero shared words with "CPU", "scheduling", "algorithm")
  #1 score=0.5148 page=1  -- the actual CPU-scheduling chapter opening
  #2 score=0.4898 page=7
  #3 score=0.4828 page=19

Query: 'round robin scheduling'
  #1 score=0.4626 page=15 -- the actual round-robin section
  #2 score=0.4281 page=16
  #3 score=0.4148 page=10

Query: 'How do plants convert sunlight into energy through photosynthesis?'
  #1 score=0.1404 page=20
  #2 score=0.1312 page=1
  #3 score=0.1108 page=14
```
The first two prove semantic matching works without keyword overlap. The third proves something equally important: when nothing relevant exists, scores collapse to a visibly lower range instead of confidently matching something wrong. This score gap is what a later "I don't know" threshold could be built on.

## What can go wrong

- **Cold-start latency** — mitigated by loading the model at startup, not on first use.
- **Similarity scores aren't probabilities** — 0.51 doesn't mean "51% confident"; it's a relative measure. What counts as "relevant enough" is an empirical threshold, decided once real retrieval is in place.
- **Domain mismatch** — a general-purpose model wasn't trained specifically on OS textbooks; it could occasionally misrank lexically-similar-but-unrelated chunks. No evidence of this yet, but a real limitation of an off-the-shelf model.
- **Fixed 384 dimensions** regardless of chunk length — a long, dense paragraph loses relatively more detail in that compression than a short chunk.

## Environment note (this machine specifically)

This network's security proxy blocks Hugging Face's newer "Xet" CDN (`*.cdn.hf.co`) with an explicit `Policy: URL Filtering` page — not an auth issue. Fix: set `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to the corporate CA bundle and `HF_HUB_DISABLE_XET=1`; retry if the first attempt fails (the block seemed intermittent). Once downloaded, the model is cached in `~/.cache/huggingface` and needs no further network access — `HF_HUB_OFFLINE=1` (see `.env.example`) skips even the metadata check on subsequent startups.

## Self-check questions

1. Why does `normalize_embeddings=True` specifically enable a dot product instead of the full cosine similarity formula — what part of the formula does normalization eliminate?
2. The out-of-domain photosynthesis query still scored 0.14, not 0.0. Why does unrelated text produce a nonzero similarity at all, rather than a fixed "no match" signal?
3. If `all-MiniLM-L6-v2` were swapped for a larger, more accurate embedding model with a different output dimension, what would have to change in the code? What wouldn't?

<details><summary>Answers</summary>

1. Cosine similarity is `(A·B)/(|A||B|)`. With both vectors normalized to length 1, `|A|=|B|=1`, so the division by `|A||B|` becomes division by 1 — the formula reduces to the numerator alone, `A·B`.
2. Embedding models don't produce a binary "related/unrelated" signal — every real sentence lands *somewhere* in the 384-dimensional space, and any two non-orthogonal vectors have some nonzero dot product just from shared, generic aspects of language (common function words, general sentence structure). Zero similarity would require genuinely orthogonal vectors, which unrelated-but-still-English sentences rarely are.
3. Must change: `EMBEDDING_DIM` in `faiss_store.py` (the FAISS index is built for a fixed vector size) and any already-persisted index/metadata would need to be rebuilt from scratch (old vectors and new vectors from different models are not comparable). Wouldn't need to change: `embed_texts()`'s interface (still takes texts, returns normalized vectors), `chunk_pages()`, or anything upstream of embedding — the model is swapped via `EMBEDDING_MODEL` env var, not code.
</details>
