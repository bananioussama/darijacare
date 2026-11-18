// Sessions client anonymes connues de ce navigateur (F-UI-05 « reprendre l'échange »).
// Le jeton de session (24 h) ne donne accès qu'à sa propre conversation.
import { readJson, writeJson } from "./storage";

export interface StoredSession {
  session_id: string;
  token: string;
  created_at: string;
  expires_at: string;
  preview: string;
  closed: boolean;
}

const KEY = "darijacare.sessions";
const MAX_SESSIONS = 10;

export function listSessions(): StoredSession[] {
  return readJson<StoredSession[]>("local", KEY, []);
}

export function isExpired(session: StoredSession, now = Date.now()): boolean {
  return Date.parse(session.expires_at) <= now;
}

/** Session à poursuivre dans le chat : la plus récente, ouverte et non expirée. */
export function currentSession(): StoredSession | null {
  return listSessions().find((s) => !s.closed && !isExpired(s)) ?? null;
}

export function saveSession(
  session_id: string,
  token: string,
  expiresInSeconds: number,
  preview = "",
): StoredSession {
  const now = new Date();
  const entry: StoredSession = {
    session_id,
    token,
    created_at: now.toISOString(),
    expires_at: new Date(now.getTime() + expiresInSeconds * 1000).toISOString(),
    preview,
    closed: false,
  };
  const others = listSessions().filter((s) => s.session_id !== session_id);
  writeJson("local", KEY, [entry, ...others].slice(0, MAX_SESSIONS));
  return entry;
}

export function updateSession(session_id: string, patch: Partial<StoredSession>): void {
  writeJson(
    "local",
    KEY,
    listSessions().map((s) => (s.session_id === session_id ? { ...s, ...patch } : s)),
  );
}
