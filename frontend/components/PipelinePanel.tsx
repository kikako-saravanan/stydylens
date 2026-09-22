"use client";

import { PipelineEvent, PipelineStage } from "@/lib/api";

const STAGES: { key: PipelineStage; title: string; blurb: string }[] = [
  {
    key: "routing",
    title: "1. Query routing & decomposition",
    blurb: "Classifies the question (single fact / multi-part / summary) and, if needed, splits it into standalone sub-questions.",
  },
  {
    key: "retrieval",
    title: "2. Retrieval",
    blurb: "Embeds each sub-question and searches the FAISS index for the most similar chunks, merging results across sub-questions.",
  },
  {
    key: "reranking",
    title: "3. Re-ranking",
    blurb: "A cross-encoder re-scores the merged candidates against the original question — often reordering FAISS's initial ranking.",
  },
  {
    key: "generation",
    title: "4. Generation",
    blurb: "The reranked chunks become the LLM's context. The model must answer only from that context, or say it can't find an answer.",
  },
];

type StageState = "pending" | "running" | "done";

function stateFor(events: PipelineEvent[], stage: PipelineStage): StageState {
  const stageEvents = events.filter((e) => e.stage === stage);
  if (stageEvents.some((e) => e.status === "done")) return "done";
  if (stageEvents.some((e) => e.status === "start")) return "running";
  return "pending";
}

function eventFor(events: PipelineEvent[], stage: PipelineStage, status: "start" | "done") {
  return events.find((e) => e.stage === stage && e.status === status);
}

const DOT: Record<StageState, string> = {
  pending: "bg-gray-200",
  running: "bg-amber-400 animate-pulse",
  done: "bg-green-500",
};

export function PipelinePanel({ events }: { events: PipelineEvent[] }) {
  const errorEvent = events.find((e) => e.stage === "error");

  return (
    <div className="mt-4 space-y-3 rounded-lg border border-black/10 bg-gray-50 p-4">
      <p className="text-xs font-medium text-gray-500">Pipeline (live)</p>

      {STAGES.map(({ key, title, blurb }) => {
        const state = stateFor(events, key);
        const doneEvent = eventFor(events, key, "done");

        return (
          <div key={key} className="flex gap-3">
            <span className={`mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full ${DOT[state]}`} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-800">{title}</p>
              <p className="text-xs text-gray-500">{blurb}</p>

              {state === "done" && key === "routing" && doneEvent && (
                <div className="mt-1.5 text-xs text-gray-700">
                  <span className="rounded-full bg-gray-200 px-2 py-0.5 font-medium">
                    {doneEvent.query_type}
                  </span>
                  {(doneEvent.sub_questions?.length ?? 0) > 1 && (
                    <ul className="mt-1 list-inside list-disc text-gray-500">
                      {doneEvent.sub_questions!.map((sq) => (
                        <li key={sq}>{sq}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {state === "done" && key === "retrieval" && doneEvent && (
                <p className="mt-1.5 text-xs text-gray-700">
                  {doneEvent.candidate_count} unique candidate chunk(s) retrieved across{" "}
                  {doneEvent.retrieval_trace?.length ?? 1} sub-question(s)
                </p>
              )}

              {state === "done" && key === "reranking" && doneEvent && (
                <p className="mt-1.5 text-xs text-gray-700">
                  Top result{" "}
                  {doneEvent.pre_rerank_order?.[0] === doneEvent.post_rerank_order?.[0]
                    ? "unchanged after reranking"
                    : "changed after reranking"}{" "}
                  — kept top {doneEvent.post_rerank_order?.length} of{" "}
                  {doneEvent.pre_rerank_order?.length} candidates
                </p>
              )}

              {state === "done" && key === "generation" && (
                <p className="mt-1.5 text-xs text-gray-700">Answer generated — see below.</p>
              )}
            </div>
          </div>
        );
      })}

      {errorEvent && (
        <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          {errorEvent.message}
        </div>
      )}
    </div>
  );
}
