import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.rag.llm_provider import generate
from app.rag.router import route_query
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


def format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no relevant material found in the uploaded documents)"
    return "\n\n".join(
        f"[Source: {c['source']}, page {c['page']}]\n{c['text']}" for c in chunks
    )


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
    """
    k = inputs.get("k") or int(os.getenv("RETRIEVAL_TOP_K", "5"))
    routed = route_query(inputs["question"])

    seen_chunk_ids: set[str] = set()
    merged_chunks: list[dict] = []
    retrieval_trace: list[dict] = []

    for sub_question in routed.sub_questions:
        results = query_index(sub_question, k)
        retrieval_trace.append(
            {"sub_question": sub_question, "chunk_ids": [r["chunk_id"] for r in results]}
        )
        for r in results:
            if r["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(r["chunk_id"])
                merged_chunks.append(r)

    merged_chunks.sort(key=lambda r: r["score"], reverse=True)
    logger.info(
        "[routing] %r -> type=%s, %d sub-question(s), %d unique chunk(s) after merge",
        inputs["question"], routed.query_type, len(routed.sub_questions), len(merged_chunks),
    )

    return {
        "query_type": routed.query_type,
        "sub_questions": routed.sub_questions,
        "chunks": merged_chunks,
        "retrieval_trace": retrieval_trace,
    }


def _generate_answer(inputs: dict) -> str:
    prompt_value = PROMPT.invoke({"context": inputs["context"], "question": inputs["question"]})
    return generate(prompt_value.to_messages())


def build_chain():
    """The actual LCEL chain: question -> route+retrieve -> augment -> generate.

    Each stage is an explicit, composed step (via RunnablePassthrough.assign
    and the `|` operator), not a sequence of plain function calls that
    happen to use LangChain objects — this is the difference between "uses
    LangChain" and "is an LCEL chain." Generation itself delegates to
    llm_provider.generate(), which handles primary/fallback provider
    switching — the chain doesn't need to know that happens.
    """
    return (
        RunnablePassthrough.assign(retrieval=RunnableLambda(_route_and_retrieve))
        | RunnablePassthrough.assign(context=lambda x: format_context(x["retrieval"]["chunks"]))
        | RunnablePassthrough.assign(answer=RunnableLambda(_generate_answer))
    )


def answer_question(question: str, k: int | None = None) -> dict:
    chain = build_chain()
    result = chain.invoke({"question": question, "k": k})
    retrieval = result["retrieval"]

    return {
        "question": question,
        "answer": result["answer"],
        "query_type": retrieval["query_type"],
        "sub_questions": retrieval["sub_questions"],
        "retrieval_trace": retrieval["retrieval_trace"],
        "sources": [
            {
                "chunk_id": c["chunk_id"],
                "source": c["source"],
                "page": c["page"],
                "score": c["score"],
                "snippet": c["text"][:200],
            }
            for c in retrieval["chunks"]
        ],
    }
