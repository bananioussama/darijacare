"""Decision engine (cahier des charges, F-DEC-01 and F-DEC-03, Table 24).

Rules are evaluated **in this order**; the first one that matches decides:

1. input not allowed (empty, length, prompt injection) -> polite refusal;
2. needs_human above the threshold or urgency = 3 -> priority escalation;
3. security intent (scam_spam_report, lost_stolen) -> safety procedure + escalation;
4. non_telecom -> polite out-of-scope reply;
5. intent confidence below the threshold -> clarification offering the top-2 intents
   (at most one per turn; if the customer was already asked, escalate — prudence);
6. conversational intent (greeting_thanks, agency_location, customer_service_contact)
   -> direct template;
7. otherwise -> grounded answer (RAG).

Every decision carries the rule that fired and a French explanation, and is logged.
Rule 2 fires before rule 3, as in the specification; when an escalated message has a
security intent, :attr:`Decision.include_safety_procedure` asks the reply to include
the safety steps anyway, so the customer is never left without them.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from darijacare.decision.priority import Priority, priority_score
from darijacare.guards.input_guard import GuardResult
from darijacare.nlu.service import NLUResult

log = logging.getLogger("darijacare.decision")


class Action(StrEnum):
    """What the assistant does with the message."""

    REFUSE = "refus"
    ESCALATE = "escalade"
    SAFETY_ESCALATE = "securite_escalade"
    OUT_OF_SCOPE = "hors_perimetre"
    CLARIFY = "clarification"
    TEMPLATE = "gabarit_direct"
    RAG = "reponse_ancree"


@dataclass(frozen=True)
class ConversationState:
    """What the policy needs to know about the conversation so far."""

    clarification_pending: bool = False
    """``True`` when the previous assistant turn was a clarification question."""


@dataclass
class Decision:
    """Outcome of the policy for one message (always explainable)."""

    action: Action
    rule: int
    rule_name: str
    explanation: str
    escalate: bool = False
    priority: Priority | None = None
    include_safety_procedure: bool = False
    clarification_options: list[str] = field(default_factory=list)
    refusal_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d


class DecisionPolicy:
    """Rule-based policy configured by ``configs/decision.yaml``."""

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.cfg = cfg
        t = cfg["thresholds"]
        self.needs_human_threshold = float(t["needs_human"])
        self.intent_threshold = float(t["intent_confidence"])
        self.escalate_urgency = int(t["escalate_urgency"])
        intents = cfg["intents"]
        self.security = set(intents["security"])
        self.out_of_scope = set(intents["out_of_scope"])
        self.conversational = set(intents["conversational"])
        self.after_failed_clarification = cfg["clarification"]["after_failed_clarification"]

    def _priority(self, nlu: NLUResult) -> Priority:
        return priority_score(
            urgency=nlu.urgency,
            needs_human_probability=nlu.needs_human_probability,
            confidence=nlu.intent_joint_confidence,
            intent=nlu.intent,
            category=nlu.category,
            cfg=self.cfg["priority"],
        )

    def decide(
        self,
        guard: GuardResult,
        nlu: NLUResult | None,
        state: ConversationState | None = None,
    ) -> Decision:
        """Apply the rules in order. ``nlu`` may be ``None`` only when the guard refused."""
        state = state or ConversationState()
        decision = self._decide(guard, nlu, state)
        log.info(
            "décision règle=%d (%s) action=%s intention=%s",
            decision.rule,
            decision.rule_name,
            decision.action.value,
            nlu.intent if nlu else None,
        )
        return decision

    def _decide(
        self, guard: GuardResult, nlu: NLUResult | None, state: ConversationState
    ) -> Decision:
        # 1. Input not allowed.
        if not guard.allowed:
            return Decision(
                Action.REFUSE,
                1,
                "entree_non_conforme",
                f"Entrée refusée ({guard.reason}).",
                refusal_reason=guard.reason,
            )
        if nlu is None:
            raise ValueError("Analyse NLU manquante pour une entrée acceptée")

        # 2. Human needed or urgency 3.
        human = nlu.needs_human_probability >= self.needs_human_threshold
        urgent = nlu.urgency >= self.escalate_urgency
        if human or urgent:
            why = []
            if human:
                why.append(
                    f"p(needs_human)={nlu.needs_human_probability:.2f} ≥ "
                    f"{self.needs_human_threshold:.2f}"
                )
            if urgent:
                why.append(f"urgence={nlu.urgency}")
            return Decision(
                Action.ESCALATE,
                2,
                "escalade_prioritaire",
                "Escalade prioritaire : " + ", ".join(why) + ".",
                escalate=True,
                priority=self._priority(nlu),
                include_safety_procedure=nlu.intent in self.security,
            )

        # 3. Security intents.
        if nlu.intent in self.security:
            return Decision(
                Action.SAFETY_ESCALATE,
                3,
                "procedure_securite",
                f"Intention de sécurité ({nlu.intent}) : procédure + escalade.",
                escalate=True,
                priority=self._priority(nlu),
                include_safety_procedure=True,
            )

        # 4. Out of scope.
        if nlu.intent in self.out_of_scope:
            return Decision(
                Action.OUT_OF_SCOPE, 4, "hors_perimetre", "Message hors du périmètre télécom."
            )

        # 5. Low confidence -> clarification (at most once), then escalation.
        if nlu.intent_joint_confidence < self.intent_threshold:
            conf = f"{nlu.intent_joint_confidence:.2f} < {self.intent_threshold:.2f}"
            if state.clarification_pending and self.after_failed_clarification == "escalate":
                return Decision(
                    Action.ESCALATE,
                    5,
                    "clarification_echouee",
                    f"Confiance toujours faible après une clarification ({conf}).",
                    escalate=True,
                    priority=self._priority(nlu),
                )
            options = [s.label for s in nlu.intent_top2]
            if len(options) < 2:  # single-intent category: offer the second category instead
                options = [nlu.intent] + [s.label for s in nlu.category_top2[1:2]]
            return Decision(
                Action.CLARIFY,
                5,
                "clarification",
                f"Confiance faible ({conf}) : clarification entre {options}.",
                clarification_options=options,
            )

        # 6. Conversational intents.
        if nlu.intent in self.conversational:
            return Decision(
                Action.TEMPLATE, 6, "gabarit_direct", f"Intention conversationnelle ({nlu.intent})."
            )

        # 7. Nominal case.
        return Decision(
            Action.RAG,
            7,
            "reponse_ancree",
            f"Réponse ancrée sur la fiche de l'intention {nlu.intent}.",
        )
