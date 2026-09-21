from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PageDocument:
    source: str
    page: int
    text: str


def extract_pages(pdf_path: str | Path, source: str | None = None) -> list[PageDocument]:
    """Extract text from a PDF, one PageDocument per non-blank page.

    Page numbers are 1-indexed to match what a human sees when opening
    the PDF (page 1, not page 0) — citations must point to a page number
    a student can actually find by opening the file.
    """
    pdf_path = Path(pdf_path)
    source = source or pdf_path.name

    pages: list[PageDocument] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(PageDocument(source=source, page=page_number, text=text))
    return pages
