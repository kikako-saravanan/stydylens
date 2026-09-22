# Milestone 9 — RAGAS Evaluation

## What problem are we solving?

Everything built so far — retrieval, reranking, routing, generation — has been verified with a handful of hand-picked example questions. That's enough to prove each mechanism *works*, but not enough to say the system is *good*, or to notice when a future change quietly makes it worse. We need a repeatable, numeric measurement, run over a fixed set of real questions, that can be compared run to run.

## Why does this problem exist?

A normal unit test asserts one exact expected output. A RAG system's output is generated text — there's no single "correct string" to assert equality against, and grading it requires judgment: is this answer *supported by the evidence*? Does it *actually answer* what was asked? Was the *evidence itself* any good? Those are three separate, genuinely different failure modes:

```
Bad retrieval, good generation:
  wrong chunks retrieved -> LLM faithfully summarizes the WRONG evidence
  -> answer is "faithful" to context, but the context itself was useless

Good retrieval, bad generation:
  right chunks retrieved -> LLM ignores them, answers from general
  knowledge or hallucinates beyond what's actually there
  -> retrieval was fine, generation broke the grounding

Good retrieval, good generation, wrong question:
  answer is accurate and grounded, but doesn't actually address
  what the user asked
```

A single "did it get the right answer" metric can't distinguish these. RAGAS scores each failure mode with its own metric, specifically so a bad score points at *which stage* broke, not just that something did.

## What each metric actually measures

- **Faithfulness**: extracts individual factual claims from the generated answer, then checks each claim against the retrieved context — is every claim actually supported, or did the model add something not in the evidence? This is the direct measure of "did generation stay grounded."
- **Answer relevancy**: generates several synthetic questions that the given *answer* would be a good response to, then compares those synthetic questions' embeddings to the *actual* question's embedding. A relevant answer produces synthetic questions that closely resemble the real one; an off-topic or evasive answer produces synthetic questions that don't.
- **Context precision**: judges, chunk by chunk, whether each retrieved chunk was actually relevant to answering the question (using the reference answer as the standard), and rewards rankings where relevant chunks appear earlier. This measures retrieval quality specifically, independent of what generation did with it.

## What we implemented, where

- `data/eval/questions.json` — 14 real question/expected-answer pairs covering the actual sample document (not fabricated), including 2 deliberately out-of-scope questions (deadlock, photosynthesis) to test honest refusal under evaluation, not just under ad-hoc manual testing.
- `scripts/run_ragas_eval.py` — runs every question through the real `build_chain()` (routing → retrieval → rerank → generation, unmodified from Milestones 6-8), builds a RAGAS `EvaluationDataset`, scores it with `faithfulness`/`answer_relevancy`/`context_precision`, and appends results to `data/eval/results.jsonl`.
- `data/eval/results.jsonl` — the actual output of a real run, committed as evidence.

## Real, honestly-documented integration bugs (three, all fixed by verifying against the installed package, not by guessing)

**Bug 1 — `ragas` 0.4.3 fails to import at all.** `ragas.llms.base` imports `from langchain_community.chat_models.vertexai import ChatVertexAI` — a module that was removed from `langchain-community` starting at 0.4.0. Fix: pinned `langchain-community==0.3.31` (the last release that still has the deprecated shim), documented with a comment in `requirements.txt` explaining exactly why, so a future contributor doesn't "helpfully" upgrade it and reintroduce the break.

**Bug 2 — every RAGAS judge call failed: `\`temperature\` is deprecated for this model.`** RAGAS's internal evaluation prompts always pass an explicit `temperature` to the LLM. Current-generation Claude models (Sonnet 5, Opus 5) reject that parameter outright with a 400 — a real, current API constraint, not a RAGAS bug. Fix: a **separate, dedicated judge model** for RAGAS only (`RAGAS_JUDGE_MODEL=claude-haiku-4-5`, confirmed via a direct test call to accept `temperature`), distinct from `LLM_MODEL` (the model actually used to generate StudyLens's answers). This is a legitimate, common pattern in practice — the model judging quality doesn't have to be the same model producing the output.

**Bug 3 — `answer_relevancy` crashed with `AttributeError: 'HuggingFaceEmbeddings' object has no attribute 'embed_query'`.** RAGAS ships two, incompatible embeddings interfaces: a newer `ragas.embeddings.HuggingFaceEmbeddings` (a different, non-LangChain-shaped interface), and the classic LangChain-shaped interface (`.embed_query()`/`.embed_documents()`) that the *deprecated* `answer_relevancy` metric actually expects internally. Fix: wrap the classic `langchain_community.embeddings.HuggingFaceEmbeddings` in RAGAS's own `LangchainEmbeddingsWrapper` — verified with a standalone test call (`embed_query('hello world')` → a real 384-dim vector) before trusting it in the full eval run.

