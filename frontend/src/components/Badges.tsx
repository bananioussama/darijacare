import type { EscalationStatus, PriorityLevel } from "../api/types";
import {
  confidenceLevel,
  LEVEL_LABELS,
  LEVEL_STYLES,
  pct,
  STATUS_LABELS,
  STATUS_STYLES,
} from "../lib/labels";

const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold";

export function Pill({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={`${PILL} ${className}`}>{children}</span>;
}

/** Badge de confiance (F-UI-03) : niveau en toutes lettres et pourcentage. */
export function ConfidenceBadge({ value }: { value: number }) {
  const level = confidenceLevel(value);
  return (
    <span
      className={`${PILL} ${level.style}`}
      title="Confiance conjointe catégorie × intention du modèle NLU"
    >
      Confiance {level.label} · {pct(value)}
    </span>
  );
}

export function LevelPill({ level }: { level: PriorityLevel }) {
  return <span className={`${PILL} ${LEVEL_STYLES[level]}`}>{LEVEL_LABELS[level]}</span>;
}

export function StatusPill({ status }: { status: EscalationStatus }) {
  return <span className={`${PILL} ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>;
}
