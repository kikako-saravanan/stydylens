"use client";

import { FormEvent, useState } from "react";
import { ApiError, AskResult, Credentials, askQuestion } from "@/lib/api";
import { SourcesList } from "./SourcesList";

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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setStatus("loading");
    setError(null);
    try {
      const res = await askQuestion(question, creds);
      setResult(res);
      setStatus("success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong asking that question.");
      setStatus("error");
    }
  }

  return (
    <section className="rounded-xl border border-black/10 p-5">
      <h2 className="text-sm font-semibold text-gray-700">2. Ask a question</h2>

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
        </p>
      )}

      {status === "error" && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
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
