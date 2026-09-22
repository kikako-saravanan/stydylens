"""Unit test: real PDF extraction against the real committed sample PDF.

No mocking here -- pdfplumber runs for real against a real file. This is
the "does the ingestion pipeline actually work" test, not a simulation
of one. See docs/milestones/02-pdf-ingestion.md.
"""

from app.ingestion.pdf_loader import extract_pages


def test_extract_pages_returns_all_24_pages(sample_pdf_path):
    pages = extract_pages(sample_pdf_path)
    assert len(pages) == 24


def test_page_numbers_are_1_indexed_and_sequential(sample_pdf_path):
    pages = extract_pages(sample_pdf_path)
    assert [p.page for p in pages] == list(range(1, 25))


def test_source_filename_is_tagged_on_every_page(sample_pdf_path):
    pages = extract_pages(sample_pdf_path)
    assert all(p.source == sample_pdf_path.name for p in pages)


def test_page_text_is_real_and_nonempty(sample_pdf_path):
    pages = extract_pages(sample_pdf_path)
    # Real content check, not just "some string exists" -- page 1 should
    # actually contain the chapter's real opening material.
    assert "CPU" in pages[0].text
    assert all(len(p.text) > 0 for p in pages)
