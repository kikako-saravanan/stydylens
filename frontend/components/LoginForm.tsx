"use client";

import { FormEvent, useState } from "react";
import { checkLogin, saveCredentials } from "@/lib/api";

const CONTACT_EMAIL = "[REDACTED_EMAIL_ADDRESS_1]";

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
    <div className="mx-auto mt-16 w-full max-w-sm rounded-xl border border-black/10 p-8 shadow-sm">
      <h1 className="text-xl font-semibold">StudyLens</h1>
      <p className="mt-1 text-sm text-gray-500">Lecture Notes Q&amp;A Assistant</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label htmlFor="username" className="mb-1 block text-sm font-medium">
            Username
          </label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40"
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-black px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Checking…" : "Sign in"}
        </button>
      </form>

      {error && (
        <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <p className="font-medium">Access restricted</p>
          <p className="mt-1">
            This app is access-restricted to control LLM API usage costs. Email{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
              {CONTACT_EMAIL}
            </a>{" "}
            to request credentials.
          </p>
        </div>
      )}
    </div>
  );
}
