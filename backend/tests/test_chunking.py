"""Unit test: chunk metadata correctness and the overlap math, formalized
as real assertions (Milestone 3 verified this by hand against real output;
this test makes that verification repeatable). See
docs/milestones/03-chunking.md.
"""

from app.chunking.chunker import Chunk, chunk_pages, chunk_text
from app.ingestion.pdf_loader import PageDocument


def test_chunk_id_encodes_source_page_and_index():
    page = PageDocument(source="lecture.pdf", page=7, text="word " * 1000)
    chunks = chunk_pages([page], target_tokens=150, overlap_ratio=0.125)
    assert len(chunks) > 1, "expected this page to split into multiple chunks"
    for i, c in enumerate(chunks):
        assert isinstance(c, Chunk)
        assert c.chunk_id == f"lecture.pdf::p7::c{i}"
        assert c.source == "lecture.pdf"
        assert c.page == 7


def test_chunks_never_cross_a_page_boundary():
    pages = [
        PageDocument(source="doc.pdf", page=1, text="alpha " * 50),
        PageDocument(source="doc.pdf", page=2, text="beta " * 50),
    ]
    chunks = chunk_pages(pages)
    for c in chunks:
        # every chunk's text must come entirely from ONE page's source text
        assert ("alpha" in c.text) != ("beta" in c.text)


def test_overlap_is_word_for_word_exact():
    text = " ".join(f"word{i}" for i in range(281))
    chunks = chunk_text(text, target_tokens=150, overlap_ratio=0.125)
    assert len(chunks) == 3

    words_per_chunk = round(150 / 1.3)  # 115
    overlap_words = int(words_per_chunk * 0.125)  # 14

    c0_words = chunks[0].split()
    c1_words = chunks[1].split()
    assert c0_words[-overlap_words:] == c1_words[:overlap_words]


def test_zero_overlap_produces_contiguous_non_overlapping_chunks():
    text = " ".join(f"word{i}" for i in range(281))
    chunks = chunk_text(text, target_tokens=150, overlap_ratio=0.0)
    all_words = " ".join(chunks).split()
    # with zero overlap, concatenating every chunk reproduces the original
    # word sequence exactly, with no word appearing twice across chunks.
    assert all_words == text.split()
