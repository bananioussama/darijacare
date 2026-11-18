// Chat de démonstration multi-script (F-UI-01 à F-UI-04, maquette Figure 12).
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, streamChat } from "../api/client";
import type { MessagePage, Script, SessionOut } from "../api/types";
import AnalysisPanel, { type Analysis } from "../components/AnalysisPanel";
import Composer from "../components/Composer";
import {
  AssistantBubble,
  ClientBubble,
  type AssistantTurn,
  type Turn,
} from "../components/MessageView";
import { ADVISOR_REQUEST, EXAMPLES, SCRIPT_LABELS } from "../lib/labels";
import { currentSession, saveSession, updateSession, type StoredSession } from "../lib/sessions";
import { useTitle } from "../lib/useTitle";

let sequence = 0;
const nextKey = (): string => `tour-${++sequence}`;

export function historyTurns(page: MessagePage): Turn[] {
  return page.items.flatMap((m): Turn[] => [
    { kind: "client", key: `c-${m.id}`, text: m.text },
    {
      kind: "assistant",
      key: `a-${m.id}`,
      status: "done",
      text: m.reply,
      script: m.script,
      messageId: m.id,
      action: m.decision_action,
      confidence: m.confidence,
      sources: m.sources,
    },
  ]);
}

function wideScreen(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(min-width: 1024px)").matches
    : true;
}

const SESSION_LOST =
  "Votre session a expiré ou a été fermée. Renvoyez votre message : une nouvelle session sera ouverte.";

