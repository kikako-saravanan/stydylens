import os
from dataclasses import dataclass

from app.ingestion.pdf_loader import PageDocument

# ~4 characters/token and ~1.3 tokens/word are common rough heuristics for
# English text under a subword tokenizer (real subword tokenizers split
# longer/rarer words into multiple pieces). We use words/token here because
# splitting on word boundaries — never mid-word — is simple to guarantee.
# This is an approximation: Milestone 4 introduces the actual embedding
# model's tokenizer, which is the real source of truth for token counts.
TOKENS_PER_WORD = 1.3

DEFAULT_TARGET_TOKENS = int(os.getenv("CHUNK_TARGET_TOKENS", "650"))
DEFAULT_OVERLAP_RATIO = float(os.getenv("CHUNK_OVERLAP_RATIO", "0.125"))


@dataclass
class Chunk:
    chunk_id: str
    source: str
    page: int
    text: str


def chunk_text(
    text: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    """Split text into overlapping, word-boundary-safe chunks.

    A sliding window over words (not characters): each chunk is
    `words_per_chunk` words long, and consecutive chunks share
    `overlap_words` words at the boundary so a concept split across
    a chunk edge still appears whole in at least one chunk.
    """
    words = text.split()
    if not words:
        return []

    words_per_chunk = max(1, round(target_tokens / TOKENS_PER_WORD))
    overlap_words = int(words_per_chunk * overlap_ratio)
    step = max(1, words_per_chunk - overlap_words)

    chunks = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += step
    return chunks


def chunk_pages(
    pages: list[PageDocument],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[Chunk]:
    """Chunk each page independently — chunks never cross a page boundary.

    This keeps every chunk's citation unambiguous (exactly one page number),
    at the cost of occasionally losing context that flows across a page
    break (e.g. a sentence starting on page 3 and finishing on page 4).
    """
    chunks: list[Chunk] = []
    for page_doc in pages:
        page_chunks = chunk_text(page_doc.text, target_tokens, overlap_ratio)
        for i, chunk_text_value in enumerate(page_chunks):
            chunks.append(
                Chunk(
                    chunk_id=f"{page_doc.source}::p{page_doc.page}::c{i}",
                    source=page_doc.source,
                    page=page_doc.page,
                    text=chunk_text_value,
                )
            )
    return chunks
