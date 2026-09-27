"use client";

import { useState } from "react";
import { Source } from "@/lib/api";

export function SourcesList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(true);

  if (sources.length === 0) {
    return (
      <p className="mt-3 text-sm text-muted">
        No source chunks were retrieved for this answer.
      </p>
    );
  }

  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-sm font-medium text-accent underline underline-offset-2 hover:text-accent-hover"
      >
        {open ? "Hide" : "Show"} {sources.length} source{sources.length === 1 ? "" : "s"}
      </button>

      {open && (
        <ul className="mt-2 space-y-2">
          {sources.map((s) => (
            <li key={s.chunk_id} className="rounded-lg border border-line bg-surface-2 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
                <span className="font-semibold text-fg">{s.source}</span>
                <span>page {s.page}</span>
                <span>faiss {s.faiss_score.toFixed(3)}</span>
                <span>rerank {s.rerank_score.toFixed(3)}</span>
              </div>
              <p className="mt-1.5 leading-relaxed text-fg">{s.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
