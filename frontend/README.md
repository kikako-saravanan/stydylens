# StudyLens frontend

Next.js (App Router) + TypeScript + Tailwind. A minimal UI over the StudyLens backend: sign in, upload a lecture PDF, ask questions, see grounded answers with expandable source citations.

## Setup

```bash
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your backend if not localhost:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The backend must be running (see `../backend/README.md`... actually see the root `README.md`) and `CORS_ORIGINS` there must include this frontend's origin (`http://localhost:3000` by default).

## What's here

- `app/page.tsx` — top-level flow: login gate → upload panel → ask panel.
- `lib/api.ts` — the only place that talks to the backend. Credentials are HTTP Basic Auth, held in `sessionStorage` (cleared when the tab closes) and attached to every request — never stored in a cookie or sent anywhere but this backend.
- `components/LoginForm.tsx` — validates credentials against the cheap `GET /api/me` endpoint (no LLM/embedding cost). On failure, explains the app is access-restricted to control LLM API costs and who to email for credentials.
- `components/UploadPanel.tsx`, `components/QAPanel.tsx`, `components/SourcesList.tsx` — the actual upload/ask/citations UI, each with loading, success, error, and empty states.

## Known limitation

Visual/click-through testing of this UI was not possible in the environment this was built in (no connected browser automation tool). It was verified as far as possible without one: `npm run build` type-checks and compiles cleanly, and every API call the frontend makes was independently verified via direct HTTP requests (correct CORS headers, correct response shapes matching the TypeScript interfaces in `lib/api.ts`) against the real running backend. Actually clicking through the UI in a browser before considering this done is a real gap — do that before treating this milestone as fully verified.
