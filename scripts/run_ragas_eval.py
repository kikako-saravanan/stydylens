"""Milestone 9: RAGAS evaluation of the full StudyLens RAG pipeline.

Runs every question in data/eval/questions.json through the real chain
(routing -> retrieval -> rerank -> generation), then scores each
question/answer/context triple with three RAGAS metrics:

  - faithfulness: is the answer actually supported by the retrieved
    context, or does it contain unsupported claims?
  - answer_relevancy: does the answer actually address the question asked?
  - context_precision: of the retrieved chunks, how many were actually
    relevant, ranked against the reference answer?

Results are appended to data/eval/results.jsonl (one line per question,
per run) -- real output, not fabricated scores. Requires ANTHROPIC_API_KEY
(used both for generation and as the RAGAS judge LLM) and a populated
FAISS index (this script builds one from the sample PDF if empty).
"""

import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

warnings.filterwarnings("ignore", category=DeprecationWarning, module="ragas")

from langchain_anthropic import ChatAnthropic  # noqa: E402
from langchain_community.embeddings import HuggingFaceEmbeddings as LCHuggingFaceEmbeddings  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import answer_relevancy, context_precision, faithfulness  # noqa: E402

from app.chunking.chunker import chunk_pages  # noqa: E402
from app.ingestion.pdf_loader import extract_pages  # noqa: E402
from app.rag.chain import build_chain  # noqa: E402
from app.retrieval.faiss_store import add_chunks, count  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "data" / "sample_pdfs" / "os-concepts-ch5-cpu-scheduling-excerpt.pdf"
QUESTIONS_PATH = ROOT / "data" / "eval" / "questions.json"
RESULTS_PATH = ROOT / "data" / "eval" / "results.jsonl"


def ensure_index_populated() -> None:
    if count() > 0:
        print(f"Index already has {count()} chunks; skipping ingestion.")
        return
    print(f"Index is empty; ingesting {PDF_PATH.name}...")
    pages = extract_pages(PDF_PATH)
    chunks = chunk_pages(pages)
    total = add_chunks(chunks)
    print(f"Indexed {total} chunks.")


def main() -> None:
    ensure_index_populated()
    questions = json.loads(QUESTIONS_PATH.read_text())
    print(f"Running {len(questions)} eval questions through the full RAG chain...")

    chain = build_chain()
    samples = []
    run_meta = []

    for i, item in enumerate(questions, start=1):
        print(f"  [{i}/{len(questions)}] {item['question'][:70]}")
        result = chain.invoke({"question": item["question"], "k": None})
        full_contexts = [c["text"] for c in result["reranked_chunks"]]

        samples.append(
            SingleTurnSample(
                user_input=item["question"],
                response=result["answer"],
                retrieved_contexts=full_contexts,
                reference=item["reference_answer"],
            )
        )
        run_meta.append(
            {
                "question": item["question"],
                "answer": result["answer"],
                "query_type": result["retrieval"]["query_type"],
                "num_contexts": len(full_contexts),
            }
        )

    print("\nScoring with RAGAS (faithfulness, answer_relevancy, context_precision)...")
    dataset = EvaluationDataset(samples=samples)
    # Deliberately NOT _primary_llm() (claude-sonnet-5): RAGAS's internal
    # judge calls always pass an explicit `temperature`, which current-
    # generation Claude models reject outright (400: "temperature is
    # deprecated for this model"). claude-haiku-4-5 still accepts it, and
    # is cheaper for the many per-metric judge calls RAGAS makes.
    judge_llm = ChatAnthropic(
        model=os.getenv("RAGAS_JUDGE_MODEL", "claude-haiku-4-5"), temperature=0.0
    )
    ragas_llm = LangchainLLMWrapper(judge_llm)
    # The DEPRECATED answer_relevancy metric expects the classic LangChain
    # embeddings interface (.embed_query()) via LangchainEmbeddingsWrapper --
    # NOT ragas's newer ragas.embeddings.HuggingFaceEmbeddings, which
    # implements a different (BaseRagasEmbedding) interface without
    # embed_query and fails with AttributeError if used here.
    ragas_embeddings = LangchainEmbeddingsWrapper(
        LCHuggingFaceEmbeddings(
            model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        )
    )

    eval_result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    df = eval_result.to_pandas()

    timestamp = datetime.now(timezone.utc).isoformat()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        for meta, (_, row) in zip(run_meta, df.iterrows()):
            f.write(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "question": meta["question"],
                        "answer_preview": meta["answer"][:200],
                        "query_type": meta["query_type"],
                        "num_contexts": meta["num_contexts"],
                        "faithfulness": _clean(row.get("faithfulness")),
                        "answer_relevancy": _clean(row.get("answer_relevancy")),
                        "context_precision": _clean(row.get("context_precision")),
                    }
                )
                + "\n"
            )

    print(f"\nWrote {len(df)} results to {RESULTS_PATH.relative_to(ROOT)}")
    print("\n=== Summary (mean across all questions) ===")
    for metric in ["faithfulness", "answer_relevancy", "context_precision"]:
        if metric in df.columns:
            print(f"  {metric}: {df[metric].mean():.4f}")


def _clean(value):
    """NaN (a metric can't be computed for some edge-case inputs) isn't
    valid JSON -- store it as null instead of silently writing 'NaN'."""
    if value is None:
        return None
    try:
        if value != value:  # NaN != NaN is the standard float NaN check
            return None
    except TypeError:
        pass
    return float(value)


if __name__ == "__main__":
    main()
