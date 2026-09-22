const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const CREDS_KEY = "studylens_credentials";

export interface Credentials {
  username: string;
  password: string;
}

// sessionStorage, not localStorage: credentials are cleared when the tab
// closes rather than persisting indefinitely on a shared machine.
export function saveCredentials(creds: Credentials) {
  sessionStorage.setItem(CREDS_KEY, JSON.stringify(creds));
}

export function loadCredentials(): Credentials | null {
  const raw = sessionStorage.getItem(CREDS_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Credentials;
  } catch {
    return null;
  }
}

export function clearCredentials() {
  sessionStorage.removeItem(CREDS_KEY);
}

function authHeader(creds: Credentials): string {
  return "Basic " + btoa(`${creds.username}:${creds.password}`);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit,
  creds: Credentials
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { ...(options.headers || {}), Authorization: authHeader(creds) },
    });
  } catch {
    throw new ApiError(0, "Could not reach the StudyLens server. Is the backend running?");
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body.detail || body.error || message;
    } catch {
      // response wasn't JSON; keep the generic message
    }
    throw new ApiError(res.status, message);
  }
  return res.json();
}

export async function checkLogin(creds: Credentials): Promise<{ username: string }> {
  return request("/api/me", { method: "GET" }, creds);
}

export interface UploadResult {
  filename: string;
  page_count: number;
  chunk_count: number;
  index_total_chunks: number;
}

export async function uploadPdf(file: File, creds: Credentials): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return request("/api/upload", { method: "POST", body: formData }, creds);
}

export interface Source {
  chunk_id: string;
  source: string;
  page: number;
  faiss_score: number;
  rerank_score: number;
  snippet: string;
}

export interface AskResult {
  question: string;
  answer: string;
  query_type: "single_fact" | "multi_part" | "summarization";
  sub_questions: string[];
  retrieval_trace: { sub_question: string; chunk_ids: string[] }[];
  pre_rerank_order: string[];
  post_rerank_order: string[];
  sources: Source[];
}

export async function askQuestion(question: string, creds: Credentials): Promise<AskResult> {
  return request(
    "/api/ask",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    },
    creds
  );
}

export type PipelineStage = "routing" | "retrieval" | "reranking" | "generation";

export interface PipelineEvent {
  stage: PipelineStage | "complete" | "error";
  status?: "start" | "done";
  // routing
  query_type?: AskResult["query_type"];
  sub_questions?: string[];
  // retrieval
  retrieval_trace?: AskResult["retrieval_trace"];
  candidate_count?: number;
  // reranking
  pre_rerank_order?: string[];
  post_rerank_order?: string[];
  // generation / complete
  answer?: string;
  sources?: Source[];
  question?: string;
  // error
  message?: string;
}

/**
 * Consumes the SSE pipeline-visualization endpoint. Not the native
 * browser EventSource API: EventSource can only do unauthenticated GET
 * requests, and this needs a POST body plus a Basic Auth header. Instead,
 * fetch() the stream manually and parse the same "data: {json}\n\n"
 * framing by hand — a standard workaround for authenticated/POST SSE.
 */
export async function* streamAsk(
  question: string,
  creds: Credentials
): AsyncGenerator<PipelineEvent> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authHeader(creds) },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiError(0, "Could not reach the StudyLens server. Is the backend running?");
  }

  if (!response.ok || !response.body) {
    throw new ApiError(response.status, `Failed to start the pipeline stream (${response.status}).`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? ""; // last piece may be incomplete, keep it for next chunk

    for (const raw of events) {
      const line = raw.trim();
      if (line.startsWith("data: ")) {
        yield JSON.parse(line.slice("data: ".length)) as PipelineEvent;
      }
    }
  }
}
