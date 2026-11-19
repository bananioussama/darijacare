// Accès à l'API. En développement, /api passe par le proxy de Vite ; en production
// (Phase 6), nginx servira l'interface et relaiera /api vers le backend.
import { SseParser } from "./sse";
import type { ChatEvent } from "./types";

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const FALLBACK: Record<number, string> = {
  401: "Authentification requise ou expirée.",
  403: "Accès refusé pour ce rôle.",
  404: "Élément introuvable.",
  409: "Action impossible dans l'état actuel.",
  422: "Requête invalide.",
  429: "Trop de requêtes, réessayez dans un instant.",
  500: "Erreur interne du serveur.",
};

async function errorFrom(res: Response): Promise<ApiError> {
  let detail: string | undefined;
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      detail = body.detail;
    }
  } catch {
    // corps absent ou non JSON : message par défaut
  }
  return new ApiError(res.status, detail ?? FALLBACK[res.status] ?? `Erreur ${res.status}.`);
}

function unreachable(error: unknown): unknown {
  if (error instanceof DOMException && error.name === "AbortError") return error;
  return new ApiError(0, "Serveur injoignable : l'API est-elle lancée ?");
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token, signal } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    throw unreachable(error);
  }
  if (!res.ok) throw await errorFrom(res);
  if (res.status === 204) return undefined as T; // pas de corps (refus d'une inscription)
  return (await res.json()) as T;
}

export interface ChatRequest {
  text: string;
  requestHuman?: boolean;
  token?: string | null;
  signal?: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}

/** Envoie un message et transmet les événements SSE au fur et à mesure. */
export async function streamChat({
  text,
  requestHuman = false,
  token,
  signal,
  onEvent,
}: ChatRequest): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text, request_human: requestHuman }),
      signal,
    });
  } catch (error) {
    throw unreachable(error);
  }
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new ApiError(0, "Réponse vide du serveur.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  const dispatch = (events: { event: string; data: string }[]): void => {
    for (const e of events) onEvent({ type: e.event, data: JSON.parse(e.data) } as ChatEvent);
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    dispatch(parser.push(decoder.decode(value, { stream: true })));
  }
  dispatch(parser.push(decoder.decode()));
  dispatch(parser.flush());
}