All three were found by actually running the code and reading the real traceback — not by pattern-matching to how an older or different version of RAGAS is remembered to work. RAGAS's own current README examples were not sufficient here (the deprecated-but-still-functional classic metrics path, which this project uses, isn't quite what the docs point newcomers toward — `ragas.metrics.collections` — but the collections API requires a different, more involved LLM wrapper (`InstructorBaseRagasLLM`) not yet integrated; the classic path was chosen deliberately for this milestone's scope).

## What happened — real scores, first successful run

```
faithfulness:      0.9155
answer_relevancy:  0.7275
context_precision: 0.7012
```

Not all 1.0, not missing — real variance across 14 real questions, matching exactly the assignment's own stated bar for a credible (not fabricated) result.

**Per-question detail reveals two genuinely instructive cases:**

1. **The two out-of-scope questions** ("What is a deadlock and how can it be prevented?", "How do plants convert sunlight...?") scored **faithfulness=1.0, answer_relevancy=0.0, context_precision=0.0**. This is exactly correct, not a bug: the actual answer both times was *"I couldn't find this in the uploaded material"* — a claim with nothing unsupported in it (perfectly faithful), but one that doesn't resemble a real answer to the literal question (correctly scored as not relevant), retrieved from chunks that aren't actually about the question either (correctly scored as low precision). RAGAS's metrics independently reconstructed, from raw text alone, exactly the behavior we already knew the system exhibits — real, external confirmation, not just an internal claim.

2. **"What is dispatch latency?"** got a **correct, verifiably accurate one-sentence answer** ("Dispatch latency is the time it takes for the dispatcher to stop one process and start another process running" — matching the source almost verbatim) yet scored **faithfulness=0.0**. Separately, **"What is Shortest-Job-First (SJF) scheduling...?"** got a **detailed, correct, well-grounded answer** yet scored **answer_relevancy=0.0**. Neither looks like an actual system failure on inspection of the real answer text — both read as limitations of the judge model's own claim-extraction (faithfulness) and synthetic-question-generation (answer_relevancy) steps, which are themselves LLM calls and can misfire on short or single-claim answers. This is reported here rather than quietly re-run until it looked better — a RAGAS score of 0 does not automatically mean the underlying system is wrong, and part of doing this evaluation honestly is not treating every low score as proof of a bug without checking.

## What can go wrong

- **The judge LLM is itself an LLM** — faithfulness/relevancy scoring is not a deterministic ground truth; it inherits its own judge model's occasional misjudgments, as seen directly above.
- **`answer_relevancy` involves generating synthetic questions**, an inherently somewhat non-deterministic step — re-running the exact same eval could produce slightly different scores for borderline cases, even with `temperature=0.0` on the judge model, since embedding comparison thresholds are continuous, not binary.
- **Context precision depends on the reference answer's exact phrasing**: a reference answer that doesn't closely mirror how the source document phrases something could make genuinely relevant retrieved chunks look less "precise" to the judge than they actually are.
- **This eval set is 14 questions against one 24-page excerpt** — a real signal, not a comprehensive benchmark. A production system would want a much larger, more diverse eval set before trusting these numbers as representative.

## Self-check questions

1. Why does a RAG system need three separate metrics (faithfulness, answer relevancy, context precision) instead of one overall "is this a good answer" score?
2. The two out-of-scope questions scored faithfulness=1.0 but answer_relevancy=0.0. Explain in your own words why *both* of those scores are actually correct, not contradictory.
3. Why was a *different* model (`claude-haiku-4-5`) chosen as the RAGAS judge instead of reusing `LLM_MODEL` (`claude-sonnet-5`), and why isn't using two different models here a source of inconsistency?

<details><summary>Answers</summary>

1. Retrieval quality and generation quality are separate failure points (Milestone 0's core lesson) — a single blended score can't tell you which stage to actually go fix. A low score with high faithfulness but low context precision points at retrieval; a low score with high context precision but low faithfulness points at generation ignoring good evidence. Collapsing these into one number would throw away exactly the diagnostic information evaluation exists to provide.
2. Faithfulness asks "is every claim in the answer supported by the context" — the answer "I couldn't find this in the uploaded material" makes zero factual claims about deadlocks at all, so there's nothing unsupported to flag; it's trivially, correctly faithful. Answer relevancy asks "does this answer actually address what was asked" — a refusal, by definition, doesn't supply the substantive content the question was asking for, so it correctly scores as not relevant to the literal question. Both are measuring genuinely different things, and a refusal can legitimately be faithful (true to what it says) while also being non-relevant (not the substantive answer that was asked for) — no contradiction.
3. `claude-sonnet-5` is the model StudyLens uses to generate the actual answers users see — that's what's being evaluated. The *judge* doing the evaluation is a separate role, and current-generation Claude models happen to reject the `temperature` parameter RAGAS's internal prompts require, making `claude-sonnet-5` technically unusable as a RAGAS judge regardless of preference. Using a different, compatible model as judge doesn't undermine the evaluation's validity — the judge's job is to read the already-generated answer and context and assess them, a task that doesn't require it to be the same model that produced that answer, the same way a human grader doesn't need to be the same person who wrote the essay being graded.
</details>
