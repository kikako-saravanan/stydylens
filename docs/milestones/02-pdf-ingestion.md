# Milestone 2 — PDF Ingestion

## What problem are we solving?

A PDF on disk is an opaque binary blob — you can't ask it "what does page 5 say" without a parser. Every later stage (chunking, embeddings, citations) needs actual text, tagged with *which page it came from*.

## Why does this problem exist?

A PDF isn't fundamentally a text format — it's a **page-layout format**. Internally it stores instructions like "draw glyph 'T' at coordinate (120, 480) in font Helvetica-12," page by page, in compressed streams. There's no built-in concept of "paragraph" — just positioned glyphs. Reconstructing readable text means a parser walks the drawing instructions, groups nearby glyphs back into words/lines, and tracks which page it was looking at.

## First principles

```
Binary PDF (compressed drawing instructions, page by page)
        |
   need a parser that understands PDF's internal structure
        |
   walk page-by-page, reconstruct glyphs -> words -> text
        |
   critically: remember WHICH page each piece of text came from
   (every later citation depends on this one piece of metadata)
        |
   page-aware document: { source filename, page number, page text }
```

## What we implemented, where

- `backend/app/ingestion/pdf_loader.py` — `PageDocument` (`source`, `page`, `text`) and `extract_pages()`, using `pdfplumber` to open a PDF and yield one `PageDocument` per page with text.
- `backend/app/main.py` — `POST /api/upload`: saves the file to `data/uploads/` (gitignored, runtime-only), runs `extract_pages()`, prints every page's length + preview to console, returns a JSON summary.
- `data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf` — the real test document: pages 267-290 (Chapter 5: CPU Scheduling) of Silberschatz's *Operating System Concepts*, 10th ed., cut via `scripts/extract_sample_excerpt.py`. The full copyrighted textbook stays local-only (`.gitignore`); only this small excerpt is committed, alongside `data/sample_pdfs/SOURCE.md` documenting exactly where it came from.

## Code walkthrough

```python
for page_number, page in enumerate(pdf.pages, start=1):
    text = (page.extract_text() or "").strip()
    if text:
        pages.append(PageDocument(source=source, page=page_number, text=text))
```

- **`start=1`, not 0**: page numbers must match what a student sees in their PDF viewer. Citing "page 0" would be actively wrong.
- **`page.extract_text() or ""`**: `extract_text()` returns `None` for pages with no extractable text (e.g. pure-image scans). Without `or ""`, `.strip()` on `None` crashes the whole upload on the first such page.
- **`if text:` filters blank pages** — a title slide has nothing to retrieve; keeping it as an empty chunk would be dead weight with no citation value.

**Why `pdfplumber` over `PyPDFLoader` (LangChain)**, both allowed by the assignment: deliberately avoiding the full LangChain dependency until Milestone 6, when its chain-composition machinery is actually needed. `pdfplumber` gives direct page access with nothing else attached.

## What happened at runtime (real example)

```
curl -F "file=@data/sample_pdfs/os-concepts-ch5-cpu-scheduling-excerpt.pdf" http://127.0.0.1:8000/api/upload
```
```json
{"filename":"os-concepts-ch5-cpu-scheduling-excerpt.pdf","page_count":24,
 "pages":[{"page":1,"char_count":1415}, {"page":2,"char_count":1709}, ...]}
```
Console:
```
[ingestion] os-concepts-ch5-cpu-scheduling-excerpt.pdf: 24 pages with extractable text
  page 1: 1415 chars — '200 Chapter5 CPUScheduling 5.1 Basic Concepts InasystemwithasingleCPUcore,onlyon'
```
Note `page`/`source` refer to *this excerpt file's own* pages (1-24), not the original textbook's page 267 — a citation must point to a page the student can actually open in the document they uploaded.

## What can go wrong

- **Squished words** — `'200Chapter5CPUScheduling'` in the real output: `pdfplumber`'s text extraction lost spaces in places, due to font-encoding/kerning quirks. Cosmetic to a human, but a real source of tokenization noise for retrieval later.
- **Scanned/image-only pages** — `extract_text()` returns `None`, silently dropped by our filter. A scanned slide deck would silently lose entire pages; OCR is out of scope for Phase 1.
- **Multi-column layouts** can interleave text from both columns out of reading order.
- **Synchronous parsing inside an `async def` route** — blocks the entire event loop while parsing; fine for one 24-page PDF, a real scaling limit for large uploads.

## Self-check questions

1. Why number pages `1..24` for the excerpt file itself, rather than preserving the original textbook's page numbers (267-290)?
2. A student uploads a scanned (image-only) slide deck. What does `extract_pages()` return, and what does that mean for answering questions about that lecture?
3. Why does `PageDocument` need a `source` field at all, given a single upload already "knows" which file it came from?

<details><summary>Answers</summary>

1. `PageDocument.page` must represent the page number in the document StudyLens actually received and that a student can open — not a page number from wherever that document originally came from.
2. `extract_pages()` returns an empty list (or drops those pages) — the text is visually present to a human but not machine-readable. StudyLens would have zero evidence for that lecture and should honestly say "not found" rather than guess.
3. Once a student uploads *multiple* course PDFs, "page 5" alone is ambiguous. `(source, page)` together is the composite key that makes a citation resolvable to one exact location.
</details>
