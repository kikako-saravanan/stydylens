# Milestone 3 — Chunking

## What problem are we solving?

A `PageDocument` can hold a whole page of text as one blob. An embedding model compresses whatever text it's given into a *single* vector — if a page mixes two unrelated ideas, that vector is a blurred average of both, useless for pinpointing either. We need smaller, single-topic-ish units — **chunks** — each with its own embedding.

## Why does this problem exist?

Same signal-to-noise problem as Milestone 0, at the sub-page level: retrieval quality depends on units small enough to be about *one thing*. Too large dilutes the vector with irrelevant content; too small loses the surrounding context a concept needs to make sense standalone.

## First principles

```
Page text (a few hundred to a few thousand words, possibly several topics)
        |
   need units small enough to be topically coherent,
   large enough to carry full context for one idea
        |
   split into overlapping windows of ~500-800 tokens
        |
   why OVERLAP: hard, non-overlapping cuts tear a concept whose
   explanation straddles the cut point in half — neither resulting
   chunk contains the whole idea
        |
   overlap = each chunk repeats the tail of the previous chunk, so a
   boundary-spanning concept appears WHOLE in at least one chunk
```

## What we implemented, where

- `backend/app/chunking/chunker.py` — `Chunk` (`chunk_id`, `source`, `page`, `text`), `chunk_text()` (sliding-window splitter), `chunk_pages()` (applies it per page).
- `backend/app/main.py` — `/api/upload` chunks every extracted page; response and console log include chunk metadata.
- `.env.example` — `CHUNK_TARGET_TOKENS` (650), `CHUNK_OVERLAP_RATIO` (0.125), tunable without code changes.

## Code walkthrough

*Chunking never crosses a page boundary* (`chunk_pages()` calls `chunk_text()` per `PageDocument`). Deliberate trade-off: every chunk gets exactly one unambiguous page number, directly satisfying "every citation is verifiable by opening the cited page." Cost: a sentence genuinely straddling a page break in the source PDF can't be stitched back together.

*Token counting is an approximation, and the code says so.* `TOKENS_PER_WORD = 1.3` is a rough heuristic — real tokenizers split some words into sub-word pieces. Measuring in **words**, not characters, guarantees the sliding window only cuts *between* words, never mid-word (`"schedul"` + `"ing"` as two chunk-halves would actively hurt embedding quality).

```python
words_per_chunk = max(1, round(target_tokens / TOKENS_PER_WORD))
overlap_words = int(words_per_chunk * overlap_ratio)
step = max(1, words_per_chunk - overlap_words)
```
A plain sliding window: each chunk is `words_per_chunk` words; the next chunk starts `step` words later (not `words_per_chunk` words later) — that gap of `overlap_words` is the repeated region.

## Why this design vs. alternatives

LangChain's `RecursiveCharacterTextSplitter` tries paragraph breaks first, then sentences, then words. We chose a simpler plain word-sliding-window: fully transparent, easy to verify by hand, avoids LangChain a milestone early, and already solves the one failure mode that would visibly hurt quality (mid-word cuts). Paragraph-aware splitting is a legitimate future improvement if retrieval-quality testing shows it's needed.

## What happened at runtime — and an honest surprise

At the default `CHUNK_TARGET_TOKENS=650` (-> 500 words/chunk), the real excerpt produced **exactly one chunk per page, 24 chunks from 24 pages** — every page (200-560 words) is shorter than 500 words. Not a bug: chunking only *does* something once a page exceeds the target size.

To actually verify the multi-chunk-and-overlap logic, `chunk_text()` was run directly against page 3 (281 words) with `target_tokens=150`:
```
words_per_chunk=115, overlap_words=14
chunk 0: words[0:115]
chunk 1: words[101:216]
chunk 2: words[202:281]

c0 last 14 words:  ['can', 'result', 'in', 'race', 'conditions', ..., 'Consider', 'the']
c1 first 14 words: ['can', 'result', 'in', 'race', 'conditions', ..., 'Consider', 'the']
exact match: True
```
Word-for-word exact match — not just "looks plausible."

## What can go wrong

- **Target size mismatched to the document** silently produces degenerate behavior (as above) — check `chunk_count` vs `page_count`, don't assume the config is right.
- **Overlap too high** wastes storage/compute and can crowd out genuinely distinct top-k results with near-duplicates at query time.
- **Overlap too low/zero** recreates the boundary-tearing failure overlap exists to prevent.
- The squished-word artifact from Milestone 2 means `text.split()` sometimes treats 2-3 words as one long word — minor tokenization noise worth remembering.

## Self-check questions

1. Why chunk per page instead of concatenating the whole document and chunking across the concatenated whole? Gain/loss of switching?
2. With `CHUNK_OVERLAP_RATIO=0`, what exactly changes in the page-3/`target_tokens=150` example above, and what failure mode does it recreate?
3. Why does `chunk_id` (`{source}::p{page}::c{index}`) encode the source filename instead of a running global counter?

<details><summary>Answers</summary>

1. Per-page chunking guarantees every chunk has one unambiguous page number, making citations directly verifiable. Chunking the whole concatenated document could preserve context across page boundaries, at the cost of needing richer multi-page provenance metadata per chunk.
2. `overlap_words=0`, so `step=115=words_per_chunk`: chunks become exactly contiguous — `words[0:115]`, `words[115:230]`, `words[230:281]` — zero shared words at any boundary. The "can result in race conditions..." sentence that previously appeared whole in both chunk 0 and chunk 1 would now have its first half in chunk 0 and second half in chunk 1, with neither chunk containing the complete thought — exactly the boundary-tearing failure overlap prevents.
3. A global counter is unique but communicates nothing. `os-concepts.pdf::p12::c2` is unique *and* immediately tells you source, page, and position — directly useful for retrieval debugging and evidence tracing.
</details>
