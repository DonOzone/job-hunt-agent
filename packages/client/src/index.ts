export type Kind = "job" | "project";
export interface User { id: string; email: string }
export interface Profile {
  name: string; location: string; home_country: string;
  work_authorization: string[]; roles: string[]; prefer_remote: boolean; cv_text: string;
}
export interface Opportunity {
  id: string; title: string; company: string; url: string; source: string;
  location: string; description: string; remote: boolean; opportunity_type: Kind;
  duration: string; skills: string[]; match_score: number | null; rank: number | null;
}
export interface Application {
  id: string; opportunity_id: string; title: string; company: string;
  opportunity_type: Kind; status: string; next_action: string; updated_at: string;
}
export interface Feedback {
  id: string; application_id: string; subject: string; body: string;
  analysis: string; created_at: string;
}
export interface Resource { name: string; url: string; provider?: string; type?: string }
export interface Learning {
  id: string; skill: string; status: "planned" | "learning" | "completed";
  hours: number; evidence: string; resources: Resource[];
}
export interface Card {
  id: string; topic: string; front: string; kind: string; options: string[];
}
export interface Task {
  id: string; title: string; prompt: string; status: string; result: string; created_at: string;
}
export interface Run {
  id: string; kind: string; status: string; result: string; error: string; created_at: string;
}
export interface Dashboard {
  opportunities: number; projects: number; applications: number;
  application_statuses: Record<string, number>; learning_completed: number;
  learning_total: number; study_attempts: number; study_correct: number;
  feedback_received: number; feedback_unreviewed: number; pending_tasks: number;
}
export interface Match {
  report: string; matched: string[]; missing: string[]; score: number;
}
export interface Gap {
  skill: string; importance: number; jobs: number; courses: Resource[];
}
export interface AiSettings { provider: string; model: string; configured: boolean }
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export function validateBaseUrl(value: string): string {
  if (!value) return "";
  const url = new URL(value);
  const local = /^(localhost|127\.0\.0\.1|\[::1\]|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(url.hostname);
  if (url.username || url.password || url.search || url.hash ||
      (url.protocol !== "https:" && !(url.protocol === "http:" && local))) {
    throw new Error("Use HTTPS, or HTTP on a trusted local development network. Do not put credentials in the URL.");
  }
  return url.origin;
}

export class ApiClient {
  private token = "";
  readonly baseUrl: string;
  constructor(baseUrl = "") { this.baseUrl = validateBaseUrl(baseUrl); }
  setToken(token: string): void { this.token = token; }
  getToken(): string { return this.token; }
  async upload<T>(path: string, body: FormData): Promise<T> {
    if (!path.startsWith("/api/")) throw new Error("Only application API routes are allowed.");
    const response = await fetch(this.baseUrl + path, {
      method: "POST", credentials: "include", body,
      headers: this.token ? {Authorization: `Bearer ${this.token}`} : {}
    });
    if (!response.ok) {
      const error: unknown = await response.json().catch(() => null);
      const message = typeof error === "object" && error !== null && "detail" in error &&
        typeof error.detail === "string" ? error.detail : `Upload failed (${response.status})`;
      throw new ApiError(message, response.status);
    }
    return response.json() as Promise<T>;
  }
  async request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    if (!path.startsWith("/api/")) throw new Error("Only application API routes are allowed.");
    const response = await fetch(this.baseUrl + path, {
      method, credentials: "include",
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {})
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      const error: unknown = await response.json().catch(() => null);
      if (typeof error === "object" && error !== null && "detail" in error &&
          typeof error.detail === "string") message = error.detail;
      throw new ApiError(message, response.status);
    }
    return response.json() as Promise<T>;
  }
  async login(email: string, password: string, register = false): Promise<User> {
    const result = await this.request<{user: User; token: string}>(
      `/api/auth/${register ? "register" : "login"}`, "POST", {email, password});
    this.token = result.token;
    return result.user;
  }
  async restore(): Promise<User> { return this.request<User>("/api/auth/me"); }
  async logout(): Promise<void> {
    await this.request("/api/auth/logout", "POST");
    this.token = "";
  }
}
