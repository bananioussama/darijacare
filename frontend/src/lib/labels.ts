// Libellés français et styles d'état. Les couleurs d'état ne servent jamais seules :
// chaque pastille porte aussi son libellé (accessibilité, impression, daltonisme).
import type { EscalationStatus, Lang, PriorityLevel, Script } from "../api/types";

export const SCRIPT_LABELS: Record<Script, string> = {
  arabic: "arabe",
  arabizi: "arabizi",
  mixed: "mixte",
};

export const CATEGORY_LABELS: Record<string, string> = {
  billing_payment: "Facturation et paiement",
  customer_care: "Service client",
  devices: "Appareils",
  home_internet: "Internet à domicile",
  home_line: "Ligne fixe",
  mobile_money: "Portefeuille mobile",
  network_calls: "Réseau et appels",
  out_of_scope: "Hors périmètre",
  plans_subscription: "Offres et abonnements",
  prepaid_credit: "Crédit prépayé",
  sim_line: "SIM et ligne",
  usage_mobile_data: "Consommation et internet mobile",
};

export const ACTION_LABELS: Record<string, string> = {
  refus: "Message non traité",
  escalade: "Transmis à un conseiller",
  securite_escalade: "Procédure de sécurité et conseiller",
  hors_perimetre: "Hors périmètre télécom",
  clarification: "Précision demandée",
  gabarit_direct: "Réponse directe",
  reponse_ancree: "Réponse appuyée sur une fiche",
};

export const STATUS_LABELS: Record<EscalationStatus, string> = {
  nouveau: "Nouveau",
  en_cours: "En cours",
  cloture: "Clôturé",
};

export const STATUS_STYLES: Record<EscalationStatus, string> = {
  nouveau: "bg-[#FFF1E0] text-[#8A3B00]",
  en_cours: "bg-lavande text-profond",
  cloture: "bg-[#E6F6EC] text-[#14532D]",
};

export const LEVEL_LABELS: Record<PriorityLevel, string> = {
  critique: "Critique",
  haute: "Haute",
  normale: "Normale",
  basse: "Basse",
};

export const LEVEL_STYLES: Record<PriorityLevel, string> = {
  critique: "bg-[#FDECEC] text-[#9B1C1C]",
  haute: "bg-[#FFF1E0] text-[#8A3B00]",
  normale: "bg-[#FFF7D6] text-[#7A4B00]",
  basse: "bg-gris text-texte-2",
};

export const CONTRIBUTION_LABELS: Record<string, string> = {
  urgence: "Urgence",
  needs_human: "Besoin d'un conseiller",
  incertitude: "Incertitude du modèle",
  bonus: "Bonus (sécurité, argent)",
};

export interface ConfidenceLevel {
  label: "élevée" | "moyenne" | "faible";
  style: string;
}

/** Niveau de confiance affiché ; 0,80 est le seuil de clarification de la politique. */
export function confidenceLevel(p: number): ConfidenceLevel {
  if (p >= 0.8) return { label: "élevée", style: "bg-[#E6F6EC] text-[#14532D]" };
  if (p >= 0.5) return { label: "moyenne", style: "bg-[#FFF7D6] text-[#7A4B00]" };
  return { label: "faible", style: "bg-[#FDECEC] text-[#9B1C1C]" };
}

export function pct(p: number | null | undefined): string {
  return p == null ? "—" : `${Math.round(p * 100)} %`;
}

export function langOf(script: Script | null | undefined): Lang {
  if (script === "arabic") return "ar";
  if (script === "arabizi") return "arabizi";
  return "fr";
}

const dateFormat = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });

export function formatDate(iso: string | null | undefined): string {
  return iso ? dateFormat.format(new Date(iso)) : "—";
}

/** Texte envoyé par le bouton « Parler à un conseiller », dans l'écriture du client. */
export const ADVISOR_REQUEST: Record<Script, string> = {
  arabic: "بغيت نهضر مع مستشار",
  arabizi: "bghit nhder m3a chi conseiller",
  mixed: "Je voudrais parler à un conseiller.",
};

/** Exemples cliquables dans les trois écritures (messages fictifs). */
export const EXAMPLES: { script: Script; text: string }[] = [
  { script: "arabic", text: "الكونيكسيون مقطوعة من البارح ف الدار" },
  { script: "arabizi", text: "chargit 20dh w ma wslatni walo, 3afak chofo lia" },
  { script: "mixed", text: "Bonjour, ma facture de ce mois est trop élevée" },
  { script: "arabizi", text: "solde dyali sala bzerba, 3lach?" },
  { script: "arabic", text: "كيفاش نشري باس ديال الأنترنيت" },
];

export const MIN_CHARS = 4;
export const MAX_CHARS = 500;
