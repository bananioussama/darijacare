// Console conseiller (F-UI-06, séquence d'escalade Figure 3) : file triée par priorité,
// dossier complet, prise en charge, clôture avec correction éventuelle de l'intention.
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { EscalationDetail, EscalationOut } from "../api/types";
import { LevelPill, StatusPill } from "../components/Badges";
import IntentSelect, { useIntents } from "../components/IntentSelect";
import { useAuth, useStaffApi } from "../lib/auth";
import { CONTRIBUTION_LABELS, formatDate, pct, SCRIPT_LABELS } from "../lib/labels";
import { useTitle } from "../lib/useTitle";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Erreur inattendue.";
}

export default function ConsolePage() {
  useTitle("Console conseiller");
  const call = useStaffApi();
  const { user } = useAuth();
  const { intents } = useIntents();
  const [showClosed, setShowClosed] = useState(false);
  const [queue, setQueue] = useState<EscalationOut[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [correction, setCorrection] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canAct = user?.role === "conseiller";
  const title = (intent: string | null): string =>
    (intent && intents?.find((i) => i.intent === intent)?.titles.fr) || intent || "—";

  const loadQueue = useCallback(async () => {
    const statuses = showClosed ? ["nouveau", "en_cours", "cloture"] : ["nouveau", "en_cours"];
    const query = statuses.map((s) => `status=${s}`).join("&");
    setQueue(await call<EscalationOut[]>(`/escalades?${query}&limit=100`));
  }, [call, showClosed]);

  const loadDetail = useCallback(
    async (id: string) => setDetail(await call<EscalationDetail>(`/escalades/${id}`)),
    [call],
  );

  useEffect(() => {
    loadQueue().catch((e: unknown) => setError(message(e)));
  }, [loadQueue]);

  useEffect(() => {
    setCorrection("");
    if (!selectedId) {
      setDetail(null);
      return;
    }
    loadDetail(selectedId).catch((e: unknown) => setError(message(e)));
  }, [selectedId, loadDetail]);

  async function act(action: "prendre" | "cloturer"): Promise<void> {
    if (!detail) return;
    setBusy(true);
    setError(null);
    try {
      await call(`/escalades/${detail.id}`, {
        method: "PATCH",
        body: { action, corrected_intent: action === "cloturer" && correction ? correction : null },
      });
      await Promise.all([loadQueue(), loadDetail(detail.id)]);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="titre-page">Console conseiller</h1>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-6 accent-vif"
              checked={showClosed}
              onChange={(event) => setShowClosed(event.target.checked)}
            />
            Afficher les dossiers clôturés
          </label>
          <button
            type="button"
            className="bouton-secondaire"
            onClick={() => void loadQueue().catch((e: unknown) => setError(message(e)))}
          >
            Actualiser
          </button>
        </div>
      </div>
      {!canAct && (
        <p className="rounded-bouton bg-[#FFF7D6] p-3 text-sm text-[#7A4B00]">
          Lecture seule : seuls les conseillers prennent en charge et clôturent les dossiers.
        </p>
      )}
      {error && (
        <p className="rounded-bouton bg-[#FDECEC] p-3 text-sm text-[#9B1C1C]" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <section className="carte p-3 lg:w-96" aria-labelledby="titre-file">
          <h2 id="titre-file" className="px-1 pb-2 font-semibold text-profond">
            File d'escalades (par priorité)
          </h2>
          {queue === null && <p className="p-2 text-texte-2">Chargement…</p>}
          {queue?.length === 0 && <p className="p-2 text-texte-2">Aucun dossier en attente.</p>}
          <ul className="space-y-2">
            {queue?.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  aria-current={selectedId === e.id ? "true" : undefined}
                  className={`w-full rounded-bouton p-3 text-start ring-1 ${
                    selectedId === e.id
                      ? "bg-lavande ring-vif"
                      : "bg-white ring-lavande hover:bg-gris"
                  }`}
                  onClick={() => setSelectedId(e.id)}
                >
                  <span className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold" dir="ltr">
                      {e.case_number}
                    </span>
                    <StatusPill status={e.status} />
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                    <LevelPill level={e.priority_level} />
                    <span>priorité {e.priority.toFixed(1)}</span>
                  </span>
                  <span className="mt-1 block text-sm">{title(e.intent)}</span>
                  <span className="block text-xs text-texte-2">
                    {e.script ? SCRIPT_LABELS[e.script] : "—"} · {formatDate(e.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="carte min-w-0 flex-1 p-4" aria-labelledby="titre-dossier">
          {!detail ? (
            <p id="titre-dossier" className="text-texte-2">
              Choisissez un dossier dans la file.
            </p>
          ) : (
            <div className="space-y-5">
              <header className="flex flex-wrap items-center gap-2">
                <h2 id="titre-dossier" className="text-xl font-bold text-profond" dir="ltr">
                  Dossier {detail.case_number}
                </h2>
                <StatusPill status={detail.status} />
                <LevelPill level={detail.priority_level} />
                <span className="text-sm text-texte-2">priorité {detail.priority.toFixed(1)}</span>
              </header>
              <p className="text-sm text-texte-2">
                {detail.reason} · créé {formatDate(detail.created_at)}
                {detail.advisor && ` · pris en charge par ${detail.advisor}`}
              </p>

              <div>
                <h3 className="font-semibold text-profond">Résumé</h3>
                <p className="mt-1 text-sm" dir="auto">
                  {detail.summary}
                </p>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <div>
                  <h3 className="font-semibold text-profond">Message du client (masqué)</h3>
                  <p className="mt-1 rounded-bouton bg-gris p-3" dir="auto">
                    {detail.message.text}
                  </p>
                  {detail.analysis && (
                    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                      <dt className="text-texte-2">Intention</dt>
                      <dd>{detail.analysis.intent}</dd>
                      <dt className="text-texte-2">Confiance</dt>
                      <dd>{pct(detail.analysis.intent_joint_confidence)}</dd>
                      <dt className="text-texte-2">Urgence</dt>
                      <dd>{detail.analysis.urgency}</dd>
                      <dt className="text-texte-2">Besoin d'un conseiller</dt>
                      <dd>{pct(detail.analysis.needs_human_probability)}</dd>
                      <dt className="text-texte-2">Écriture</dt>
                      <dd>{SCRIPT_LABELS[detail.analysis.script]}</dd>
                    </dl>
                  )}
                </div>
                <div>
                  <h3 className="font-semibold text-profond">Calcul de la priorité</h3>
                  <ul className="mt-1 space-y-1 text-sm">
                    {Object.entries(detail.priority_contributions).map(([name, value]) => (
                      <li key={name} className="flex justify-between gap-2">
                        <span>{CONTRIBUTION_LABELS[name] ?? name}</span>
                        <span>+{value.toFixed(1)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {detail.proposed_fiche && (
                <div>
                  <h3 className="font-semibold text-profond">
                    Fiche proposée : {detail.proposed_fiche.title}{" "}
                    <span className="text-sm font-normal text-texte-2" dir="ltr">
                      ({detail.proposed_fiche.id} · v{detail.proposed_fiche.version})
                    </span>
                  </h3>
                  <ol className="mt-1 list-decimal space-y-1 ps-6 text-sm">
                    {detail.proposed_fiche.etapes.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  <p className="mt-1 text-sm text-texte-2">{detail.proposed_fiche.escalade}</p>
                </div>
              )}

              <div>
                <h3 className="font-semibold text-profond">Historique de la conversation</h3>
                <ol className="mt-2 space-y-2">
                  {detail.history.map((m) => (
                    <li key={m.id} className="rounded-bouton bg-gris p-3 text-sm">
                      <p className="font-semibold" dir="auto">
                        {m.text}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-texte-2" dir="auto">
                        {m.reply}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>

              {canAct && detail.status === "nouveau" && (
                <button
                  type="button"
                  className="bouton-principal"
                  disabled={busy}
                  onClick={() => void act("prendre")}
                >
                  Prendre en charge
                </button>
              )}
              {canAct && detail.status === "en_cours" && detail.advisor === user?.username && (
                <form
                  className="space-y-3 rounded-bouton bg-gris p-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void act("cloturer");
                  }}
                >
                  <IntentSelect
                    id="intention-corrigee"
                    label="Intention corrigée (facultatif)"
                    value={correction}
                    onChange={setCorrection}
                  />
                  <button type="submit" className="bouton-principal" disabled={busy}>
                    Clôturer le dossier
                  </button>
                </form>
              )}
              {detail.status === "en_cours" && detail.advisor !== user?.username && (
                <p className="text-sm text-texte-2">Dossier pris en charge par {detail.advisor}.</p>
              )}
              {detail.corrected_intent && (
                <p className="text-sm">
                  Intention corrigée : <strong>{title(detail.corrected_intent)}</strong>
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
