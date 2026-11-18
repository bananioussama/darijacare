"""Chat processing for the API: assistant, then storage of the exchange in one transaction.

Escalation flow (cahier des charges, Figure 3): when the decision escalates, an
:class:`Escalade` is created (or raised) with its priority, a summary and a case
number, and the reply tells the customer this number. Each conversation has at most
one escalation; a new escalation on a closed case reopens it.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from darijacare.api.models import Conversation, Escalade, Message, ModeleNLU
from darijacare.decision.policy import Action, ConversationState
from darijacare.guards.input_guard import GuardResult
from darijacare.nlu.service import NLUResult
from darijacare.pipeline import AssistantReply, DarijaCareAssistant

log = logging.getLogger("darijacare.api.chat")

SUMMARY_MAX_CHARS = 2000


@dataclass
class Exchange:
    """Stored message, the assistant output and the escalation, if any."""

    message: Message
    reply: AssistantReply
    escalation: Escalade | None


def nlu_analysis(nlu: NLUResult | None) -> dict[str, Any] | None:
    """NLU output to store (the text itself is stored masked in ``message.text``)."""
    if nlu is None:
        return None
    data = nlu.to_dict()
    data.pop("text", None)
    return data


def new_case_number() -> str:
    """Short case number given to the customer, e.g. ``DC-3F9A1C2B``."""
    return f"DC-{uuid.uuid4().hex[:8].upper()}"


class ChatService:
    """Run the assistant and persist each exchange.

    One inference at a time: the NLU model runs on CPU and the same loaded model is
    shared by all requests.
    """

    def __init__(self, assistant: DarijaCareAssistant, decision_config_id: str) -> None:
        self.assistant = assistant
        self.decision_config_id = decision_config_id
        self._lock = threading.Lock()

    def analyse(self, text: str) -> tuple[GuardResult, NLUResult | None]:
        """Guard and NLU only (``POST /predict``): nothing is stored."""
        guard = self.assistant.guard.check(text)
        if not guard.allowed:
            return guard, None
        with self._lock:
            return guard, self.assistant.nlu.predict(guard.model_text)

    def handle(self, db: Session, conversation: Conversation, text: str) -> Exchange:
        """Process ``text`` in ``conversation`` and commit the exchange."""
        state = ConversationState(clarification_pending=conversation.clarification_pending)
        with self._lock:
            reply = self.assistant.handle(text, state)
        nlu, decision = reply.nlu, reply.decision
        if nlu is not None and nlu.model_version and db.get(ModeleNLU, nlu.model_version) is None:
            db.add(ModeleNLU(version=nlu.model_version, encoder="inconnu", metrics={}))
        turn = (
            db.scalar(
                select(func.max(Message.turn)).where(Message.conversation_id == conversation.id)
            )
            or 0
        ) + 1
        message = Message(
            conversation_id=conversation.id,
            turn=turn,
            text=reply.masked_input,
            script=reply.script,
            intent=nlu.intent if nlu else None,
            category=nlu.category if nlu else None,
            product=nlu.product if nlu else None,
            urgency=nlu.urgency if nlu else None,
            needs_human=nlu.needs_human if nlu else None,
            needs_human_probability=nlu.needs_human_probability if nlu else None,
            confidence=nlu.intent_joint_confidence if nlu else None,
            model_version=nlu.model_version if nlu and nlu.model_version else None,
            decision_config_id=self.decision_config_id,
            decision_rule=decision.rule,
            decision_action=decision.action.value,
            analysis=nlu_analysis(nlu),
            decision=decision.to_dict(),
            reply=reply.text,
            reply_template=reply.template,
            sources=list(reply.sources),
            fiche_id=reply.sources[0]["id"] if reply.sources else None,
            latency_ms={k: round(v, 1) for k, v in reply.latency_ms.items()},
        )
        db.add(message)
        db.flush()
        escalation = None
        if reply.escalate:
            escalation = self._escalate(db, conversation, message, reply)
            line = self.assistant.responder.case_number_line(reply.script, escalation.case_number)
            message.reply = f"{reply.text}\n{line}"
            conversation.status = "escaladee"
        conversation.clarification_pending = decision.action is Action.CLARIFY
        db.commit()
        log.info(
            "message traité",
            extra={
                "action": decision.action.value,
                "rule": decision.rule,
                "intent": message.intent,
                "escalation": escalation.case_number if escalation else None,
            },
        )
        return Exchange(message, reply, escalation)

    def _escalate(
        self, db: Session, conversation: Conversation, message: Message, reply: AssistantReply
    ) -> Escalade:
        decision = reply.decision
        priority = decision.priority
        score = priority.score if priority else 0.0
        level = priority.level if priority else "basse"
        contributions = dict(priority.contributions) if priority else {}
        reason = f"règle {decision.rule} : {decision.rule_name}"[:255]
        summary = summarize(message, reply)
        escalation = db.scalar(select(Escalade).where(Escalade.conversation_id == conversation.id))
        if escalation is None:
            escalation = Escalade(
                case_number=new_case_number(),
                conversation_id=conversation.id,
                message_id=message.id,
                priority=score,
                priority_level=level,
                priority_contributions=contributions,
                reason=reason,
                status="nouveau",
                summary=summary,
            )
            db.add(escalation)
            db.flush()
            return escalation
        reopened = escalation.status == "cloture"
        if reopened:  # new request on a closed case: reopen it, same case number
            escalation.status = "nouveau"
            escalation.advisor_id = None
            escalation.taken_at = None
            escalation.closed_at = None
            escalation.corrected_intent = None
        if reopened or score > escalation.priority:  # an open case keeps its highest priority
            escalation.priority = score
            escalation.priority_level = level
            escalation.priority_contributions = contributions
        escalation.message_id = message.id
        escalation.reason = reason
        escalation.summary = summary
        return escalation


def summarize(message: Message, reply: AssistantReply) -> str:
    """Advisor-facing summary in French (built from the masked text only)."""
    nlu, decision = reply.nlu, reply.decision
    parts = []
    if nlu is not None:
        parts.append(
            f"Intention : {nlu.intent} ({nlu.intent_joint_confidence:.0%}), catégorie "
            f"{nlu.category}, produit {nlu.product}, urgence {nlu.urgency}, "
            f"p(conseiller) {nlu.needs_human_probability:.0%}, écriture {nlu.script}."
        )
    parts.append(f"Décision : {decision.explanation}")
    parts.append(f"Message : « {message.text} »")
    return " ".join(parts)[:SUMMARY_MAX_CHARS]
