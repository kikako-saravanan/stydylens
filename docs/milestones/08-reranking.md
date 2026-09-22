# Milestone 8 — Re-ranking

## What problem are we solving?

FAISS retrieval (Milestone 5) is fast because it compares two vectors that were each computed *independently* — the question never "sees" a specific chunk, and a chunk's vector never "sees" the question. That independence is exactly what makes precomputing chunk vectors once and reusing them across every future query possible. But it's also a real approximation: two chunks can look equally "close" to a question in vector space for genuinely different reasons — one because it's actually about the same thing, another because it happens to share surface vocabulary without being the best answer.

## Why does this problem exist?

This is the bi-encoder vs. cross-encoder distinction, and it's structural, not a tuning problem:

```
BI-ENCODER (what FAISS/embeddings do):
  question -> vector_q  (computed once, alone)
  chunk    -> vector_c  (computed once, alone, ahead of time)
  similarity = compare(vector_q, vector_c)   <- only NOW do they interact,
                                                 and only as two numbers

CROSS-ENCODER (what re-ranking does):
  (question, chunk) -> ONE model call, fed together
  the model can directly attend to how specific words in the
  question relate to specific words in THIS SPECIFIC chunk
  -> a single relevance score
```

The cross-encoder is strictly more informative per comparison — it never throws away the interaction between question and chunk the way "compare two pre-computed vectors" necessarily does. The cost: it can't be precomputed. Comparing a question against 10,000 chunks means literally running the model 10,000 times, one per pair — completely impractical as your only retrieval mechanism. Hence the two-stage pattern: FAISS (cheap, precomputed, approximate) narrows a large corpus down to a small candidate set; the cross-encoder (expensive per-comparison, precise) spends its computation only on that already-narrowed set.

## What we implemented, where

- `backend/app/rerank/reranker.py` — `get_reranker()` (a `sentence_transformers.CrossEncoder` singleton, `cross-encoder/ms-marco-MiniLM-L-6-v2`), `rerank(query, chunks, top_k)`.
- `backend/app/rag/chain.py` — `_route_and_retrieve` now fetches `RETRIEVAL_CANDIDATE_K` (10) candidates per sub-question instead of the final count directly; a new `_rerank_step` re-scores the merged candidate pool against the **original** question (not the sub-questions used for retrieval) and keeps `RERANK_TOP_K` (5) for generation. The chain is now: route+retrieve → **rerank** → augment → generate.
- `answer_question()` returns `pre_rerank_order`/`post_rerank_order` (chunk id lists) and each source now carries both `faiss_score` and `rerank_score` — the before/after comparison the assignment explicitly requires is available directly from the API response, not something that has to be reconstructed from logs.

## Code walkthrough — the decisions that matter

**Rerank against the original question, not the sub-questions:**
```python
def _rerank_step(inputs: dict) -> list[dict]:
    top_k = int(os.getenv("RERANK_TOP_K", "5"))
    return rerank(inputs["question"], inputs["retrieval"]["chunks"], top_k)
```
Sub-questions (Milestone 7) exist to *retrieve broadly* — they're probes designed to pull in candidate evidence FAISS might otherwise miss. Once candidates are gathered, judging "how relevant is this chunk, really" should be judged against what the user actually asked as a whole, not against one artificial sub-question fragment of it.

**Candidate count deliberately exceeds final count** (`RETRIEVAL_CANDIDATE_K=10` → `RERANK_TOP_K=5`): if these were equal, reranking could only ever *reorder* a fixed set — it could never rescue a genuinely relevant chunk that FAISS's approximate similarity ranked just outside the final cut, nor drop a chunk that only looked relevant due to superficial vocabulary overlap. Casting a wider net first is what gives the cross-encoder real room to correct FAISS's mistakes, not just shuffle them.

**Why `sentence_transformers.CrossEncoder` rather than a separate library:** `sentence-transformers` was already a dependency (Milestone 4, for embeddings) and ships `CrossEncoder` as part of the same package — no new dependency needed, and the same model-loading/caching patterns (network quirks and all) already understood from Milestone 4 apply directly.

## What happened at runtime — a real, unedited before/after

Four real questions were tested to find a genuine reordering (not constructed to force one):

