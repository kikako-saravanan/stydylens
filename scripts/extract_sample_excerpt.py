"""Build the committed demo fixture from a locally-held source textbook.

We don't commit full copyrighted textbooks to this public repo. Instead,
this script cuts a small, self-contained page range out of a source PDF
(kept locally, gitignored) and writes it as a standalone PDF small enough
to commit as a realistic test/demo document.

Usage:
    python scripts/extract_sample_excerpt.py

Edit SOURCE / PAGE_RANGE / OUTPUT below to change what gets extracted.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_pdfs"

SOURCE = DATA_DIR / "Abraham-Silberschatz-Operating-System-Concepts-10th-2018.pdf"
# 1-indexed, inclusive, matching the PDF's own page numbers (not the printed
# in-book page numbers, which differ due to front matter).
PAGE_RANGE = (267, 290)
OUTPUT = DATA_DIR / "os-concepts-ch5-cpu-scheduling-excerpt.pdf"


def main() -> None:
    reader = PdfReader(SOURCE)
    writer = PdfWriter()

    start, end = PAGE_RANGE
    for page_number in range(start - 1, end):  # pypdf pages are 0-indexed
        writer.add_page(reader.pages[page_number])

    with OUTPUT.open("wb") as f:
        writer.write(f)

    print(f"Wrote {OUTPUT.name}: pages {start}-{end} ({end - start + 1} pages) from {SOURCE.name}")


if __name__ == "__main__":
    main()
