// Panneau d'analyse NLU (F-UI-02) : toutes les sorties du modèle pour le dernier message,
// avec la confiance de chaque tâche et les deux intentions les plus probables.
import type { Decision, NluAnalysis, Script } from "../api/types";
import { ACTION_LABELS, CATEGORY_LABELS, pct, SCRIPT_LABELS } from "../lib/labels";
import { LevelPill } from "./Badges";

export interface Analysis {
  script: Script;
  maskedText: string;
  nlu: NluAnalysis | null;
  decision: Decision;
}

function Row({ term, value, detail }: { term: string; value: React.ReactNode; detail?: string }) {
  return (
    <div className="border-b border-lavande py-2 last:border-b-0">
      <dt className="text-xs text-texte-2">{term}</dt>
      <dd className="flex flex-wrap items-baseline justify-between gap-2 font-semibold">
        <span>{value}</span>
        {detail && <span className="text-xs font-normal text-texte-2">{detail}</span>}
      </dd>
    </div>
  );
}

export default function AnalysisPanel({ analysis }: { analysis: Analysis | null }) {
  if (!analysis) {
    return (
      <p className="text-sm text-texte-2">
        Envoyez un message pour voir l'analyse du modèle : écriture, catégorie, intention, produit,
        urgence et besoin d'un conseiller.
      </p>
    );
  }
  const { nlu, decision } = analysis;
  return (
    <div className="space-y-4">
      <dl aria-label="Sorties du modèle NLU">
        <Row term="Écriture détectée" value={SCRIPT_LABELS[analysis.script]} />
        {nlu ? (
          <>
            <Row
              term="Catégorie"
              value={CATEGORY_LABELS[nlu.category] ?? nlu.category}
              detail={pct(nlu.category_confidence)}
            />
            <Row term="Intention" value={nlu.intent} detail={pct(nlu.intent_confidence)} />
            <div className="border-b border-lavande py-2">
              <dt className="text-xs text-texte-2">Deux intentions les plus probables</dt>
              <dd>
                <ol className="mt-1 space-y-1 text-sm">
                  {nlu.intent_top2.map((s) => (
                    <li key={s.label} className="flex justify-between gap-2">
                      <span>{s.label}</span>
                      <span className="text-texte-2">{pct(s.p)}</span>
                    </li>
                  ))}
                </ol>
              </dd>
            </div>
            <Row term="Produit" value={nlu.product} detail={pct(nlu.product_confidence)} />
            <Row term="Urgence (0 à 3)" value={nlu.urgency} detail={pct(nlu.urgency_confidence)} />
            <Row
              term="Besoin d'un conseiller (needs_human)"
              value={nlu.needs_human ? "oui" : "non"}
              detail={`p = ${pct(nlu.needs_human_probability)}`}
            />
            <Row term="Confiance conjointe" value={pct(nlu.intent_joint_confidence)} />
          </>
        ) : (
          <Row term="Modèle NLU" value="non appelé (message refusé)" />
        )}
      </dl>
      <div className="rounded-bouton bg-gris p-3 text-sm">
        <p className="font-semibold text-profond">
          Règle {decision.rule} · {ACTION_LABELS[decision.action] ?? decision.action}
        </p>
        <p className="mt-1 text-texte-2">{decision.explanation}</p>
        {decision.priority && (
          <p className="mt-2 flex items-center gap-2">
            Priorité {decision.priority.score.toFixed(1)}{" "}
            <LevelPill level={decision.priority.level} />
          </p>
        )}
      </div>
      {nlu && (
        <p className="text-xs text-texte-2">
          Modèle {nlu.model_version} · analyse en {Math.round(nlu.latency_ms)} ms
        </p>
      )}
    </div>
  );
}
