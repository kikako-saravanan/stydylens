"use client";

import { ChangeEvent, useState } from "react";
import { ApiError, Credentials, UploadResult, uploadPdf } from "@/lib/api";

type Status = "idle" | "loading" | "success" | "error";

export function UploadPanel({
  creds,
  onUploaded,
}: {
  creds: Credentials;
  onUploaded: () => void;
}) {
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setStatus("loading");
    setError(null);
    try {
      const res = await uploadPdf(file, creds);
      setResult(res);
      setStatus("success");
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed unexpectedly.");
      setStatus("error");
    } finally {
      e.target.value = "";
    }
  }

  return (
    <section className="rounded-xl border border-black/10 p-5">
      <h2 className="text-sm font-semibold text-gray-700">1. Upload a lecture PDF</h2>

      <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-black/15 px-4 py-8 text-center hover:border-black/30">
        <span className="text-sm text-gray-600">
          {status === "loading" ? "Uploading & indexing…" : "Click to choose a PDF"}
        </span>
        <input type="file" accept="application/pdf" className="hidden" onChange={handleChange} />
      </label>

      {status === "idle" && (
        <p className="mt-3 text-xs text-gray-400">No document uploaded yet — questions won&apos;t have anything to search until you upload one.</p>
      )}

      {status === "success" && result && (
        <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          <p className="font-medium">{fileName} indexed</p>
          <p className="mt-1 text-xs text-green-700">
            {result.page_count} page(s) → {result.chunk_count} chunk(s) · index now holds{" "}
            {result.index_total_chunks} chunk(s) total
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </section>
  );
}
