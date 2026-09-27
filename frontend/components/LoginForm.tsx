"use client";

import { FormEvent, useState } from "react";
import { checkLogin, saveCredentials } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

// Set NEXT_PUBLIC_CONTACT_EMAIL in frontend/.env.local to show a contact address.
const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL;

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await checkLogin({ username, password });
      saveCredentials({ username, password });
      onSuccess();
    } catch {
      setError("denied");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto mt-16 w-full max-w-sm rounded-2xl border border-line bg-surface p-8 shadow-card">
      <div className="flex items-start justify-between">
        <h1 className="text-2xl font-bold tracking-tight">StudyLens</h1>
        <ThemeToggle />
      </div>
      <p className="mt-1 text-sm text-muted">Lecture Notes Q&amp;A Assistant</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-fg">
            Username
          </label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2.5 text-base text-fg placeholder:text-subtle outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-fg">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2.5 text-base text-fg placeholder:text-subtle outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-accent px-3 py-2.5 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover disabled:opacity-50"
        >
          {loading ? "Checking…" : "Sign in"}
        </button>
      </form>

      {error && (
        <div className="mt-5 rounded-lg border border-err-line bg-err-bg p-3 text-sm text-err-fg">
          <p className="font-medium">Access restricted</p>
          <p className="mt-1">
            This app is access-restricted to control LLM API usage costs.{" "}
            {CONTACT_EMAIL ? (
              <>
                Email{" "}
                <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
                  {CONTACT_EMAIL}
                </a>{" "}
                to request credentials.
              </>
            ) : (
              "Ask the administrator to request credentials."
            )}
          </p>
        </div>
      )}
    </div>
  );
}
