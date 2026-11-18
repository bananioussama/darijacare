// Historique de session (F-UI-05) : sessions de ce navigateur, lecture paginée côté API.
// Une session ne voit que ses propres messages : chaque lecture utilise son propre jeton.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { api, ApiError } from "../api/client";
import type { MessagePage, SessionOut } from "../api/types";
import { AssistantBubble, ClientBubble } from "../components/MessageView";
import { formatDate } from "../lib/labels";
import {
  currentSession,
  isExpired,
  listSessions,
  saveSession,
  updateSession,
  type StoredSession,
} from "../lib/sessions";
import { useTitle } from "../lib/useTitle";
import { historyTurns } from "./ChatPage";

function statusOf(session: StoredSession, current: StoredSession | null): string {
  if (isExpired(session)) return "Expirée";
  if (session.closed) return "Fermée";
  return current?.session_id === session.session_id ? "En cours" : "Ouverte";
}

export default function HistoryPage() {
  useTitle("Historique de session");
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<StoredSession[]>(listSessions);
  const [selected, setSelected] = useState<StoredSession | null>(() => listSessions()[0] ?? null);
  const [page, setPage] = useState<MessagePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = currentSession();

  useEffect(() => {
    setPage(null);
    setError(null);
    if (!selected) return undefined;
    if (isExpired(selected)) {
      setError("Session expirée : son historique n'est plus accessible (jeton valable 24 h).");
      return undefined;
    }
    const controller = new AbortController();
    api<MessagePage>(`/sessions/${encodeURIComponent(selected.session_id)}/messages?limit=100`, {
      token: selected.token,
      signal: controller.signal,
    })
      .then(setPage)
      .catch((e: unknown) => {
        if (e instanceof ApiError) setError(e.message);
      });
    return () => controller.abort();
  }, [selected]);

  async function reset(session: StoredSession): Promise<void> {
    try {
      const out = await api<SessionOut>(
        `/sessions/${encodeURIComponent(session.session_id)}/reset`,
        { method: "POST", token: session.token },
      );
      updateSession(session.session_id, { closed: true });
      const fresh = saveSession(out.session_id, out.session_token, out.expires_in);
      setSessions(listSessions());
      setSelected(fresh);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Réinitialisation impossible.");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="titre-page">Historique de session</h1>
      <p className="text-sm text-texte-2">
        Les conversations de ce navigateur restent lisibles 24 heures. Personne d'autre ne peut les
        lire : chaque session a son propre jeton.
      </p>
      {sessions.length === 0 ? (
        <p className="carte p-5">
          Aucune session pour l'instant : commencez une conversation dans l'assistant.
        </p>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <ul className="space-y-2 lg:w-72" aria-label="Sessions">
            {sessions.map((s) => (
              <li key={s.session_id}>
                <button
                  type="button"
                  aria-current={selected?.session_id === s.session_id ? "true" : undefined}
                  className={`w-full rounded-carte p-3 text-start ring-1 ${
                    selected?.session_id === s.session_id
                      ? "bg-lavande ring-vif"
                      : "bg-white ring-lavande hover:bg-gris"
                  }`}
                  onClick={() => setSelected(s)}
                >
                  <span className="block text-sm font-semibold">{formatDate(s.created_at)}</span>
                  <span className="block truncate text-sm" dir="auto">
                    {s.preview || "Nouvelle conversation"}
                  </span>
                  <span className="text-xs text-texte-2">{statusOf(s, current)}</span>
                </button>
              </li>
            ))}
          </ul>
          <section className="min-w-0 flex-1 space-y-4" aria-label="Fil de la session">
            {selected && current?.session_id === selected.session_id && (
              <div className="flex flex-wrap gap-2">
                <button type="button" className="bouton-principal" onClick={() => navigate("/")}>
                  Reprendre dans l'assistant
                </button>
                <button
                  type="button"
                  className="bouton-secondaire"
                  onClick={() => void reset(selected)}
                >
                  Réinitialiser la session
                </button>
              </div>
            )}
            {error && (
              <p className="carte p-4 text-[#9B1C1C]" role="alert">
                {error}
              </p>
            )}
            {page && page.items.length === 0 && (
              <p className="carte p-4">Aucun message dans cette session.</p>
            )}
            {page &&
              historyTurns(page).map((turn) =>
                turn.kind === "client" ? (
                  <ClientBubble key={turn.key} turn={turn} />
                ) : (
                  <AssistantBubble
                    key={turn.key}
                    turn={turn}
                    sessionToken={selected?.token ?? null}
                  />
                ),
              )}
          </section>
        </div>
      )}
    </div>
  );
}
