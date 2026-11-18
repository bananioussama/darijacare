"""Request and response bodies (Pydantic). They define the OpenAPI contract of the API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_INPUT_CHARS = 4000
"""Above this size the request is rejected (422). Between the guard limit (500) and this
one, the message is accepted and politely refused by decision rule 1."""


class TextIn(BaseModel):
    """A customer message."""

    text: str = Field(max_length=MAX_INPUT_CHARS, examples=["solde dyali sala bzerba, 3lach?"])


class PredictOut(BaseModel):
    """NLU analysis without storage (``POST /predict``)."""

    allowed: bool
    refusal_reason: str | None
    masked_text: str
    script: str
    nlu: dict[str, Any] | None


class SessionOut(BaseModel):
    """A new anonymous session."""

    session_id: str
    session_token: str
    expires_in: int
    """Seconds."""


class FeedbackIn(BaseModel):
    """Rating of an assistant reply by the customer."""

    message_id: uuid.UUID
    rating: Literal["utile", "a_corriger"]
    corrected_intent: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    rating: str
    corrected_intent: str | None
    comment: str | None
    author: str
    created_at: datetime


class MessageOut(BaseModel):
    """One exchange: masked customer text, analysis, decision and reply."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    turn: int
    created_at: datetime
    text: str
    script: str
    intent: str | None
    category: str | None
    product: str | None
    urgency: int | None
    needs_human: bool | None
    confidence: float | None
    decision_rule: int
    decision_action: str
    reply: str
    sources: list[dict[str, Any]]
    fiche_id: str | None


class MessagePage(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    role: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=12, max_length=256)
    role: Literal["conseiller", "ml", "admin"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: str
    active: bool
    created_at: datetime


class EscalationOut(BaseModel):
    """Line of the advisor queue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_number: str
    status: str
    priority: float
    priority_level: str
    reason: str
    summary: str
    created_at: datetime
    taken_at: datetime | None
    closed_at: datetime | None
    advisor: str | None = None
    intent: str | None = None
    script: str | None = None
    corrected_intent: str | None = None


class EscalationDetail(EscalationOut):
    """Escalation with its context (message, NLU analysis, proposed fiche, history)."""

    priority_contributions: dict[str, float]
    message: MessageOut
    analysis: dict[str, Any] | None
    proposed_fiche: dict[str, Any] | None
    history: list[MessageOut]


class EscalationUpdate(BaseModel):
    """Advisor action: take the case, then close it (optionally correcting the intent)."""

    action: Literal["prendre", "cloturer"]
    corrected_intent: str | None = Field(default=None, max_length=64)


class HealthOut(BaseModel):
    status: Literal["ok", "degrade"]
    database: str
    qdrant: str
    models_loaded: bool
    nlu_model: str | None
    decision_config: str | None
    kb_fiches: int
