"""Relational model, following the class diagram of the cahier des charges (§10.6, Figure 6).

Three domains:

* conversation: :class:`Conversation`, :class:`Message` (with its NLU predictions and
  its decision), :class:`Feedback`, :class:`Escalade`, and :class:`Utilisateur` (staff
  accounts: conseiller, ml, admin; customers stay anonymous and only get a session);
* knowledge: :class:`FicheKB` (one row per fiche and language) and :class:`Chunk`
  (mirror of the Qdrant points);
* steering: :class:`ModeleNLU`, :class:`ExecutionEvaluation`, :class:`ConfigDecision`.

Every message records the model version and the decision configuration that produced
it, so results stay reproducible. Texts are stored **masked** (``<TEL>``, ``<URL>``,
``<EMAIL>``): the raw customer text never reaches the database.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from darijacare.api.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")

ROLES = ("conseiller", "ml", "admin")
SCRIPTS = ("arabic", "arabizi", "mixed")
CONVERSATION_STATUSES = ("ouverte", "escaladee", "close")
ESCALATION_STATUSES = ("nouveau", "en_cours", "cloture")
FEEDBACK_RATINGS = ("utile", "a_corriger")
FEEDBACK_AUTHORS = ("client", "conseiller")
MODEL_STATUSES = ("en_service", "archive", "rejete")


def utcnow() -> datetime:
    """Current time, timezone-aware (UTC)."""
    return datetime.now(UTC)


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


# --- conversation domain ------------------------------------------------------------


class Utilisateur(Base):
    """Staff account. Passwords are stored as Argon2id hashes only.

    Self-registered accounts start ``pending``: they cannot log in until an administrator
    validates them and sets their role (a refused request is deleted).
    """

    __tablename__ = "utilisateur"
    __table_args__ = (CheckConstraint(_one_of("role", ROLES), name="ck_utilisateur_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """Self-registration waiting for an administrator: login refused until validated."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    """Anonymous customer conversation, opened with a session token."""

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(_one_of("status", CONVERSATION_STATUSES), name="ck_conversation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="ouverte")
    clarification_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    """The previous turn asked for a clarification (decision rule 5, one per turn)."""

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.turn", cascade="all, delete-orphan"
    )
    escalation: Mapped[Escalade | None] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """One customer message with its masked text, NLU predictions, decision and reply."""

    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "turn", name="uq_message_turn"),
        CheckConstraint(_one_of("script", SCRIPTS), name="ck_message_script"),
        CheckConstraint("urgency IS NULL OR urgency BETWEEN 0 AND 3", name="ck_message_urgency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    turn: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    text: Mapped[str] = mapped_column(Text)
    """Customer text with phone numbers, URLs and e-mails masked."""
    script: Mapped[str] = mapped_column(String(8))
    intent: Mapped[str | None] = mapped_column(String(64), index=True)
    category: Mapped[str | None] = mapped_column(String(64))
    product: Mapped[str | None] = mapped_column(String(64))
    urgency: Mapped[int | None] = mapped_column(Integer)
    needs_human: Mapped[bool | None] = mapped_column(Boolean)
    needs_human_probability: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    """Joint confidence category x intent (decision rule 5)."""
    model_version: Mapped[str | None] = mapped_column(ForeignKey("modele_nlu.version"))
    decision_config_id: Mapped[str] = mapped_column(ForeignKey("config_decision.id"))
    decision_rule: Mapped[int] = mapped_column(Integer)
    decision_action: Mapped[str] = mapped_column(String(32))
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    """Full NLU output (top-2, probabilities, latency) for the analysis panel and console."""
    decision: Mapped[dict[str, Any]] = mapped_column(JSONType)
    reply: Mapped[str] = mapped_column(Text)
    reply_template: Mapped[str] = mapped_column(String(32))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    fiche_id: Mapped[str | None] = mapped_column(String(80))
    """Fiche the reply relies on (the "fiche proposée" of the advisor console)."""
    latency_ms: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    feedback: Mapped[Feedback | None] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class Feedback(Base):
    """Rating or intent correction of one message (customer or advisor)."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(_one_of("rating", FEEDBACK_RATINGS), name="ck_feedback_rating"),
        CheckConstraint(_one_of("author", FEEDBACK_AUTHORS), name="ck_feedback_author"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[str] = mapped_column(String(16))
    corrected_intent: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    """Masked like the messages."""
    author: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[Message] = relationship(back_populates="feedback")


class Escalade(Base):
    """Local escalation handed to an advisor (no real ticketing system: out of scope)."""

    __tablename__ = "escalade"
    __table_args__ = (
        CheckConstraint(_one_of("status", ESCALATION_STATUSES), name="ck_escalade_status"),
        Index("ix_escalade_queue", "status", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_number: Mapped[str] = mapped_column(String(16), unique=True)
    """Number given to the customer ("n° de dossier", cahier des charges Figure 3)."""
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), unique=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("message.id", ondelete="CASCADE"))
    """Message that triggered (or last raised) the escalation."""
    priority: Mapped[float] = mapped_column(Float)
    priority_level: Mapped[str] = mapped_column(String(16))
    priority_contributions: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="nouveau")
    advisor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utilisateur.id"))
    summary: Mapped[str] = mapped_column(Text)
    corrected_intent: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="escalation")
    message: Mapped[Message] = relationship()
    advisor: Mapped[Utilisateur | None] = relationship()


