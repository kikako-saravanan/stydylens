# Milestone 10 — Source Attribution

## What problem are we solving?

A grounded answer is worth little to a student if they can't check it. If StudyLens says "round-robin uses a time quantum of 10-100ms" and the student has no way to find *where* that claim comes from, they're back to trusting an AI's unverified word — the exact problem RAG exists to avoid. Every answer needs to point at exactly which page(s) of which document it came from.

## Why does this problem exist, and why is it mostly already solved?

This milestone is unusual: by the time Milestones 2 through 8 were built, source attribution was already a forced design decision, not something bolted on afterward. Every stage was built to carry `(source, page)` metadata forward specifically *because* later stages would need it — this milestone is where that design pays off, and where it gets verified end to end rather than assumed.

## The complete data lineage, traced through real code

```
PDF file
   |
extract_pages() [ingestion/pdf_loader.py, Milestone 2]
   -> PageDocument(source=filename, page=1-indexed page number, text=...)
   |
chunk_pages() [chunking/chunker.py, Milestone 3]
   -> Chunk(chunk_id=f"{source}::p{page}::c{i}", source, page, text)
      NEVER crosses a page boundary -- every chunk has exactly ONE page
   |
add_chunks() [retrieval/faiss_store.py, Milestone 5]
   -> embeds each chunk's text, adds the VECTOR to FAISS,
      appends {chunk_id, source, page, text} to a position-aligned
      metadata sidecar (FAISS itself has no concept of "page" --
      this sidecar is what makes vector position N mean anything)
   |
query_index() [retrieval/faiss_store.py]
   -> returns {chunk_id, source, page, text, score} per hit --
      metadata riding along with every retrieval result
   |
rerank() [rerank/reranker.py, Milestone 8]
   -> re-scores the SAME dicts, adding "rerank_score" --
      never drops or reconstructs chunk_id/source/page/text
   |
answer_question() [rag/chain.py, Milestone 6+10]
   -> the reranked chunks become BOTH:
        (a) the LLM's context (via format_context())
        (b) the response's "sources" array
      -- the same data, used two ways, never regenerated from the
         LLM's output text
```

The critical property this traces: **citations are never parsed out of the LLM's answer.** The LLM never gets asked "which sources did you use" — StudyLens already knows, deterministically, exactly which chunks it fed into the prompt. This was a design decision made back in Milestone 6, explicitly to avoid trusting an LLM's self-report of its own sourcing (which can be inaccurate, since LLMs don't have privileged introspective access to which specific tokens in their input most influenced a given output).

## What we implemented, where (this milestone specifically)

- `backend/app/rag/chain.py` — `make_snippet(text, max_len=200)`: truncates a chunk's text for the `sources` response field at the **last word boundary before the limit**, not an arbitrary character cutoff. Applied in both `answer_question()`'s `sources` and `/api/query`'s `results`.

Before this fix, a snippet could end `"...schedulingdependson"` (an actual observed example, split mid-sentence at exactly character 200). After: `"...schedulingdependson observed…"` — a cleaner fragment, still an exact substring of the real page text (so it remains directly matchable against the source page), just not severed at an arbitrary byte offset.

## How we verified it — an actual independent check, not just re-reading the code

To directly test the assignment's own grading question — "is every citation-to-source claim verifiable by opening the cited page" — `pdfplumber` was used *independently* (outside the app's own code path) to open `os-concepts-ch5-cpu-scheduling-excerpt.pdf` and extract page 11's raw text directly:

```
=== Actual page 11 text (first 400 chars), read directly with pdfplumber ===
210 Chapter5 CPUScheduling
TheCPUschedulerpicksthefirstprocessfromthereadyqueue,setsatimerto
interruptafter1timequantum,anddispatchestheprocess. ...
```

This was then compared against a real `/api/ask` response's cited snippet for `os-concepts-ch5-cpu-scheduling-excerpt.pdf::p11::c0` — an exact character-for-character match. This is meaningfully different from "the code looks like it should produce correct citations" — it's an outside-in check that opened the actual file and confirmed the actual claim.

## What can go wrong

- **A citation's page number is only as correct as `pdfplumber`'s own page indexing** — if the PDF library itself misattributes text to the wrong page (rare, but possible with unusual PDF structures), that error would propagate all the way through as a wrong-but-confident citation. Not observed in this document, but a real, structural dependency worth naming.
- **Snippets are still just the first ~200 characters of a chunk**, not necessarily the exact sentence that most directly supports the answer's specific claim. A chunk can be ~400-700 tokens; the cited snippet is a preview of it, not a pinpointed quote. A reviewer verifying a citation needs to read the whole cited chunk (or open the page), not just trust the 200-character preview alone.
- **The squished-word artifact from Milestone 2** (`"schedulingdependson"`) is preserved faithfully into citations too — an honest byproduct of citing real extracted text exactly as extracted, rather than a cleaned-up paraphrase that would technically no longer be a direct quote.

## Self-check questions

1. Why does `answer_question()` build the `sources` array from the same `reranked_chunks` list used for `format_context()`, instead of, say, asking the LLM in a follow-up call which sources it used?
2. `chunk_id` is built as `f"{source}::p{page}::c{i}"`. Given that `source` and `page` are already separate fields in the citation dict, why does encoding them redundantly into `chunk_id` still add value?
3. The independent `pdfplumber` verification check in this milestone re-extracted page 11 using the exact same library (`pdfplumber`) the app itself uses internally. Does that weaken the verification (since a bug in `pdfplumber` itself could affect both the app and the check identically)? What would a stronger, fully independent check look like?

<details><summary>Answers</summary>

1. Asking the LLM to self-report its sources is unreliable — an LLM doesn't have precise introspective access to which specific input tokens most influenced its output, so a self-reported citation could be plausible-sounding but wrong (citing a source that wasn't actually the basis for a claim, or missing one that was). Since `answer_question()` already knows, as plain data, exactly which chunks were placed in the prompt, building citations from that data is strictly more reliable than trusting a second LLM call to remember and accurately report it.
2. Redundancy here serves debuggability, not correctness — `chunk_id` alone (e.g., in a log line, or a `retrieval_trace` chunk-id list, both of which appear without the full citation dict alongside them) is self-describing: you can read `source` and `page` directly off the ID string without needing to cross-reference back to a separate metadata record. It's a convenience for exactly the situations (logs, traces) where only the ID travels, not the full dict.
3. Fair concern — this check does share `pdfplumber` as a common dependency with the app itself, so it wouldn't catch a `pdfplumber`-specific misparse affecting both identically. A fully independent check would use a *different* tool entirely (e.g., opening the PDF in a different library, or a human visually opening the actual PDF file in a viewer like Preview/Adobe and reading page 11 with their own eyes) to rule out a shared-dependency blind spot. The check performed here does still meaningfully verify the app's own internal *data flow* is correct (that the citation's page number and text genuinely correspond to what `pdfplumber` extracts for that page) — it just doesn't independently verify `pdfplumber`'s own extraction accuracy against the PDF's ground truth.
</details>
