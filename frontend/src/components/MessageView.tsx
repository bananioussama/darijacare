// Bulles de la conversation. Les textes sont toujours rendus comme du texte (React les
// échappe) : une réponse ne peut pas injecter de HTML ni de script dans la page.
import type { Decision, EscalationRef, NluAnalysis, Script, Source } from "../api/types";
import { ACTION_LABELS, langOf } from "../lib/labels";
import { ConfidenceBadge, Pill } from "./Badges";
import FeedbackBar from "./FeedbackBar";
import SourcesBox from "./SourcesBox";

export interface ClientTurn {
  kind: "client";
  key: string;
  text: string;
}

export interface AssistantTurn {
  kind: "assistant";
  key: string;
  status: "streaming" | "done" | "error";
  text: string;
  script?: Script;
  messageId?: string;
  nlu?: NluAnalysis | null;
  decision?: Decision;
  action?: string;
  confidence?: number | null;
  sources: Source[];
  escalation?: EscalationRef | null;
  error?: string;
}

export type Turn = ClientTurn | AssistantTurn;

export function ClientBubble({ turn }: { turn: ClientTurn }) {
  return (
    <div className="flex justify-end">
      <p
        dir="auto"
        className="max-w-[85%] whitespace-pre-wrap rounded-carte bg-profond px-4 py-3 text-white lg:max-w-[70%]"
      >
        {turn.text}
      </p>
    </div>
  );
}

function StateBadge({ turn }: { turn: AssistantTurn }) {
  const action = turn.decision?.action ?? turn.action;
  if (turn.escalation) {
    return (
      <Pill className="bg-[#FFF1E0] text-[#8A3B00]">
        Transmis à un conseiller · dossier {turn.escalation.case_number}
      </Pill>
    );
  }
  if (action === "hors_perimetre")
    return <Pill className="bg-gris text-texte-2">Hors périmètre</Pill>;
  if (action === "clarification") {
    return (
      <Pill className="bg-[#FFF7D6] text-[#7A4B00]">Confiance faible : précision demandée</Pill>
    );
  }
  if (action === "refus") return <Pill className="bg-gris text-texte-2">Message non traité</Pill>;
  return null;
}

export function AssistantBubble({
  turn,
  sessionToken,
}: {
  turn: AssistantTurn;
  sessionToken: string | null;
}) {
  const confidence = turn.nlu?.intent_joint_confidence ?? turn.confidence ?? null;
  const action = turn.decision?.action ?? turn.action;
  return (
    <article
      className="max-w-full rounded-carte bg-white p-4 shadow-sm ring-1 ring-lavande lg:max-w-[85%]"
      aria-busy={turn.status === "streaming"}
      aria-label="Réponse de l'assistant"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill className="bg-lavande text-profond">Réponse automatique</Pill>
        <StateBadge turn={turn} />
        {confidence != null && action !== "refus" && <ConfidenceBadge value={confidence} />}
      </div>
      {turn.status === "error" ? (
        <p className="text-[#9B1C1C]" role="alert">
          {turn.error}
        </p>
      ) : turn.text ? (
        <p dir="auto" className="whitespace-pre-wrap">
          {turn.text}
        </p>
      ) : (
        <p className="flex items-center gap-1 text-texte-2" aria-label="Réponse en cours">
          <span className="motion-safe:animate-pulse">●</span>
          <span className="motion-safe:animate-pulse [animation-delay:150ms]">●</span>
          <span className="motion-safe:animate-pulse [animation-delay:300ms]">●</span>
        </p>
      )}
      {turn.status === "done" && (
        <>
          <SourcesBox sources={turn.sources} lang={langOf(turn.script)} />
          {turn.messageId && action && action !== "refus" && (
            <FeedbackBar messageId={turn.messageId} token={sessionToken} />
          )}
          {action && ACTION_LABELS[action] && (
            <p className="mt-2 text-xs text-texte-2">{ACTION_LABELS[action]}</p>
          )}
        </>
      )}
    </article>
  );
}
