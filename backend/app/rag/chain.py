import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.rag.llm_provider import generate
from app.rag.router import route_query
from app.rerank.reranker import rerank
from app.retrieval.faiss_store import query_index

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are StudyLens, an assistant that answers questions about a student's "
    "uploaded course material.\n\n"
    "Rules:\n"
    "1. Answer ONLY using the provided context below. Do not use outside or "
    "general knowledge, even if you happen to know the answer.\n"
    "2. If the context does not contain enough information to answer, say so "
    "explicitly — respond with something like \"I couldn't find this in the "
    "uploaded material.\" Never guess or fill gaps.\n"
    "3. Be direct and concise."
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ]
)


def make_snippet(text: str, max_len: int = 200) -> str:
    """Truncate at a word boundary, not mid-word, so a citation snippet
    reads as a real fragment a reviewer can match against the source page
    rather than a string arbitrarily cut off partway through a word."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.6:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "…"


def format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no relevant material found in the uploaded documents)"
    return "\n\n".join(
        f"[Source: {c['source']}, page {c['page']}]\n{c['text']}" for c in chunks
    )


def _classify_and_decompose(question: str):
    """Stage 1 alone: classify + decompose, no retrieval yet.

    Split out from retrieval (below) specifically so a caller — the
    streaming pipeline-visualization endpoint — can observe "routing
    finished" as its own moment in time, distinct from "retrieval
    finished", rather than only ever seeing both bundled as one step.
    """
    return route_query(question)


def _retrieve_for_subquestions(routed, candidate_k: int) -> dict:
    """Stage 2 alone: retrieve per sub-question and merge, given an
    already-computed routing decision. See `_route_and_retrieve` for why
    single_fact/multi_part/summarization all flow through the same loop.
    """
    seen_chunk_ids: set[str] = set()
    merged_chunks: list[dict] = []
    retrieval_trace: list[dict] = []

    for sub_question in routed.sub_questions:
        results = query_index(sub_question, candidate_k)
        retrieval_trace.append(
            {"sub_question": sub_question, "chunk_ids": [r["chunk_id"] for r in results]}
        )
        for r in results:
            if r["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(r["chunk_id"])
                merged_chunks.append(r)

    merged_chunks.sort(key=lambda r: r["score"], reverse=True)
    return {"chunks": merged_chunks, "retrieval_trace": retrieval_trace}


def _route_and_retrieve(inputs: dict) -> dict:
    """Classify the question, decompose if needed, retrieve per sub-question,
    and merge into one deduplicated evidence set.

    single_fact produces exactly one sub-question (the original), so this
    reduces to plain Milestone-5 retrieval in that case. multi_part and
    summarization produce several sub-questions, each retrieved
    independently — this is what lets a question like "what is X and how
    does it compare to Y" pull in evidence for BOTH X and Y, instead of one
    side dominating a single top-k search when the two topics' embeddings
    aren't equally close to the combined question.

    A thin composer over _classify_and_decompose + _retrieve_for_subquestions
    (below) — kept as one function here because the LCEL chain (build_chain)
    only needs the combined result, never the intermediate boundary.
    """
    # Fetch MORE candidates per sub-question than we'll actually use for
    # generation (RETRIEVAL_CANDIDATE_K > RERANK_TOP_K) — FAISS casts a
    # cheap, wide net here; the cross-encoder in the next stage narrows it
    # down using a more precise (but slower) relevance judgment.
    candidate_k = inputs.get("k") or int(os.getenv("RETRIEVAL_CANDIDATE_K", "10"))
    routed = _classify_and_decompose(inputs["question"])
    retrieval = _retrieve_for_subquestions(routed, candidate_k)

    logger.info(
        "[routing] %r -> type=%s, %d sub-question(s), %d unique chunk(s) after merge",
        inputs["question"], routed.query_type, len(routed.sub_questions), len(retrieval["chunks"]),
    )

    return {
        "query_type": routed.query_type,
        "sub_questions": routed.sub_questions,
        "chunks": retrieval["chunks"],
        "retrieval_trace": retrieval["retrieval_trace"],
    }


def _rerank_step(inputs: dict) -> list[dict]:
    """Re-score the merged FAISS candidates against the ORIGINAL question
    (not the sub-questions used for retrieval) with a cross-encoder, and
    keep only the best few for generation.

    Using the original question here, not a sub-question, matters: the
    sub-questions were retrieval PROBES to gather candidate evidence broadly;
    the reranker's job is judging what's actually most relevant to what the
    user really asked, as a whole.
    """
    top_k = int(os.getenv("RERANK_TOP_K", "5"))
    return rerank(inputs["question"], inputs["retrieval"]["chunks"], top_k)


def _generate_answer(inputs: dict) -> str:
    prompt_value = PROMPT.invoke({"context": inputs["context"], "question": inputs["question"]})
    return generate(prompt_value.to_messages())


def build_chain():
    """The actual LCEL chain: question -> route+retrieve -> rerank -> augment -> generate.

    Each stage is an explicit, composed step (via RunnablePassthrough.assign
    and the `|` operator), not a sequence of plain function calls that
    happen to use LangChain objects — this is the difference between "uses
    LangChain" and "is an LCEL chain." Generation itself delegates to
    llm_provider.generate(), which handles primary/fallback provider
    switching — the chain doesn't need to know that happens.
    """
    return (
        RunnablePassthrough.assign(retrieval=RunnableLambda(_route_and_retrieve))
        | RunnablePassthrough.assign(reranked_chunks=RunnableLambda(_rerank_step))
        | RunnablePassthrough.assign(context=lambda x: format_context(x["reranked_chunks"]))
        | RunnablePassthrough.assign(answer=RunnableLambda(_generate_answer))
    )


def _build_sources(reranked_chunks: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": c["chunk_id"],
            "source": c["source"],
            "page": c["page"],
            "faiss_score": c["score"],
            "rerank_score": c["rerank_score"],
            "snippet": make_snippet(c["text"]),
        }
        for c in reranked_chunks
    ]


def answer_question(question: str, k: int | None = None) -> dict:
    chain = build_chain()
    result = chain.invoke({"question": question, "k": k})
    retrieval = result["retrieval"]
    reranked_chunks = result["reranked_chunks"]

    return {
        "question": question,
        "answer": result["answer"],
        "query_type": retrieval["query_type"],
        "sub_questions": retrieval["sub_questions"],
        "retrieval_trace": retrieval["retrieval_trace"],
        "pre_rerank_order": [c["chunk_id"] for c in retrieval["chunks"]],
        "post_rerank_order": [c["chunk_id"] for c in reranked_chunks],
        "sources": _build_sources(reranked_chunks),
    }


def stream_answer_question(question: str, k: int | None = None):
    """Same pipeline as answer_question(), reusing the exact same stage
    functions (_classify_and_decompose, _retrieve_for_subquestions, rerank,
    _generate_answer) — but as a generator that yields a {"stage", "status",
    ...} event right before and right after each stage, instead of
    returning one final dict.

    This exists specifically for the frontend's pipeline-visualization
    panel: it lets a student watch "routing -> retrieval -> reranking ->
    generation" happen as four distinct, real moments in time, rather than
    reading a JSON blob that describes the finished result. It is a
    different ORCHESTRATION of the same building blocks the LCEL chain
    (build_chain) uses, not a second implementation of the pipeline logic
    — every function called here is the identical function build_chain()
    composes, so the two paths cannot silently drift apart in behavior.
    """
    candidate_k = k or int(os.getenv("RETRIEVAL_CANDIDATE_K", "10"))

    yield {"stage": "routing", "status": "start"}
    routed = _classify_and_decompose(question)
    yield {
        "stage": "routing",
        "status": "done",
        "query_type": routed.query_type,
        "sub_questions": routed.sub_questions,
    }

    yield {"stage": "retrieval", "status": "start"}
    retrieval = _retrieve_for_subquestions(routed, candidate_k)
    yield {
        "stage": "retrieval",
        "status": "done",
        "retrieval_trace": retrieval["retrieval_trace"],
        "candidate_count": len(retrieval["chunks"]),
    }

    yield {"stage": "reranking", "status": "start"}
    top_k = int(os.getenv("RERANK_TOP_K", "5"))
    reranked_chunks = rerank(question, retrieval["chunks"], top_k)
    yield {
        "stage": "reranking",
        "status": "done",
        "pre_rerank_order": [c["chunk_id"] for c in retrieval["chunks"]],
        "post_rerank_order": [c["chunk_id"] for c in reranked_chunks],
    }

    yield {"stage": "generation", "status": "start"}
    context = format_context(reranked_chunks)
    answer = _generate_answer({"question": question, "context": context})
    sources = _build_sources(reranked_chunks)
    yield {"stage": "generation", "status": "done", "answer": answer, "sources": sources}

    yield {
        "stage": "complete",
        "question": question,
        "answer": answer,
        "query_type": routed.query_type,
        "sub_questions": routed.sub_questions,
        "retrieval_trace": retrieval["retrieval_trace"],
        "pre_rerank_order": [c["chunk_id"] for c in retrieval["chunks"]],
        "post_rerank_order": [c["chunk_id"] for c in reranked_chunks],
        "sources": sources,
    }
