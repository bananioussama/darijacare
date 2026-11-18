// Types des réponses de l'API (schémas Pydantic de src/darijacare/api/schemas.py).

export type Script = "arabic" | "arabizi" | "mixed";
export type Lang = "fr" | "ar" | "arabizi";
export type Role = "conseiller" | "ml" | "admin";
export type EscalationStatus = "nouveau" | "en_cours" | "cloture";
export type PriorityLevel = "critique" | "haute" | "normale" | "basse";

export interface Scored {
  label: string;
  p: number;
}

/** Sortie complète du modèle NLU (sans le texte, stocké masqué à part). */
export interface NluAnalysis {
  script: Script;
  category: string;
  category_confidence: number;
  intent: string;
  intent_confidence: number;
  intent_joint_confidence: number;
  product: string;
  product_confidence: number;
  urgency: number;
  urgency_confidence: number;
  needs_human: boolean;
  needs_human_probability: number;
  category_top2: Scored[];
  intent_top2: Scored[];
  model_version: string;
  latency_ms: number;
}

export interface Priority {
  score: number;
  level: PriorityLevel;
  contributions: Record<string, number>;
}

export interface Decision {
  action: string;
  rule: number;
  rule_name: string;
  explanation: string;
  escalate: boolean;
  priority: Priority | null;
  include_safety_procedure: boolean;
  clarification_options: string[];
  refusal_reason: string | null;
}

export interface Source {
  id: string;
  version: number;
  title?: string;
}

export interface EscalationRef {
  case_number: string;
  priority_level: PriorityLevel;
  status: EscalationStatus;
}

export interface SessionInfo {
  session_id: string;
  conversation_id: string;
  session_token?: string;
  expires_in?: number;
}

/** Événements du flux SSE de POST /chat, dans l'ordre d'arrivée. */
export type ChatEvent =
  | { type: "session"; data: SessionInfo }
  | {
      type: "analysis";
      data: {
        message_id: string;
        script: Script;
        masked_text: string;
        nlu: NluAnalysis | null;
        decision: Decision;
      };
    }
  | { type: "token"; data: { text: string } }
  | { type: "sources"; data: Source[] }
  | {
      type: "done";
      data: {
        message_id: string;
        turn: number;
        escalation: EscalationRef | null;
        latency_ms: Record<string, number>;
      };
    };

export interface SessionOut {
  session_id: string;
  session_token: string;
  expires_in: number;
}

export interface MessageOut {
  id: string;
  turn: number;
  created_at: string;
  text: string;
  script: Script;
  intent: string | null;
  category: string | null;
  product: string | null;
  urgency: number | null;
  needs_human: boolean | null;
  confidence: number | null;
  decision_rule: number;
  decision_action: string;
  reply: string;
  sources: Source[];
  fiche_id: string | null;
}

export interface MessagePage {
  items: MessageOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface IntentInfo {
  intent: string;
  category: string;
  titles: Record<Lang, string>;
}

export interface FicheView {
  id: string;
  intent: string;
  category: string;
  version: number;
  status: string;
  lang: Lang;
  notice: string;
  title: string;
  sections: {
    objet: string;
    etapes: string[];
    conditions: string[];
    limites: string[];
    escalade: string;
  };
}

export interface TokenOut {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  role: Role;
}

export interface UserOut {
  id: string;
  username: string;
  role: Role;
  active: boolean;
  created_at: string;
}

export interface EscalationOut {
  id: string;
  case_number: string;
  status: EscalationStatus;
  priority: number;
  priority_level: PriorityLevel;
  reason: string;
  summary: string;
  created_at: string;
  taken_at: string | null;
  closed_at: string | null;
  advisor: string | null;
  intent: string | null;
  script: Script | null;
  corrected_intent: string | null;
}

export interface ProposedFiche {
  id: string;
  version: number;
  title: string;
  etapes: string[];
  escalade: string;
}

export interface EscalationDetail extends EscalationOut {
  priority_contributions: Record<string, number>;
  message: MessageOut;
  analysis: NluAnalysis | null;
  proposed_fiche: ProposedFiche | null;
  history: MessageOut[];
}

export interface AnalyticsSummary {
  periode_jours: number;
  messages: number;
  escalades: number;
  taux_escalade: number;
  latence_ms: { p50: number | null; p95: number | null };
  par_script: Record<string, number>;
  par_decision: Record<string, number>;
  top_intentions: { intent: string; messages: number }[];
  feedback: Record<string, number>;
  modele: {
    version: string | null;
    evaluation: { dataset: string; f1_macro: number | null; ece: number | null } | null;
  };
}

export interface EscalationStats {
  par_statut: Record<string, number>;
  ouvertes_par_niveau: Record<string, number>;
}

export interface KbFiche {
  id: string;
  intent: string;
  version: number;
  status: string;
  titles: Record<string, string>;
}

export interface ModelInfo {
  version: string;
  encoder: string;
  status: string;
  metrics: Record<string, unknown>;
  evaluations: { dataset: string; f1_macro: number | null; ece: number | null; source: string }[];
}

export interface DecisionConfigOut {
  id: string;
  created_at: string;
  content: {
    thresholds: Record<string, number>;
    priority: { weights: Record<string, number>; levels: Record<string, number> };
    [key: string]: unknown;
  };
}

export interface Health {
  status: "ok" | "degrade";
  database: string;
  qdrant: string;
  models_loaded: boolean;
  nlu_model: string | null;
  decision_config: string | null;
  kb_fiches: number;
}