export default function ChatPage() {
  useTitle("Assistant");
  const [session, setSession] = useState<StoredSession | null>(() => currentSession());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastScript, setLastScript] = useState<Script>("mixed");
  const [showPanel, setShowPanel] = useState(wideScreen);
  const [notice, setNotice] = useState<string | null>(null);
  const initialSession = useRef(session);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // Reprendre la conversation en cours après un rechargement (F-UI-05).
  useEffect(() => {
    const resumed = initialSession.current;
    if (!resumed) return undefined;
    const controller = new AbortController();
    api<MessagePage>(`/sessions/${encodeURIComponent(resumed.session_id)}/messages?limit=100`, {
      token: resumed.token,
      signal: controller.signal,
    })
      .then((page) => {
        setTurns(historyTurns(page));
        const last = page.items.at(-1);
        if (last) setLastScript(last.script);
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          updateSession(resumed.session_id, { closed: true });
          setSession(null);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const patch = useCallback(
    (
      key: string,
      change: Partial<AssistantTurn> | ((t: AssistantTurn) => Partial<AssistantTurn>),
    ) => {
      setTurns((all) =>
        all.map((t) =>
          t.kind === "assistant" && t.key === key
            ? { ...t, ...(typeof change === "function" ? change(t) : change) }
            : t,
        ),
      );
    },
    [],
  );

  async function send(text: string, requestHuman = false): Promise<void> {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    const key = nextKey();
    setTurns((all) => [
      ...all,
      { kind: "client", key: nextKey(), text },
      { kind: "assistant", key, status: "streaming", text: "", sources: [] },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    let active = session;
    try {
      await streamChat({
        text,
        requestHuman,
        token: active?.token ?? null,
        signal: controller.signal,
        onEvent: (event) => {
          switch (event.type) {
            case "session":
              if (event.data.session_token) {
                active = saveSession(
                  event.data.session_id,
                  event.data.session_token,
                  event.data.expires_in ?? 24 * 3600,
                  text.slice(0, 80),
                );
                setSession(active);
              }
              break;
            case "analysis":
              setLastScript(event.data.script);
              setAnalysis({
                script: event.data.script,
                maskedText: event.data.masked_text,
                nlu: event.data.nlu,
                decision: event.data.decision,
              });
              patch(key, {
                messageId: event.data.message_id,
                script: event.data.script,
                nlu: event.data.nlu,
                decision: event.data.decision,
              });
              break;
            case "token":
              patch(key, (t) => ({ text: t.text + event.data.text }));
              break;
            case "sources":
              patch(key, { sources: event.data });
              break;
            case "done":
              patch(key, { status: "done", escalation: event.data.escalation });
              break;
          }
        },
      });
      patch(key, (t) =>
        t.status === "streaming" ? { status: "error", error: "Réponse interrompue." } : {},
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      let message = error instanceof ApiError ? error.message : "Erreur inattendue.";
      if (error instanceof ApiError && [401, 404, 409].includes(error.status) && active) {
        updateSession(active.session_id, { closed: true });
        setSession(null);
        message = SESSION_LOST;
      }
      patch(key, { status: "error", error: message });
    } finally {
      setBusy(false);
    }
  }

  async function newSession(): Promise<void> {
    abortRef.current?.abort();
    if (session) {
      try {
        const out = await api<SessionOut>(
          `/sessions/${encodeURIComponent(session.session_id)}/reset`,
          { method: "POST", token: session.token },
        );
        updateSession(session.session_id, { closed: true });
        setSession(saveSession(out.session_id, out.session_token, out.expires_in));
      } catch {
        updateSession(session.session_id, { closed: true });
        setSession(null);
      }
    }
    setTurns([]);
    setAnalysis(null);
    setBusy(false);
    setNotice("Nouvelle session ouverte.");
  }

  return (
    <div className="flex flex-col gap-4 xl:flex-row">
      <section className="flex min-w-0 flex-1 flex-col" aria-labelledby="titre-chat">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 id="titre-chat" className="titre-page">
            Assistant clientèle
          </h1>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="bouton-secondaire"
              aria-expanded={showPanel}
              aria-controls="analyse-nlu"
              onClick={() => setShowPanel((shown) => !shown)}
            >
              {showPanel ? "Masquer l'analyse" : "Afficher l'analyse"}
            </button>
            <button type="button" className="bouton-secondaire" onClick={() => void newSession()}>
              Nouvelle session
            </button>
          </div>
        </header>
        <p className="mt-1 text-sm text-texte-2">
          Réponses automatiques appuyées sur des fiches fictives. Écrivez en arabe, en arabizi ou en
          darija mêlée de français.
        </p>
        {notice && (
          <p role="status" className="mt-2 text-sm text-[#14532D]">
            {notice}
          </p>
        )}

        <div className="mt-4 min-h-64 flex-1 space-y-4" aria-live="polite">
          {turns.length === 0 && (
            <div className="carte p-5">
              <h2 className="font-semibold text-profond">Essayez un exemple</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <li key={example.text}>
                    <button
                      type="button"
                      className="bouton-secondaire font-normal"
                      disabled={busy}
                      onClick={() => void send(example.text)}
                    >
                      <span dir="auto">{example.text}</span>
                      <span className="text-xs text-texte-2">
                        ({SCRIPT_LABELS[example.script]})
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {turns.map((turn) =>
            turn.kind === "client" ? (
              <ClientBubble key={turn.key} turn={turn} />
            ) : (
              <AssistantBubble key={turn.key} turn={turn} sessionToken={session?.token ?? null} />
            ),
          )}
          {/* Marge de défilement : la zone de saisie collée en bas ne masque pas la fin. */}
          <div ref={endRef} className="scroll-mb-52" />
        </div>

        <div className="sticky bottom-0 mt-4 space-y-3 border-t border-lavande bg-gris pt-3 pb-1">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="bouton-secondaire"
              disabled={busy}
              onClick={() => void send(ADVISOR_REQUEST[lastScript], true)}
            >
              Parler à un conseiller
            </button>
          </div>
          <Composer disabled={busy} onSend={(text) => void send(text)} />
        </div>
      </section>

      {showPanel && (
        <aside
          id="analyse-nlu"
          className="carte h-fit w-full shrink-0 p-4 xl:sticky xl:top-6 xl:w-80"
          aria-labelledby="titre-analyse"
        >
          <h2 id="titre-analyse" className="mb-3 text-lg font-bold text-profond">
            Analyse NLU
          </h2>
          <AnalysisPanel analysis={analysis} />
        </aside>
      )}
    </div>
  );
}
