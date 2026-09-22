"use client";

import { FormEvent, useState } from "react";
import {
  ApiError,
  AskResult,
  Credentials,
  PipelineEvent,
  askQuestion,
  streamAsk,
} from "@/lib/api";
import { SourcesList } from "./SourcesList";
import { PipelinePanel } from "./PipelinePanel";

type Status = "idle" | "loading" | "success" | "error";

const QUERY_TYPE_LABEL: Record<AskResult["query_type"], string> = {
  single_fact: "Single fact",
  multi_part: "Multi-part",
  summarization: "Summary",
};

export function QAPanel({ creds, hasDocument }: { creds: Credentials; hasDocument: boolean }) {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPipeline, setShowPipeline] = useState(false);
  const [pipelineEvents, setPipelineEvents] = useState<PipelineEvent[]>([]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setStatus("loading");
    setError(null);
    setResult(null);
    setPipelineEvents([]);

    if (!showPipeline) {
      try {
        const res = await askQuestion(question, creds);
        setResult(res);
        setStatus("success");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong asking that question.");
        setStatus("error");
      }
      return;
    }

    // Pipeline mode: consume the SSE stream, updating the visualization
    // live as each real stage event arrives, rather than waiting for one
    // final response.
    try {
      for await (const event of streamAsk(question, creds)) {
        if (event.stage === "error") {
          setError(event.message ?? "Something went wrong asking that question.");
          setStatus("error");
          return;
        }
        setPipelineEvents((prev) => [...prev, event]);
        if (event.stage === "complete") {
          setResult({
            question: event.question ?? question,
            answer: event.answer ?? "",
            query_type: event.query_type ?? "single_fact",
            sub_questions: event.sub_questions ?? [],
            retrieval_trace: event.retrieval_trace ?? [],
            pre_rerank_order: event.pre_rerank_order ?? [],
            post_rerank_order: event.post_rerank_order ?? [],
            sources: event.sources ?? [],
          });
          setStatus("success");
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong asking that question.");
      setStatus("error");
    }
  }

  return (
    <section className="rounded-xl border border-black/10 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">2. Ask a question</h2>
        <label className="flex items-center gap-1.5 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={showPipeline}
            onChange={(e) => setShowPipeline(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          Show pipeline stages
        </label>
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            hasDocument
              ? "e.g. What is round robin scheduling?"
              : "Upload a PDF first…"
          }
          className="flex-1 rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40"
        />
        <button
          type="submit"
          disabled={status === "loading" || !question.trim()}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {status === "loading" ? "Thinking…" : "Ask"}
        </button>
      </form>

      {status === "idle" && (
        <p className="mt-3 text-xs text-gray-400">
          Ask something the uploaded lecture covers, or something outside it — StudyLens will say so honestly if it can&apos;t find an answer.
          {" "}Check &quot;Show pipeline stages&quot; to watch routing → retrieval → reranking → generation happen live.
        </p>
      )}

      {status === "error" && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {showPipeline && (status === "loading" || pipelineEvents.length > 0) && (
        <PipelinePanel events={pipelineEvents} />
      )}

      {status === "success" && result && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
              {QUERY_TYPE_LABEL[result.query_type]}
            </span>
            {result.sub_questions.length > 1 && (
              <span className="text-xs text-gray-400">
                decomposed into {result.sub_questions.length} sub-questions
              </span>
            )}
          </div>

          {result.sub_questions.length > 1 && (
            <ul className="mt-2 list-inside list-disc text-xs text-gray-500">
              {result.sub_questions.map((sq) => (
                <li key={sq}>{sq}</li>
              ))}
            </ul>
          )}

          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
            {result.answer}
          </p>

          <SourcesList sources={result.sources} />
        </div>
      )}
    </section>
  );
}
