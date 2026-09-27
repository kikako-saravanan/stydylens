from langchain_core.messages import HumanMessage, SystemMessage

from app.rag.llm_provider import generate

EXPLAIN_SYSTEM_PROMPT = (
    "You are StudyLens's tutor. A student was given an answer grounded in their "
    "course material and now wants it explained from first principles.\n\n"
    "Explain the answer by starting from the most basic, undeniable ideas and "
    "building up step by step until the answer follows naturally:\n"
    "1. **The core problem** - what problem does this concept exist to solve?\n"
    "2. **Building blocks** - the fundamental ideas needed, defined simply, "
    "assuming no prior knowledge beyond them.\n"
    "3. **Step-by-step derivation** - how those blocks combine, each step "
    "following from the previous one, to reach the answer.\n"
    "4. **A concrete example** - a small worked example or analogy.\n"
    "5. **Why it matters / trade-offs** - one or two sentences.\n\n"
    "Rules:\n"
    "- Stay consistent with the given answer and course excerpts; never "
    "contradict them.\n"
    "- You may add general background to make the reasoning complete, but label "
    "anything not found in the excerpts with \"(background)\".\n"
    "- If the answer says the material didn't contain the information, say "
    "there is nothing to explain yet and suggest uploading relevant material.\n"
    "- Use short paragraphs and plain language. Use Markdown headings for the "
    "steps above."
)

MAX_ANSWER_CHARS = 6000
MAX_EXCERPT_CHARS = 1200
MAX_EXCERPTS = 8


def explain_first_principles(question: str, answer: str, excerpts: list[str]) -> str:
    context = "\n\n".join(
        f"[Excerpt {i}]\n{text[:MAX_EXCERPT_CHARS]}"
        for i, text in enumerate(excerpts[:MAX_EXCERPTS], start=1)
    ) or "(no excerpts provided)"
    return generate(
        [
            SystemMessage(content=EXPLAIN_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Question: {question}\n\n"
                    f"Answer given to the student:\n{answer[:MAX_ANSWER_CHARS]}\n\n"
                    f"Course excerpts the answer was based on:\n{context}"
                )
            ),
        ]
    )
