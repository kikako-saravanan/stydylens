"use client";

import { useState } from "react";
import { DocumentInfo } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  single_fact: "Single fact",
  multi_part: "Multi-part",
  summarization: "Summary",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function DocumentsSidebar({
  documents,
  selected,
  onSelect,
  onPickQuestion,
}: {
  documents: DocumentInfo[];
  selected: string | null;
  onSelect: (source: string) => void;
  onPickQuestion: (question: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(source: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }

  return (
    <aside className="rounded-2xl border border-line bg-surface p-5 shadow-card lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
      <h2 className="text-base font-semibold text-fg">Your documents</h2>
      <p className="mt-1 text-sm text-muted">
        Already uploaded PDFs. Pick one instead of uploading it again.
      </p>

      {documents.length === 0 ? (
        <p className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-muted">
          Nothing uploaded yet.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {documents.map((doc) => {
            const isSelected = doc.source === selected;
            const isOpen = expanded.has(doc.source);
            return (
              <li
                key={doc.source}
                className={`rounded-xl border p-3 ${
                  isSelected ? "border-accent bg-accent-soft" : "border-line bg-surface-2"
                }`}
              >
                <p className="break-words text-sm font-semibold text-fg">{doc.source}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {doc.page_count} page{doc.page_count === 1 ? "" : "s"} · {doc.chunk_count} chunks
                  {formatDate(doc.uploaded_at) && ` · ${formatDate(doc.uploaded_at)}`}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onSelect(doc.source)}
                    disabled={isSelected}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg transition hover:bg-accent-hover disabled:opacity-70"
                  >
                    {isSelected ? "In use" : "Use this PDF"}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggle(doc.source)}
                    aria-expanded={isOpen}
                    className="text-xs font-medium text-accent underline underline-offset-2 hover:text-accent-hover"
                  >
                    {doc.questions.length} question{doc.questions.length === 1 ? "" : "s"} asked
                    {isOpen ? " (hide)" : " (show)"}
                  </button>
                </div>

                {isOpen &&
                  (doc.questions.length === 0 ? (
                    <p className="mt-2 text-xs text-muted">No questions asked yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-1.5">
                      {doc.questions.map((q, i) => (
                        <li key={`${q.asked_at}-${i}`}>
                          <button
                            type="button"
                            onClick={() => {
                              onSelect(doc.source);
                              onPickQuestion(q.question);
                            }}
                            title="Use this question"
                            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-left text-xs text-fg transition hover:border-accent"
                          >
                            <span className="block break-words">{q.question}</span>
                            {q.query_type && (
                              <span className="mt-0.5 block text-[11px] text-muted">
                                {TYPE_LABEL[q.query_type] ?? q.query_type}
                              </span>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ))}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
