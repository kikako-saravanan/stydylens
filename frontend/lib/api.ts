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