| Question | Top result changed? |
|---|---|
| "What is a time quantum?" | Yes (p12→p11) |
| **"How does priority scheduling work?"** | **Yes — dramatically (p16→p15, a #6→#1 jump)** |
| "What is thread scheduling?" | No (same top result, minor reordering below it) |
| "How does the exponential average formula predict CPU bursts?" | No (same top result) |

Two out of four genuinely changed — an honest finding that reranking *often* but not *always* changes the top result, exactly what you'd expect: when FAISS's approximate ranking is already correct, a more precise re-judgment agrees with it.

**Full trace for the featured example** (`"How does priority scheduling work?"`):
```
PRE-RERANK (FAISS order):        POST-RERANK (cross-encoder order):
 #1 p16  (faiss 0.6236)           #1 p15  (rerank  3.9696)  <- was #6
 #2 p13                           #2 p14  (rerank  2.4019)
 #3 p19                           #3 p16  (rerank  1.3360)  <- was #1
 #4 p14                           #4 p19  (rerank -0.5286)
 #5 p10                           #5 p18  (rerank -1.3618)
 #6 p15  (faiss 0.4949)  <- lowest FAISS score of the top-10
```
Page 15 is the excerpt's actual "priority scheduling with round-robin" walkthrough — the chunk most directly answering the question. FAISS ranked it dead last among the ten candidates it returned (lowest cosine similarity, 0.4949) — plausibly because its text is dense with a worked numerical example (Gantt charts, specific millisecond values) rather than a clean topic-sentence-style definition, which can embed less cleanly toward a general "how does X work" question. Page 16 (multilevel *queue* scheduling — a related but distinct topic that shares surface vocabulary like "priority" and "scheduling") had the *highest* FAISS similarity, and dropped to 3rd once the cross-encoder could actually judge relevance by reading the question and that specific passage together instead of comparing two independently-computed points in space.

This is exactly the failure mode bi-encoders are structurally prone to, corrected exactly the way the two-stage architecture is supposed to correct it — observed on real data, not asserted from theory.

## What can go wrong

- **Reranking adds real latency**: a cross-encoder forward pass per candidate (10 candidates here) is more compute than FAISS's near-instant vector lookup. Fine at this project's scale; would need batching/GPU consideration at higher query volume or larger candidate counts.
- **The reranker can also be wrong.** It's a smaller model with its own biases — nothing here proves it's *always* more correct than FAISS, only that it corrects specific, observable cases like the one above. Both are approximations; the two-stage design is a mitigation, not a guarantee of perfect ranking.
- **Larger `RETRIEVAL_CANDIDATE_K` costs more without bound**: every additional FAISS candidate is one more cross-encoder forward pass. There's a real, if currently unexplored, tuning tradeoff between candidate breadth and rerank cost/latency.
- **The two "no change" test cases are equally important evidence**: a system that reranks are *always* different from FAISS's order would be suspicious (are they even using the same underlying relevance signal at all?) — agreement in the easy cases and disagreement in the hard case is the expected, healthy pattern.

## Self-check questions

1. Why can't a cross-encoder's relevance scores be precomputed and cached the way chunk embeddings are, and why does that specific limitation directly explain why we only rerank the FAISS-narrowed candidate set instead of the whole corpus?
2. In the priority-scheduling example, page 16 had the *highest* FAISS similarity but *dropped* after reranking. What does that specifically tell you about what FAISS's embedding similarity was actually picking up on for that chunk?
3. Two of the four test questions showed no change in the top result after reranking. Does that mean reranking "didn't do anything" for those questions, or is there a more precise way to describe what happened?

<details><summary>Answers</summary>

1. A cross-encoder's score depends on the (question, chunk) *pair* — the model output isn't a property of the chunk alone, unlike an embedding vector, which is a fixed property of the text regardless of what question it's later compared against. There is no way to precompute "how relevant is this chunk" without already knowing the question, and questions aren't known in advance — so cross-encoder scoring must happen at query time, for whichever candidates are already in hand, which is precisely why it can only be applied to an already-narrowed set rather than an entire corpus.
2. It suggests the embedding model picked up on shared surface-level vocabulary and general topical proximity ("scheduling," "priority," "queue") rather than the specific mechanics the question was actually asking about. Page 16 is topically adjacent (multilevel queue scheduling *does* reference priority as a concept) but isn't the chunk that actually explains how priority scheduling works — exactly the kind of near-miss a bi-encoder's independent-vector comparison is prone to, and exactly what a cross-encoder's joint reading is positioned to catch.
3. It's more precise to say the cross-encoder *agreed* with FAISS's top pick for those two questions, not that reranking was inert — the reranking computation still ran, still produced independent relevance scores, and those scores happened to confirm rather than overturn FAISS's ordering. That agreement is itself informative: it suggests FAISS's approximation was already good enough for those particular questions, which is a reasonable, expected outcome — not every retrieval is a hard case.
</details>
