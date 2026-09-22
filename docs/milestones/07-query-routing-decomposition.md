# Milestone 7 — Query Routing & Decomposition

## What problem are we solving?

Milestone 5's retrieval embeds the *whole* question as one vector and finds chunks close to that one point. That works well when a question is genuinely about one thing. It breaks down when a question is actually two questions glued together — "What is X and how does it compare to Y?" — because the combined embedding is some blend of X and Y, and whichever concept dominates that blend (often just whichever has more/more-distinctive words) crowds out the other in a single top-k search.

## Why does this problem exist?

An embedding model doesn't know "this sentence contains two separable claims that should be looked up independently." It just maps the whole input string to one point in space. Retrieval built on top of that inherits the same blindness. The fix has to happen *before* embedding-based retrieval runs: recognize when a question has separable parts, and retrieve for each part on its own.

## First principles

```
A single embedded question -> one vector -> one neighborhood in vector space
        |
   if the question actually contains 2+ distinct sub-topics, that one
   neighborhood search will favor whichever sub-topic the combined
   embedding leans toward -- the other sub-topic's evidence may not
   make the top-k at all
        |
   fix: don't retrieve once for the whole question -- first figure out
   IF it should be split, and if so, split it into standalone questions
        |
   retrieve separately for each standalone question, merge the results
        |
   this requires a CLASSIFICATION step (is this one question or many?)
   and, when it's many, a DECOMPOSITION step (what exactly are the parts?)
        |
   both can be done in a single LLM call with structured output -- the
   model reads the question once and returns both the classification
   and the list of sub-questions to retrieve for
```

Three categories, not two: `single_fact` (one focused question — the vast majority of real usage), `multi_part` (two or more distinct things joined by "and"/"vs"/"compare", or multiple question marks), and `summarization` (asks for an overview rather than one fact — has no natural "parts" to split into, but benefits from the *same* decompose-and-merge mechanism using LLM-generated topic-probing questions instead of user-specified parts).

## What we implemented, where

- `backend/app/rag/router.py` — `RoutedQuery` (a Pydantic model: `query_type`, `sub_questions`), `route_query()` using `ChatAnthropic(...).with_structured_output(RoutedQuery)`.
- `backend/app/rag/chain.py` — `_route_and_retrieve()` replaces the old single-question `_retrieve()`: calls `route_query()`, then runs `query_index()` once per sub-question, merges results deduplicated by `chunk_id` (keeping the first occurrence, sorted by score descending after merge), and records a `retrieval_trace` (which sub-question produced which chunk ids) for transparency.
- `answer_question()` now returns `query_type`, `sub_questions`, and `retrieval_trace` alongside `answer`/`sources` — not hidden internals, but genuinely useful for a frontend to show "here's how I broke down your question" and for graders/reviewers to directly verify the decomposition happened.

## Code walkthrough — the design decisions that matter

**Routing degrades gracefully, it doesn't gate the whole request:**
```python
def route_query(question: str) -> RoutedQuery:
    try:
        return _router_llm().invoke([...])
    except Exception as e:
        logger.warning("Query routing failed (%s); treating as single_fact.", e)
        return RoutedQuery(query_type="single_fact", sub_questions=[question])
```
Routing is an *enhancement* over Milestone 6's plain retrieval, not a new hard dependency. If the classification call fails for any reason, falling back to "treat it as one direct question" reproduces exactly the Milestone 6 behavior — strictly better than making the whole `/api/ask` request fail because a classification step (not the actual answer-generation step) had a problem.

**`single_fact` is not a special case in the retrieval code — it's the general case with exactly one sub-question:**
```python
for sub_question in routed.sub_questions:
    results = query_index(sub_question, k)
    ...
```
There's no `if query_type == "single_fact": do the old thing` branch. A `single_fact` classification just means `sub_questions` has length 1 (the original question, verbatim, per the router's system prompt) — the merge loop runs once and produces exactly what Milestone 6 already did. This is a meaningful simplification: one code path handles all three categories correctly, rather than three parallel implementations that could silently drift apart.

**Deduplication by `chunk_id`, not by content:** two different sub-questions can legitimately retrieve the *same* chunk (a chunk can be relevant to both halves of a comparison question). Deduplicating by the exact `chunk_id` string keeps that one copy in the final merged context instead of repeating the same paragraph twice in what the LLM reads — repeated context wastes tokens and can subtly bias the model toward whatever got duplicated.

**`summarization` reuses the multi-part machinery by generating its own "parts":** the router's system prompt instructs it to produce 3-5 broad, topic-probing questions for summarization requests (e.g. "What are the main topics covered?", "What key definitions are introduced?"). This means summarization gets *the same* retrieve-per-sub-question-and-merge treatment as multi_part, without a separate special-cased retrieval path — the only difference is *who decided the sub-questions* (the user, implicitly, for multi_part; the router LLM, explicitly, for summarization).

## What happened at runtime — real results for all three categories

**`single_fact`** (`"What is a time quantum?"`):
```
query_type: single_fact
sub_questions: ['What is a time quantum?']
```
Reduces to exactly one retrieval call, as expected.

