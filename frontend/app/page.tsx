"use client";

import { useEffect, useState } from "react";
import { checkLogin, clearCredentials, Credentials, loadCredentials } from "@/lib/api";
import { LoginForm } from "@/components/LoginForm";
import { UploadPanel } from "@/components/UploadPanel";
import { QAPanel } from "@/components/QAPanel";

export default function Home() {
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [hasDocument, setHasDocument] = useState(false);

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
    setHasDocument(false);
  }

  if (checkingSession) {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-gray-400">
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
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">StudyLens</h1>
          <p className="text-sm text-gray-500">Lecture Notes Q&amp;A Assistant</p>
        </div>
        <button
          onClick={handleSignOut}
          className="text-xs text-gray-400 underline underline-offset-2 hover:text-gray-600"
        >
          Sign out
        </button>
      </div>

      <div className="space-y-6">
        <UploadPanel creds={creds} onUploaded={() => setHasDocument(true)} />
        <QAPanel creds={creds} hasDocument={hasDocument} />
      </div>
    </main>
  );
}
