# Milestone 13 — Full Documentation

## What problem are we solving?

Milestones 1-12 each added real content to the top-level `README.md` as they were built — a chunk-size note here, a RAGAS table there, an auth section further down. That's the right way to keep documentation from rotting (write it as you build, not after), but the result was organized chronologically (by when it was written), not by what a new reader actually needs first. A stranger with only the repo link — the exact scenario the submission guidelines describe — needs a top-to-bottom structure: what is this, how do I run it, what does the API look like, what are the known gaps.

## Why does this problem exist?

Two different audiences read a README for two different reasons. Someone building on top of this project milestone-by-milestone (this project's own working style) benefits from documentation growing incrementally, right next to the code that just changed. Someone *evaluating* the finished project — a grader, a reviewer, a stranger cloning it cold — needs a single coherent document organized around their questions, in an order that makes sense to read once, top to bottom, not the order the features happened to be built in.

## What we did

Reorganized `README.md` into the structure the assignment's own Problem Statement asks for explicitly ("setup, architecture diagram, tech stack table, API reference"): a table of contents, an ASCII architecture diagram tracing the full pipeline end to end, a tech stack table with a *reason* for each choice (not just a name), a repository structure tree, consolidated setup instructions for both backend and frontend, a full environment-variables table (every variable in `.env.example`, with its default and purpose), a complete API reference table for every endpoint plus the exact `/api/ask` response shape, and a single consolidated "Known limitations" section pulling together every honestly-reported gap that was previously scattered across individual milestone sections.

**Nothing was invented or softened in this pass.** Every number, every real bug, every "not verified" admission that existed in the incremental version is still here — RAGAS's real 0.9155/0.7275/0.7012 scores, the real before/after reranking table, the real frontend browser-testing gap, the real Gemini-fallback TLS limitation. Milestone 13's job was reorganizing truthful content for a new reader, not making the project look more finished than it is — the latter is exactly what the submission guidelines' "honesty" grading dimension penalizes harder than an accurately-scoped submission.

## What's deferred, deliberately, to later milestones

- **Deployment section** — currently absent from the top-level README's table of contents on purpose; Milestone 14 will add it once there's an actual hosted URL (or a documented decision to submit as repo-only) to describe, rather than write speculative deployment instructions now and risk them drifting from what actually gets deployed.
- **Final acceptance checklist** — Milestone 15 walks the assignment's own explicit checklist item by item with real verification; this README's "Known limitations" section is the honest, ongoing version of that same spirit, kept current throughout rather than assembled only at the end.

## Self-check questions

1. Why does reorganizing the README (this milestone) matter separately from having already documented everything incrementally in the per-milestone sections (Milestones 1-12)?
2. The "Known limitations" section consolidates gaps that were each already disclosed somewhere in the per-milestone READMEs/docs. What's the actual risk of *not* consolidating them into one section, even though the information technically already existed?
3. Why does this milestone explicitly avoid writing a "Deployment" section with placeholder/aspirational instructions before Milestone 14 actually deploys anything?

<details><summary>Answers</summary>

1. Incremental documentation optimizes for the writer (capture context while it's fresh, right next to the change that produced it) — it does not optimize for a first-time reader trying to build a mental model of the whole system in one pass. A grader or new contributor reading milestone-ordered sections has to reconstruct "what does the finished system actually look like" themselves from a chronological log; a reorganized README hands them that model directly, in the order the assignment's own required depth (architecture → tech stack → setup → API → evaluation → limitations) implies a reader actually needs it.
2. Scattered disclosure technically satisfies "it's documented somewhere," but a reader skimming for "what should I not trust yet" has to read the entire document start to finish to assemble that list themselves — in practice, some gaps would get missed simply because they're not where a reader expects "gotchas" to live. Consolidating them into one section makes "here's exactly what's honestly incomplete" impossible to miss, which matters directly for the assignment's own "honesty" grading dimension: a reviewer checking whether the README accurately represents what's live-wired vs. not shouldn't have to hunt for that information.
3. Writing deployment instructions before deployment actually happens risks the classic documentation-drift failure: the written instructions describe an intended plan, the real deployment ends up different in some detail (a different host, a different env var, a CORS origin that needed adjusting), and the README quietly becomes wrong the moment it was written rather than the moment reality changed. Documenting a stage only after actually doing it — the same discipline used for every prior milestone in this project — means every claim in this README describes something that was actually run and verified, not something planned.
</details>