**`multi_part`** (`"What is round robin scheduling and how does it compare to first-come-first-served scheduling?"`) — this is the assignment's own explicit checklist item ("a deliberately multi-part test question... produces evidence that both parts were retrieved for"):
```
query_type: multi_part
sub_questions: [
  "What is round robin scheduling?",
  "How does round robin scheduling compare to first-come-first-served (FCFS) scheduling?"
]
retrieval_trace: [
  {sub_question: "What is round robin scheduling?", chunk_ids: [p16, p10, p15, p19, p7]},
  {sub_question: "...compare to FCFS...", chunk_ids: [p7, p18, p10, p16, p6]}
]
```
Both sub-questions retrieved independently and visibly, with 3 chunks overlapping (p7, p10, p16) and each contributing chunks the other didn't find (p15/p19 unique to part 1; p18/p6 unique to part 2) — direct, inspectable proof that decomposition changed what evidence reached the LLM, not just a claim that it should. The resulting answer correctly covered both round-robin's mechanics *and* an honest comparison to FCFS, including explicitly noting where the source material didn't have a direct numerical comparison — grounding held even under decomposition.

**`summarization`** (`"Summarize what this lecture material covers."`):
```
query_type: summarization
sub_questions: [
  "What are the main topics and concepts covered in this lecture?",
  "What key definitions or terminology are introduced in this lecture?",
  "What examples or case studies are used to illustrate the main ideas?",
  "What are the key takeaways or conclusions from this lecture?",
  "How do the topics in this lecture connect to broader themes in the course?"
]
12 unique chunks retrieved (vs. 5 for a single-question search)
```
The resulting summary covered Basic Concepts, Preemptive/Nonpreemptive scheduling, the Dispatcher, and multiple scheduling algorithms — a genuinely broader spread across the document than a single embedded "summarize this" query would have found on its own (which would just return the 5 chunks nearest to the word "summarize," almost certainly missing most of the document's actual range of topics).

## What can go wrong

- **Routing cost**: every question now costs at least one extra LLM call (the router) before the main generation call — for `multi_part`/`summarization`, it also means 2-5x the retrieval calls (cheap, local FAISS lookups, not a real cost concern) and a larger merged context (more tokens sent to the generation LLM, a real, if small, cost increase).
- **Misclassification**: the router can get it wrong — e.g., classifying a borderline question as `single_fact` when the user meant it as two things, or over-decomposing a question that was really about one nuanced concept. No evaluation of routing *accuracy* itself exists yet; Milestone 9's RAGAS evaluation measures the end-to-end answer/retrieval quality, not the router's classification precision specifically.
- **Structured output failures**: `.with_structured_output()` can occasionally fail to produce valid structured data (a model refusal, a malformed response) — caught by the same `except Exception` that degrades to `single_fact`, so this fails safe rather than crashing the request.
- **The router does not currently use the Anthropic→Gemini fallback** from Milestone 6 — it calls `ChatAnthropic` directly. If Anthropic is down, routing itself fails (safely, falling back to `single_fact` per the design above) even though the *main* generation step would have successfully failed over to Gemini. This is a deliberate scope decision, not an oversight: extending the fallback pattern to structured-output calls adds real complexity (verifying Gemini's structured-output behavior matches), and the safe degradation to `single_fact` means routing failure never breaks the request — it just loses the decomposition *benefit* for that one question until Anthropic recovers.

## Self-check questions

1. Why does `single_fact` not get a separate code path in `_route_and_retrieve()` — what property of the `RoutedQuery` output makes the general loop already correct for it?
2. In the multi-part test above, 3 of the 10 total retrieved chunk-slots were duplicates (same chunk retrieved by both sub-questions). Why is that overlap itself a *meaningful* signal, rather than just wasted retrieval work?
3. Why does routing failure fall back to `single_fact` specifically, rather than, say, failing the whole `/api/ask` request with a 500?

<details><summary>Answers</summary>

1. `single_fact` just means `sub_questions` is a list containing exactly one item — the original question, unchanged (per the router's own system prompt instructions). The merge loop iterates over `sub_questions` regardless of category; with one item, it runs its body once and produces exactly the single-retrieval behavior from Milestone 6. No branch is needed because the *data shape* already encodes the distinction — one sub-question naturally behaves like "don't decompose."
2. Chunks that both sub-questions independently converge on are chunks genuinely relevant to *both* halves of the comparison — in this case, pages discussing scheduling algorithms broadly enough to be pulled in by both the "what is RR" and "RR vs FCFS" searches. That overlap is a soft signal of cross-cutting relevance, not noise; it's part of why deduplication (keeping one copy, not discarding it as redundant) is the right merge strategy rather than, say, only keeping chunks unique to one sub-question.
3. A classification/decomposition step is an optimization on top of retrieval, not a prerequisite for it — the system can always fall back to treating the question as a single, undecomposed lookup and still produce a genuine (if potentially less complete) answer. Failing the entire request over a failure in an enhancement layer, when a safe, still-useful degraded path exists, would make the system less robust for no benefit — matching the same reasoning already applied to the LLM provider fallback in Milestone 6.
</details>
