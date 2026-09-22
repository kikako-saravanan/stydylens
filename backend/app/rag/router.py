import logging
import os
from functools import lru_cache
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You classify a student's question about their course material into
exactly one type, and produce the sub-questions we should retrieve evidence for.

Types:
- "single_fact": one focused question about one concept. sub_questions = a
  list containing just the original question, unchanged.
- "multi_part": the question asks about two or more distinct things (often
  joined by "and", "vs", "compare", or containing multiple question marks).
  sub_questions = one focused, standalone question per distinct part, each
  rewritten so it makes sense on its own without the rest of the original
  question.
- "summarization": the question asks for an overview/summary of the
  material rather than one specific fact. sub_questions = 3-5 broad
  questions that together probe the main topics likely covered, so
  retrieval gathers a representative spread of the material.

Always return at least one sub-question. For single_fact, always exactly
one sub-question — the original question, unchanged.
"""


class RoutedQuery(BaseModel):
    query_type: Literal["single_fact", "multi_part", "summarization"] = Field(
        description="The classified type of the question."
    )
    sub_questions: list[str] = Field(
        description="One or more standalone questions to retrieve evidence for."
    )


@lru_cache(maxsize=1)
def _router_llm():
    return ChatAnthropic(model=os.getenv("LLM_MODEL", "claude-sonnet-5")).with_structured_output(
        RoutedQuery
    )


def route_query(question: str) -> RoutedQuery:
    """Classify the question and decompose it into retrievable sub-questions.

    Routing is an enhancement over plain retrieval, not a hard dependency —
    if the router call fails for any reason, we degrade to treating the
    question as a single fact lookup (the Milestone 6 behavior) rather than
    failing the whole request over a classification step.
    """
    try:
        return _router_llm().invoke(
            [SystemMessage(content=ROUTER_SYSTEM_PROMPT), HumanMessage(content=question)]
        )
    except Exception as e:
        logger.warning("Query routing failed (%s); treating as single_fact.", e)
        return RoutedQuery(query_type="single_fact", sub_questions=[question])