# --- knowledge domain --------------------------------------------------------------


class FicheKB(Base):
    """One language part of a knowledge-base fiche (``kb/`` is the source of truth)."""

    __tablename__ = "fiche_kb"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    """``<fiche id>:<lang>``, e.g. ``KB-balance_check:arabizi``."""
    fiche_id: Mapped[str] = mapped_column(String(80), index=True)
    intent: Mapped[str] = mapped_column(String(64))
    lang: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))

    chunks: Mapped[list[Chunk]] = relationship(back_populates="fiche", cascade="all, delete-orphan")


class Chunk(Base):
    """Indexed passage; ``id`` is the Qdrant point id."""

    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    fiche_kb_id: Mapped[str] = mapped_column(
        ForeignKey("fiche_kb.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    vector_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)

    fiche: Mapped[FicheKB] = relationship(back_populates="chunks")


# --- steering domain ---------------------------------------------------------------


class ModeleNLU(Base):
    """NLU model version that produced predictions."""

    __tablename__ = "modele_nlu"
    __table_args__ = (
        CheckConstraint(_one_of("status", MODEL_STATUSES), name="ck_modele_nlu_status"),
    )

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    """``<name>@<revision>``, e.g. ``v5@8e694ecf``."""
    mlflow_run: Mapped[str | None] = mapped_column(String(64))
    encoder: Mapped[str] = mapped_column(String(128))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="en_service")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluations: Mapped[list[ExecutionEvaluation]] = relationship(back_populates="model")


class ExecutionEvaluation(Base):
    """One evaluation run of a model (official test now, gold set in Phase 6)."""

    __tablename__ = "execution_evaluation"
    __table_args__ = (
        UniqueConstraint("model_version", "dataset", "source", name="uq_evaluation_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_version: Mapped[str] = mapped_column(ForeignKey("modele_nlu.version"))
    dataset: Mapped[str] = mapped_column(String(16))
    f1_macro: Mapped[float | None] = mapped_column(Float)
    ece: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    source: Mapped[str] = mapped_column(String(255))
    """Report the numbers come from (``reports/...``)."""
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    model: Mapped[ModeleNLU] = relationship(back_populates="evaluations")


class ConfigDecision(Base):
    """Decision configuration (``configs/decision.yaml``), identified by its content hash."""

    __tablename__ = "config_decision"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    """First 16 hex characters of the SHA-256 of the YAML file."""
    confidence_threshold: Mapped[float] = mapped_column(Float)
    needs_human_threshold: Mapped[float] = mapped_column(Float)
    priority_weights: Mapped[dict[str, Any]] = mapped_column(JSONType)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
