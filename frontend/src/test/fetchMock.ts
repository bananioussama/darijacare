// Faux fetch pour les tests : routes « MÉTHODE /chemin » -> réponse. Les réponses sont de
// simples objets (pas de Response de Node) pour éviter les problèmes de royaume avec jsdom.
import { vi } from "vitest";

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

type FakeResponse = Pick<Response, "ok" | "status" | "json" | "body">;
export type Handler = (call: Call) => FakeResponse;

export function json(data: unknown, status = 200): FakeResponse {
  return {
    ok: status < 400,
    status,
    json: async () => data,
    body: null,
  };
}

/** Flux SSE découpé en morceaux de ``chunkSize`` octets (coupe aussi les caractères arabes). */
export function sse(events: [string, unknown][], chunkSize = 7): FakeResponse {
  const text = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  const reader = {
    read: async () => {
      if (offset >= bytes.length) return { done: true, value: undefined };
      const value = bytes.slice(offset, offset + chunkSize);
      offset += chunkSize;
      return { done: false, value };
    },
  };
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
    body: { getReader: () => reader } as unknown as Response["body"],
  };
}

export function mockFetch(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  const fake = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const call: Call = {
      method: (init.method ?? "GET").toUpperCase(),
      path: path + url.search,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: Object.fromEntries(new Headers(init.headers).entries()),
    };
    calls.push(call);
    const handler = routes[`${call.method} ${path}`];
    return handler ? handler(call) : json({ detail: `non simulé : ${call.method} ${path}` }, 404);
  });
  vi.stubGlobal("fetch", fake);
  return calls;
}

/** Événements d'une réponse ancrée (balance_check, arabizi). */
export function answerEvents(
  reply = "Salam! hadi lkhatawat :\n1. Chouf solde.",
): [string, unknown][] {
  return [
    [
      "session",
      {
        session_id: "s-1",
        session_token: "jeton-session-1",
        expires_in: 86400,
        conversation_id: "c-1",
      },
    ],
    [
      "analysis",
      {
        message_id: "m-1",
        script: "arabizi",
        masked_text: "solde dyali, nemra <TEL>",
        nlu: {
          script: "arabizi",
          category: "prepaid_credit",
          category_confidence: 0.95,
          intent: "balance_check",
          intent_confidence: 0.95,
          intent_joint_confidence: 0.9,
          product: "mobile",
          product_confidence: 0.9,
          urgency: 0,
          urgency_confidence: 0.8,
          needs_human: false,
          needs_human_probability: 0.05,
          category_top2: [{ label: "prepaid_credit", p: 0.95 }],
          intent_top2: [
            { label: "balance_check", p: 0.95 },
            { label: "balance_deducted", p: 0.02 },
          ],
          model_version: "v5@8e694ecf",
          latency_ms: 1400,
        },
        decision: {
          action: "reponse_ancree",
          rule: 7,
          rule_name: "reponse_ancree",
          explanation: "Réponse ancrée sur la fiche de l'intention balance_check.",
          escalate: false,
          priority: null,
          include_safety_procedure: false,
          clarification_options: [],
          refusal_reason: null,
        },
      },
    ],
    ...reply.split(/(?<=\s)/).map((piece): [string, unknown] => ["token", { text: piece }]),
    ["sources", [{ id: "KB-balance_check", version: 1, title: "Nchouf solde" }]],
    ["done", { message_id: "m-1", turn: 1, escalation: null, latency_ms: { total: 1800 } }],
  ];
}
