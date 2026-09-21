"""Milestone 4 verification: does semantic similarity actually work on our
real document, without keyword overlap doing the work?

Embeds every chunk of the sample PDF, then for each test query prints the
top-3 most similar chunks by cosine similarity (a plain dot product, since
embeddings are L2-normalized).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.chunking.chunker import chunk_pages
from app.embeddings.embedder import embed_texts
from app.ingestion.pdf_loader import extract_pages

PDF_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "sample_pdfs" / "os-concepts-ch5-cpu-scheduling-excerpt.pdf"
)

QUERIES = [
    # Same meaning as the text, deliberately different words (no "CPU",
    # "scheduling", or "algorithm" overlap with how the book phrases it)
    "How does the operating system pick which task runs next?",
    # A specific named concept that should match a specific chunk
    "round robin scheduling",
    # Completely out of domain — should score low everywhere
    "How do plants convert sunlight into energy through photosynthesis?",
]


def main() -> None:
    pages = extract_pages(PDF_PATH)
    chunks = chunk_pages(pages)
    print(f"Embedding {len(chunks)} chunks from {PDF_PATH.name}...")
    chunk_embeddings = embed_texts([c.text for c in chunks])

    for query in QUERIES:
        query_embedding = embed_texts([query])[0]
        # cosine similarity == dot product, because both sides are unit-length
        scores = chunk_embeddings @ query_embedding
        top_idx = np.argsort(scores)[::-1][:3]

        print(f"\n=== Query: {query!r} ===")
        for rank, i in enumerate(top_idx, start=1):
            c = chunks[i]
            preview = c.text[:100].replace("\n", " ")
            print(f"  #{rank} score={scores[i]:.4f} page={c.page} — {preview!r}")


if __name__ == "__main__":
    main()
