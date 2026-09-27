"use client";

import { FormEvent, useState } from "react";
import {
  ApiError,
  AskResult,
  Credentials,
  PipelineEvent,
  askQuestion,
  explainFirstPrinciples,
  streamAsk,
} from "@/lib/api";
import { SourcesList } from "./SourcesList";
import { PipelinePanel } from "./PipelinePanel";
import { SimpleMarkdown } from "./SimpleMarkdown";

type Status = "idle" | "loading" | "success" | "error";

const QUERY_TYPE_LABEL: Record<AskResult["query_type"], string> = {
  single_fact: "Single fact",
  multi_part: "Multi-part",
  summarization: "Summary",
};

export function QAPanel({
  creds,
  selected,
  question,
  onQuestionChange: setQuestion,
  onAsked,
}: {
  creds: Credentials;
  selected: string | null;
  question: string;
  onQuestionChange: (q: string) => void;
  onAsked: () => void;
}) {
  const hasDocument = selected !== null;
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPipeline, setShowPipeline] = useState(false);
  const [pipelineEvents, setPipelineEvents] = useState<PipelineEvent[]>([]);
  const [explainStatus, setExplainStatus] = useState<Status>("idle");
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explainError, setExplainError] = useState<string | null>(null);

  async function handleExplain() {
    if (!result) return;
    setExplainStatus("loading");
    setExplainError(null);
    try {
      const res = await explainFirstPrinciples(result, creds);
      setExplanation(res.explanation);
      setExplainStatus("success");
    } catch (err) {
      setExplainError(err instanceof ApiError ? err.message : "Could not generate the explanation.");
      setExplainStatus("error");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setStatus("loading");
    setError(null);
    setResult(null);
    setPipelineEvents([]);
    setExplanation(null);
    setExplainError(null);
    setExplainStatus("idle");

    if (!showPipeline) {
      try {
        const res = await askQuestion(question, creds, selected);
        setResult(res);
        setStatus("success");
        onAsked();
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
      for await (const event of streamAsk(question, creds, selected)) {
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
          onAsked();
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong asking that question.");
      setStatus("error");
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-surface p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-fg">2. Ask a question</h2>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={showPipeline}
            onChange={(e) => setShowPipeline(e.target.checked)}
            className="h-4 w-4 accent-[var(--accent)]"
          />
          Show pipeline stages
        </label>
      </div>

      <p className="mt-2 text-sm text-muted">
        {selected ? (
          <>
            Asking about <span className="font-semibold text-fg">{selected}</span>
          </>
        ) : (
          "Select or upload a PDF to ask about."
        )}
      </p>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            hasDocument
              ? "e.g. What is round robin scheduling?"
              : "Upload a PDF first…"
          }
          className="min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 py-2.5 text-base text-fg placeholder:text-subtle outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
        />
        <button
          type="submit"
          disabled={status === "loading" || !question.trim() || !hasDocument}
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover disabled:opacity-50"
        >
          {status === "loading" ? "Thinking…" : "Ask"}
        </button>
      </form>

      {status === "idle" && (
        <p className="mt-3 text-sm text-muted">
          Ask something the uploaded lecture covers, or something outside it — StudyLens will say so honestly if it can&apos;t find an answer.
          {" "}Check &quot;Show pipeline stages&quot; to watch routing → retrieval → reranking → generation happen live.
        </p>
      )}

      {status === "error" && (
        <div className="mt-4 rounded-lg border border-err-line bg-err-bg p-3 text-sm text-err-fg">
          {error}
        </div>
      )}

      {showPipeline && (status === "loading" || pipelineEvents.length > 0) && (
        <PipelinePanel events={pipelineEvents} />
      )}

      {status === "success" && result && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent-soft-fg">
              {QUERY_TYPE_LABEL[result.query_type]}
            </span>
            {result.sub_questions.length > 1 && (
              <span className="text-sm text-muted">
                decomposed into {result.sub_questions.length} sub-questions
              </span>
            )}
          </div>

          {result.sub_questions.length > 1 && (
            <ul className="mt-2 list-inside list-disc text-sm text-muted">
              {result.sub_questions.map((sq) => (
                <li key={sq}>{sq}</li>
              ))}
            </ul>
          )}

          <p className="mt-4 whitespace-pre-wrap text-base leading-7 text-fg">
            {result.answer}
          </p>

          <div className="mt-5">
            <button
              type="button"
              onClick={handleExplain}
              disabled={explainStatus === "loading"}
              className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm font-semibold text-accent-soft-fg transition hover:bg-surface-2 disabled:opacity-60"
            >
              {explainStatus === "loading"
                ? "Explaining…"
                : explanation
                  ? "Explain again"
                  : "Explain from first principles"}
            </button>
          </div>

          {explainStatus === "error" && (
            <div className="mt-3 rounded-lg border border-err-line bg-err-bg p-3 text-sm text-err-fg">
              {explainError}
            </div>
          )}

          {explanation && (
            <div className="mt-4 rounded-xl border border-line bg-surface-2 p-5">
              <p className="text-sm font-semibold text-accent">First-principles explanation</p>
              <SimpleMarkdown text={explanation} />
            </div>
          )}

          <SourcesList sources={result.sources} />
        </div>
      )}
    </section>
  );
}
