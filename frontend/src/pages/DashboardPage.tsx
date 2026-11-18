// Tableau de bord (F-UI-07, maquette Figure 13). Vue complète pour ML / data et
// administrateurs ; vue limitée (file d'escalades) pour les conseillers (Tableau 14).
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError } from "../api/client";
import type { AnalyticsSummary, EscalationOut, EscalationStats } from "../api/types";
import { LevelPill, StatusPill } from "../components/Badges";
import { useAuth, useStaffApi } from "../lib/auth";
import { ACTION_LABELS, LEVEL_LABELS, pct, SCRIPT_LABELS, STATUS_LABELS } from "../lib/labels";
import { useTitle } from "../lib/useTitle";

const number = new Intl.NumberFormat("fr-FR");
const decimal = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});
const BAR = "#7b2cbf"; // violet vif : une seule teinte (une seule série par graphique)

function reducedMotion(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : true;
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="carte p-4">
      <p className="text-sm text-texte-2">{label}</p>
      <p className="mt-1 text-3xl font-bold text-profond">{value}</p>
      {hint && <p className="mt-1 text-xs text-texte-2">{hint}</p>}
    </div>
  );
}

interface Datum {
  name: string;
  value: number;
}

/** Barres horizontales d'une seule série, avec infobulle et tableau des données. */
function HorizontalBars({ title, data, unit }: { title: string; data: Datum[]; unit: string }) {
  const height = Math.max(120, data.length * 36 + 24);
  return (
    <figure className="carte p-4">
      <figcaption className="font-semibold text-profond">{title}</figcaption>
      {data.length === 0 ? (
        <p className="mt-2 text-sm text-texte-2">Pas encore de données sur la période.</p>
      ) : (
        <>
          <div className="mt-2" style={{ height }} aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              {/* Graphique masqué aux technologies d'assistance : le tableau « Voir les
                  données » en est l'équivalent ; la couche clavier de Recharts est donc coupée. */}
              <BarChart
                accessibilityLayer={false}
                data={data}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 4 }}
              >
                <CartesianGrid horizontal={false} stroke="#e9ddf9" />
                <XAxis
                  type="number"
                  allowDecimals={false}
                  tick={{ fill: "#5b4e6e", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={170}
                  tick={{ fill: "#1e1530", fontSize: 13 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "#f4f1f8" }}
                  formatter={(value) => [`${String(value)} ${unit}`, ""]}
                  separator=""
                />
                <Bar
                  dataKey="value"
                  fill={BAR}
                  barSize={14}
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={!reducedMotion()}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-2 text-sm">
            <summary className="min-h-11 cursor-pointer content-center text-vif">
              Voir les données
            </summary>
            <table className="mt-2 w-full text-start">
              <thead>
                <tr className="text-texte-2">
                  <th className="py-1 text-start font-normal">Élément</th>
                  <th className="py-1 text-end font-normal">{unit}</th>
                </tr>
              </thead>
              <tbody>
                {data.map((d) => (
                  <tr key={d.name} className="border-t border-lavande">
                    <td className="py-1">{d.name}</td>
                    <td className="py-1 text-end">{number.format(d.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </figure>
  );
}

export default function DashboardPage() {
  useTitle("Tableau de bord");
  const { user } = useAuth();
  const call = useStaffApi();
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [stats, setStats] = useState<EscalationStats | null>(null);
  const [queue, setQueue] = useState<EscalationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const full = user?.role === "ml" || user?.role === "admin";

  useEffect(() => {
    const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Erreur inattendue.");
    if (full)
      call<AnalyticsSummary>(`/analytics/summary?days=${days}`).then(setSummary).catch(fail);
    call<EscalationStats>("/analytics/escalades").then(setStats).catch(fail);
    if (user?.role !== "ml") call<EscalationOut[]>("/escalades?limit=5").then(setQueue).catch(fail);
  }, [call, days, full, user?.role]);

  const evaluation = summary?.modele.evaluation;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="titre-page">Tableau de bord</h1>
        {full && (
          <label className="flex items-center gap-2 text-sm">
            Période
            <select
              className="champ w-auto"
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              <option value={7}>7 derniers jours</option>
              <option value={30}>30 derniers jours</option>
              <option value={90}>90 derniers jours</option>
            </select>
          </label>
        )}
      </div>
      {error && (
        <p className="rounded-bouton bg-[#FDECEC] p-3 text-sm text-[#9B1C1C]" role="alert">
          {error}
        </p>
      )}

      {full && summary && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Messages analysés" value={number.format(summary.messages)} />
            <Kpi
              label="F1 macro (test)"
              value={evaluation?.f1_macro != null ? decimal.format(evaluation.f1_macro) : "—"}
              hint={summary.modele.version ? `Modèle ${summary.modele.version}` : undefined}
            />
            <Kpi
              label="Taux d'escalade"
              value={pct(summary.taux_escalade)}
              hint={`${number.format(summary.escalades)} escalades`}
            />
            <Kpi
              label="Latence p95"
              value={
                summary.latence_ms.p95 != null
                  ? `${number.format(Math.round(summary.latence_ms.p95))} ms`
                  : "—"
              }
              hint={
                summary.latence_ms.p50 != null
                  ? `médiane ${number.format(Math.round(summary.latence_ms.p50))} ms`
                  : undefined
              }
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <HorizontalBars
              title="Répartition par écriture"
              unit="messages"
              data={Object.entries(summary.par_script).map(([script, n]) => ({
                name: SCRIPT_LABELS[script as keyof typeof SCRIPT_LABELS] ?? script,
                value: n,
              }))}
            />
            <HorizontalBars
              title="Intentions les plus fréquentes"
              unit="messages"
              data={summary.top_intentions.map((t) => ({ name: t.intent, value: t.messages }))}
            />
            <HorizontalBars
              title="Décisions"
              unit="messages"
              data={Object.entries(summary.par_decision).map(([action, n]) => ({
                name: ACTION_LABELS[action] ?? action,
                value: n,
              }))}
            />
            <div className="carte p-4">
              <h2 className="font-semibold text-profond">Retours des utilisateurs</h2>
              <p className="mt-2 text-sm">
                Utile : <strong>{number.format(summary.feedback.utile ?? 0)}</strong> · À corriger :{" "}
                <strong>{number.format(summary.feedback.a_corriger ?? 0)}</strong>
              </p>
              {evaluation?.ece != null && (
                <p className="mt-2 text-sm text-texte-2">
                  Calibration du modèle actif (test) : ECE {decimal.format(evaluation.ece)}
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {stats && (
        <div className="grid gap-4 sm:grid-cols-3">
          {(["nouveau", "en_cours", "cloture"] as const).map((status) => (
            <Kpi
              key={status}
              label={`Escalades : ${STATUS_LABELS[status].toLowerCase()}`}
              value={number.format(stats.par_statut[status] ?? 0)}
            />
          ))}
          <p className="text-sm text-texte-2 sm:col-span-3">
            Dossiers ouverts par niveau :{" "}
            {(["critique", "haute", "normale", "basse"] as const)
              .map((level) => `${LEVEL_LABELS[level]} ${stats.ouvertes_par_niveau[level] ?? 0}`)
              .join(" · ")}
          </p>
        </div>
      )}

      {queue && (
        <section className="carte p-4" aria-labelledby="titre-file-tdb">
          <h2 id="titre-file-tdb" className="font-semibold text-profond">
            File d'escalades (par priorité)
          </h2>
          {queue.length === 0 ? (
            <p className="mt-2 text-sm text-texte-2">Aucun dossier en attente.</p>
          ) : (
            <ul className="mt-2 divide-y divide-lavande">
              {queue.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="font-semibold" dir="ltr">
                    {e.case_number}
                  </span>
                  <span className="text-sm text-texte-2">
                    {e.intent ?? "—"} · {e.script ? SCRIPT_LABELS[e.script] : "—"}
                  </span>
                  <span className="flex gap-2">
                    <LevelPill level={e.priority_level} />
                    <StatusPill status={e.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
