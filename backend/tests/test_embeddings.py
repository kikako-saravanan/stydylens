"""Unit test: real embedding model, real vectors, real cosine similarity.

No mocking -- the actual sentence-transformers model runs. This is a
formalized version of the Milestone 4 semantic-similarity demo. See
docs/milestones/04-embeddings.md.
"""

import numpy as np

from app.embeddings.embedder import embed_texts


def test_embeddings_have_correct_dimension():
    vectors = embed_texts(["hello world"])
    assert vectors.shape == (1, 384)


def test_embeddings_are_l2_normalized():
    vectors = embed_texts(["a completely arbitrary sentence about scheduling"])
    norm = np.linalg.norm(vectors[0])
    assert abs(norm - 1.0) < 1e-5


def test_semantically_similar_text_scores_higher_than_unrelated_text():
    query = embed_texts(["How does the operating system pick which task runs next?"])[0]
    related = embed_texts(
        ["The CPU scheduler selects a process from the ready queue and allocates the CPU to it."]
    )[0]
    unrelated = embed_texts(
        ["Plants convert sunlight into chemical energy through photosynthesis."]
    )[0]

    related_score = float(query @ related)
    unrelated_score = float(query @ unrelated)
    assert related_score > unrelated_score
