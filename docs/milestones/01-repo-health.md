# Milestone 1 — Repository + Health

## What problem are we solving?

Code sitting on disk can't be talked to by anything — not a browser, not a future frontend, not a deployment platform's health monitor. We need it running as a **live process** other programs can send requests to and get responses from over a network (even if that network is just `localhost`).

## Why does this problem exist?

The frontend and backend are two separate, independently-running programs — possibly on different machines entirely once deployed. They don't share memory or a call stack. The only way for a browser's JavaScript to ask Python code to do something is for that Python code to expose itself as a network service speaking a protocol the browser already knows: HTTP.

## First principles

```
You want: browser -> "run this Python function for me" -> get the result back
                        |
              browser and Python process are different, isolated programs
                        |
        they need a shared protocol to talk over a network: HTTP
        (a text-based request/response protocol)
                        |
        Python needs to LISTEN for HTTP requests and map
        "GET /health" to "call this specific function"
                        |
              that's a "web server"
                        |
   writing raw socket/HTTP-parsing code yourself for every route
   would be enormous and easy to get wrong
                        |
        use a framework that already solved this: FastAPI
   (runs on Starlette + Uvicorn — Uvicorn opens the network socket
    and speaks HTTP; FastAPI lets you write `@app.get("/health")`
    instead of parsing raw bytes)
```

An **endpoint** is a URL path mapped to a Python function. When a GET request for that exact path arrives, FastAPI calls the function and turns the return value into an HTTP response.

**Why `/health` first, before anything else?** It's deliberately the dumbest possible endpoint — it proves only "the process is alive and can respond." Every later, more complex endpoint fails in more confusing ways (model loading errors, bad PDFs, timeouts). A zero-logic endpoint gives a baseline: if `/health` fails, the problem is infrastructure, not RAG logic. Deployment platforms also poll `/health`-style endpoints to decide whether an instance should receive traffic.

## What we implemented, where

- `backend/app/main.py` — the FastAPI app object, CORS middleware, `/health` route.
- `backend/requirements.txt` — `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv` — only what's imported, nothing speculative.
- `backend/.venv/` — isolated Python environment.
- `backend/.venv/pip.conf` — points pip at this machine's corporate CA bundle (this network intercepts TLS); scoped to this venv only, machine-specific, gitignored.
- `.env.example`, `.gitignore`, `README.md` (with the chosen domain stated at the top, per submission requirements).

## Code walkthrough

```python
app = FastAPI(title="StudyLens API")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}
```

`CORSMiddleware` matters because a browser enforces the same-origin policy: JavaScript on `localhost:3000` is blocked by the *browser itself* from reading a response from `localhost:8000` unless that response carries an `Access-Control-Allow-Origin` header naming the calling origin. `CORS_ORIGINS` is read from `.env` rather than hardcoded, because the allowed origin differs between local dev and production — the same "environment-configurable, never hardcoded" pattern the assignment requires for config in general, not just secrets.

## Why this design vs. alternatives

Flask is simpler but synchronous-by-default with no built-in request/response validation. FastAPI was chosen because: it's async-native (matters once we're calling an LLM API and don't want one slow request blocking the server); it integrates with Pydantic for automatic request validation; it auto-generates OpenAPI docs at `/docs` for manual testing before a frontend exists.

## What happens at runtime

```
curl http://127.0.0.1:8000/health
   -> TCP connection to Uvicorn's listening socket
   -> Uvicorn parses "GET /health"
   -> Starlette matches the path to health()
   -> health() returns {"status": "ok"}
   -> FastAPI serializes to JSON, attaches CORS header, status 200
   -> curl prints the response
```

## How we verified it

```
$ curl -s -w '\nHTTP_STATUS:%{http_code}\n' http://127.0.0.1:8000/health
{"status":"ok"}
HTTP_STATUS:200
```
Server log confirmed: `INFO: 127.0.0.1:64889 - "GET /health HTTP/1.1" 200 OK`.

## What can go wrong

- **Port already in use** — Uvicorn fails to start; fix with a different `--port`, not a code change.
- **CORS origin mismatch in production** — if the deployed backend's `CORS_ORIGINS` doesn't list the exact deployed frontend URL, requests get silently blocked by the *browser*, not the server — server logs show 200s while the frontend shows a CORS error in devtools. The single most common "why doesn't my deployed app work" bug.
- **Binding to `127.0.0.1` instead of `0.0.0.0`** in a container means the platform's health check can't reach it from outside.
- **This machine's corporate SSL proxy** breaks a fresh `pip install` if the venv is recreated without the CA-bundle fix.

## Self-check questions

1. Frontend calls backend, gets 200 OK with valid JSON, but the browser console shows a CORS error and nothing renders. Where's the actual bug?
2. Why does `/health` return a hardcoded `{"status": "ok"}` instead of checking that the FAISS index/embedding model are loaded?
3. Why might `requirements.txt` intentionally start small and grow milestone by milestone, instead of listing everything the whole project will eventually need?

<details><summary>Answers</summary>

1. Neither "frontend" nor "backend logic" — the backend already answered correctly (200, valid JSON). The bug is a missing/misconfigured CORS header (`CORS_ORIGINS` on the deployed backend doesn't list the exact deployed frontend URL). Browsers block already-successful responses at the browser level; this is never a "logic" bug.
2. A health check needs to be fast and unconditionally answer "is this process alive" — not "are all downstream dependencies perfect." Checking the embedding model/FAISS index on every poll would add latency and could cause a deployment platform to kill a perfectly healthy process over a transient blip in an unrelated dependency.
3. Adding a dependency only when a milestone actually uses it keeps the dependency footprint honest and auditable — a `requirements.txt` that lists everything upfront looks the same whether or not the corresponding code exists yet, hiding whether a feature is real or aspirational.
</details>
