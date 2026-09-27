"use client";

import { useCallback, useEffect, useState } from "react";
import {
  checkLogin,
  clearCredentials,
  Credentials,
  DocumentInfo,
  listDocuments,
  loadCredentials,
} from "@/lib/api";
import { LoginForm } from "@/components/LoginForm";
import { UploadPanel } from "@/components/UploadPanel";
import { QAPanel } from "@/components/QAPanel";
import { DocumentsSidebar } from "@/components/DocumentsSidebar";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function Home() {
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  const refreshDocuments = useCallback(async (c: Credentials) => {
    try {
      setDocuments(await listDocuments(c));
    } catch {
      // The sidebar is a convenience; failing to load it shouldn't block asking.
    }
  }, []);

  // Load the list of already-uploaded PDFs once signed in.
  useEffect(() => {
    if (!creds) return;
    let cancelled = false;
    listDocuments(creds)
      .then((docs) => {
        if (!cancelled) setDocuments(docs);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [creds]);

  // On load, re-validate any credentials already sitting in sessionStorage
  // (e.g. after a page refresh) rather than trusting they're still good.
  useEffect(() => {
    const stored = loadCredentials();
    if (!stored) {
      setCheckingSession(false);
      return;
    }
    checkLogin(stored)
      .then(() => setCreds(stored))
      .catch(() => clearCredentials())
      .finally(() => setCheckingSession(false));
  }, []);

  function handleSignOut() {
    clearCredentials();
    setCreds(null);
    setDocuments([]);
    setSelected(null);
    setQuestion("");
  }

  if (checkingSession) {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-muted">
        Loading…
      </main>
    );
  }

  if (!creds) {
    return (
      <main className="flex flex-1 flex-col px-4">
        <LoginForm onSuccess={() => setCreds(loadCredentials())} />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">StudyLens</h1>
          <p className="text-sm text-muted">Lecture Notes Q&amp;A Assistant</p>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={handleSignOut}
            className="h-9 rounded-lg border border-line bg-surface px-3 text-sm font-medium text-fg transition hover:bg-surface-2"
          >
            Sign out
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
        <DocumentsSidebar
          documents={documents}
          selected={selected}
          onSelect={setSelected}
          onPickQuestion={setQuestion}
        />

        <div className="space-y-6">
          {documents.length > 0 && selected === null && (
            <div className="rounded-2xl border border-accent bg-accent-soft p-5 text-accent-soft-fg">
              <p className="font-semibold">
                You already have {documents.length} uploaded PDF{documents.length === 1 ? "" : "s"}.
              </p>
              <p className="mt-1 text-sm">
                Do you want to use an existing one? Pick it from the list, or upload a new PDF below.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {documents.map((d) => (
                  <button
                    key={d.source}
                    type="button"
                    onClick={() => setSelected(d.source)}
                    className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover"
                  >
                    Use {d.source}
                  </button>
                ))}
              </div>
            </div>
          )}

          <UploadPanel
            creds={creds}
            documents={documents}
            onUploaded={(filename) => {
              setSelected(filename);
              refreshDocuments(creds);
            }}
            onUseExisting={setSelected}
          />
          <QAPanel
            key={selected ?? "none"}
            creds={creds}
            selected={selected}
            question={question}
            onQuestionChange={setQuestion}
            onAsked={() => refreshDocuments(creds)}
          />
        </div>
      </div>
    </main>
  );
}
