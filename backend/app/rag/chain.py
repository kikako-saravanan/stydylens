import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.rag.llm_provider import generate
from app.retrieval.faiss_store import query_index

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


def _retrieve(inputs: dict) -> list[dict]:
    k = inputs.get("k") or int(os.getenv("RETRIEVAL_TOP_K", "5"))
    return query_index(inputs["question"], k)


def _generate_answer(inputs: dict) -> str:
    prompt_value = PROMPT.invoke({"context": inputs["context"], "question": inputs["question"]})
    return generate(prompt_value.to_messages())


def build_chain():
    """The actual LCEL chain: question -> retrieve -> augment -> generate.

    Each stage is an explicit, composed step (via RunnablePassthrough.assign
    and the `|` operator), not a sequence of plain function calls that
    happen to use LangChain objects — this is the difference between "uses
    LangChain" and "is an LCEL chain." Generation itself delegates to
    llm_provider.generate(), which handles primary/fallback provider
    switching — the chain doesn't need to know that happens.
    """
    return (
        RunnablePassthrough.assign(chunks=RunnableLambda(_retrieve))
        | RunnablePassthrough.assign(context=lambda x: format_context(x["chunks"]))
        | RunnablePassthrough.assign(answer=RunnableLambda(_generate_answer))
    )


def answer_question(question: str, k: int | None = None) -> dict:
    chain = build_chain()
    result = chain.invoke({"question": question, "k": k})

    return {
        "question": question,
        "answer": result["answer"],
        "sources": [
            {
                "chunk_id": c["chunk_id"],
                "source": c["source"],
                "page": c["page"],
                "score": c["score"],
                "snippet": c["text"][:200],
            }
            for c in result["chunks"]
        ],
    }
