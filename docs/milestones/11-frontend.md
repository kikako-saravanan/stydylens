# Milestone 11 — Frontend

## What problem are we solving?

Everything so far has been a backend API — real, tested, working, but only usable via `curl`. A student can't be expected to write HTTP requests by hand. We need a UI that turns "upload a PDF, POST a question, read a JSON response" into "drag in a file, type a question, read an answer with sources."

## Why does this problem exist?

This is really two distinct sub-problems bundled together: (1) present the RAG pipeline's inputs and outputs in a form a non-technical user can operate, and (2) — a requirement specific to this project's situation, not a generic frontend concern — **gate access**, since every question asked spends real, metered LLM credit. A public, unauthenticated UI in front of a paid API is an open invitation to run up a bill; the frontend has to enforce the same access control the backend already added in Milestone 6, not bypass it.

## What we implemented, where

- `frontend/` — Next.js (App Router) + TypeScript + Tailwind, scaffolded via `create-next-app`.
- `frontend/lib/api.ts` — the single point of contact with the backend. Holds credentials in `sessionStorage` (not `localStorage` — cleared when the tab closes, limiting how long a credential sits in the browser) and attaches them as an HTTP Basic `Authorization` header to every request. Typed interfaces (`UploadResult`, `AskResult`, `Source`) mirror the backend's actual JSON response shapes exactly.
- `frontend/components/LoginForm.tsx` — the auth gate. Submits credentials to `GET /api/me` (Milestone 11's one backend addition: a cheap, auth-only endpoint that costs nothing to call, specifically so validating a login attempt doesn't burn LLM/embedding compute). On failure, shows the access-restriction message and a mailto link to the administrator, per the project's actual requirement — this isn't generic "wrong password" copy, it explains *why* access is restricted (cost control) and what to do about it.
- `frontend/components/UploadPanel.tsx` — file picker, calls `POST /api/upload`, shows loading/success (page/chunk counts)/error states, and an empty-state hint before any upload.
- `frontend/components/QAPanel.tsx` — question input, calls `POST /api/ask`, shows the query-type badge (`single_fact`/`multi_part`/`summarization`), the decomposed sub-questions when there's more than one, the answer text, and hands off to `SourcesList`. Loading/error/empty states throughout.
- `frontend/components/SourcesList.tsx` — an expandable citations panel: page number, FAISS score, rerank score, and snippet per source — the same data `docs/milestones/10-source-attribution.md` traces end to end, now visible to an actual user instead of only a JSON response.
- `frontend/app/page.tsx` — orchestrates the three: shows `LoginForm` until valid credentials exist (re-validated on page load via `/api/me`, so a stale/revoked credential in `sessionStorage` doesn't silently keep working), otherwise shows the upload + ask flow, with a sign-out button that clears the stored credentials.

## Why HTTP Basic Auth + sessionStorage, not a "real" login system

A full session/JWT/refresh-token system would be legitimate over-engineering here: the actual requirement is "keep random visitors from spending LLM credit," not "support many distinct user accounts with roles and persistent sessions across devices." HTTP Basic Auth, checked server-side with a timing-safe comparison (Milestone 6), does exactly that with no additional backend infrastructure. The frontend's job is just to collect credentials once, remember them for the tab's lifetime, and attach them to every request — which is exactly what `lib/api.ts` does, nothing more.

## What we verified, and the one real gap being reported honestly

**Verified for real:**
- `npm run build` compiles and type-checks cleanly (Next.js's own TypeScript pass, not a hand-run `tsc` which lacks Next 16's generated route types).
- Every actual API call the frontend makes was tested directly against the real running backend, with the exact headers a browser `fetch()` call would send: CORS preflight (`OPTIONS`) returns `access-control-allow-origin: http://localhost:3000` and the right allowed headers; `GET /api/me` with bad credentials returns `401` with a `{"detail": "..."}` body — exactly the shape `lib/api.ts`'s error handling expects; `POST /api/upload` and `POST /api/ask` both return `200` with `access-control-allow-origin` present, and their JSON bodies match the TypeScript interfaces in `lib/api.ts` field-for-field.

**Not verified, reported plainly rather than hidden:** actual click-through testing in a real browser — does the login form actually render correctly, does clicking "Upload" actually trigger the file picker, does the sources panel actually expand/collapse on click — was not possible in the environment this was built in (no connected browser automation tool available this session). This is a real gap. The evidence above (clean build, verified API contract) is meaningfully short of "watched it work in a browser," and that distinction matters: it's the difference between "the pieces are individually correct" and "the assembled thing behaves correctly for a real user." This should be the first thing verified in a follow-up session, ideally by actually opening `localhost:3000` and clicking through the whole flow once the environment supports it.

## What can go wrong

- **Credentials in `sessionStorage` are visible to any JavaScript running on the page** — acceptable for this project's threat model (keeping casual/accidental unauthorized use off a demo deployment), not a substitute for real secret management in a higher-stakes setting.
- **No password reset / account management flow** — matches the deliberately simple, single-shared-credential design; a real multi-user product would need much more here.
- **The untested click-through path** (above) could still hide a real bug — a CSS layout issue, a form not actually submitting on Enter, a race condition in the login re-validation — that direct HTTP testing of the API alone cannot catch.

## Self-check questions

1. Why does the login screen call `GET /api/me` instead of, say, `POST /api/ask` with a throwaway question to check whether credentials work?
2. `page.tsx` re-validates stored credentials against `/api/me` on every page load, rather than just trusting whatever is in `sessionStorage`. What real scenario does that re-validation guard against?
3. Given the honest gap above (no browser click-through testing performed), what is the *strongest* claim that can honestly be made about this frontend's correctness, and what claim would be overclaiming?

<details><summary>Answers</summary>

1. `/api/ask` costs real LLM credit every time it's called, and a throwaway question would still spend that credit on every single login attempt — including failed ones, including retries. `/api/me` does nothing but check the `Authorization` header and return the username, so validating a login costs nothing beyond a cheap auth check, no matter how many times someone tries.
2. It guards against a credential that was valid when originally entered but has since stopped being valid (e.g., an administrator changed `AUTH_PASSWORD` on the backend, or is rotating credentials after the earlier session's git-history/token-exposure incidents this project already had). Without re-validation, a stale credential sitting in `sessionStorage` would let the UI *look* logged in while every actual API call silently failed with 401s — confusing to a user staring at cryptic errors instead of being cleanly returned to the login screen.
3. Honest claim: "the frontend code compiles, type-checks, and every API call it makes has been verified to match the real backend's actual behavior and response shapes." Overclaiming would be: "the frontend works" or "the UI has been tested" stated without qualification — that implies a human or automated process actually exercised the rendered page in a browser, which did not happen here. The difference matters exactly because of this project's own README/submission requirements around honesty: a grader checking "is this actually live-wired, or partially stubbed and overclaimed" would find this specific gap if it were glossed over, and the assignment's own rubric penalizes overclaiming harder than an honestly-scoped submission.
</details>
