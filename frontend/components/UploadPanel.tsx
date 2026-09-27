"use client";

import { ChangeEvent, useState } from "react";
import { ApiError, Credentials, DocumentInfo, UploadResult, uploadPdf } from "@/lib/api";

type Status = "idle" | "loading" | "success" | "error";

export function UploadPanel({
  creds,
  documents,
  onUploaded,
  onUseExisting,
}: {
  creds: Credentials;
  documents: DocumentInfo[];
  onUploaded: (filename: string) => void;
  onUseExisting: (filename: string) => void;
}) {
  // Set when the chosen file has the same name as an already-uploaded PDF,
  // so we can ask before uploading it a second time.
  const [duplicate, setDuplicate] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    if (documents.some((d) => d.source === file.name)) {
      setDuplicate(file.name);
      return;
    }
    setDuplicate(null);
    setFileName(file.name);
    setStatus("loading");
    setError(null);
    try {
      const res = await uploadPdf(file, creds);
      setResult(res);
      setStatus("success");
      onUploaded(file.name);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed unexpectedly.");
      setStatus("error");
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-surface p-6 shadow-card">
      <h2 className="text-base font-semibold text-fg">1. Upload a lecture PDF</h2>

      <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line-strong bg-surface-2 px-4 py-10 text-center transition hover:border-accent">
        <span className="text-sm font-medium text-fg">
          {status === "loading" ? "Uploading & indexing…" : "Click to choose a PDF"}
        </span>
        <input type="file" accept="application/pdf" className="hidden" onChange={handleChange} />
      </label>

      {duplicate && (
        <div className="mt-3 rounded-lg border border-accent bg-accent-soft p-3 text-sm text-accent-soft-fg">
          <p className="font-semibold">&ldquo;{duplicate}&rdquo; is already uploaded.</p>
          <p className="mt-1">Do you want to use the existing copy instead of uploading it again?</p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => {
                onUseExisting(duplicate);
                setDuplicate(null);
              }}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover"
            >
              Use existing
            </button>
            <button
              type="button"
              onClick={() => setDuplicate(null)}
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-fg transition hover:bg-surface-2"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {status === "idle" && !duplicate && (
        <p className="mt-3 text-sm text-muted">No document uploaded yet — questions won&apos;t have anything to search until you upload one.</p>
      )}

      {status === "success" && result && (
        <div className="mt-3 rounded-lg border border-ok-line bg-ok-bg p-3 text-sm text-ok-fg">
          <p className="font-medium">{fileName} indexed</p>
          <p className="mt-1 text-sm text-ok-fg">
            {result.page_count} page(s) → {result.chunk_count} chunk(s) · index now holds{" "}
            {result.index_total_chunks} chunk(s) total
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="mt-3 rounded-lg border border-err-line bg-err-bg p-3 text-sm text-err-fg">
          {error}
        </div>
      )}
    </section>
  );
}
