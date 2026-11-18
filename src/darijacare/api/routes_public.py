"""Customer-facing routes: health, NLU analysis, sessions, chat (SSE) and feedback.

Customers are anonymous: ``POST /sessions`` (or a first ``POST /chat`` without token)
opens a conversation and returns a session token. That token only gives access to its
own conversation (history, feedback): a session never sees another session's messages.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from darijacare.api.deps import (
    AppState,
    get_db,
    get_principal,
    get_state,
    rate_limit,
    require_session,
)
from darijacare.api.models import Conversation, Feedback, FicheKB, Message
from darijacare.api.schemas import (
    FeedbackIn,
    FeedbackOut,
    HealthOut,
    MessageOut,
    MessagePage,
    PredictOut,
    SessionOut,
    TextIn,
)
from darijacare.api.security import CLIENT_ROLE, SESSION, Principal, create_token
from darijacare.api.service import nlu_analysis
from darijacare.data.normalize import mask_pii
from darijacare.data.scripts import detect_script

router = APIRouter()
chat_limit = Depends(rate_limit("chat", "rate_limit_chat_per_minute"))
TOKEN_RE = re.compile(r"\S+\s*")
"""Pieces of the reply sent as ``token`` events (a word and the spaces after it)."""


@router.get("/health", response_model=HealthOut, tags=["système"])
def health(state: AppState = Depends(get_state), db: Session = Depends(get_db)) -> HealthOut:
    """State of the database, the vector store and the loaded models."""
    try:
        kb = db.scalar(select(func.count(func.distinct(FicheKB.fiche_id)))) or 0
        database = "ok"
    except Exception:  # health must answer even when the database is down
        kb, database = 0, "erreur"
    qdrant = state.qdrant_status()
    ok = database == "ok" and qdrant in ("ok", "absent")
    return HealthOut(
        status="ok" if ok else "degrade",
        database=database,
        qdrant=qdrant,
        models_loaded=True,
        nlu_model=state.model_version,
        decision_config=state.decision_config_id,
        kb_fiches=kb,
    )


@router.post("/predict", response_model=PredictOut, dependencies=[chat_limit], tags=["analyse"])
def predict(body: TextIn, state: AppState = Depends(get_state)) -> PredictOut:
    """NLU analysis of one message (guard + model), without storage."""
    guard, nlu = state.chat.analyse(body.text)
    return PredictOut(
        allowed=guard.allowed,
        refusal_reason=guard.reason,
        masked_text=guard.masked_text,
        script=nlu.script if nlu else detect_script(guard.masked_text),
        nlu=nlu_analysis(nlu),
    )


def open_session(db: Session, state: AppState) -> tuple[Conversation, SessionOut]:
    """Create a conversation and its session token (not committed)."""
    session_id = secrets.token_urlsafe(24)
    conversation = Conversation(session_id=session_id)
    db.add(conversation)
    db.flush()
    ttl = timedelta(hours=state.settings.session_ttl_hours)
    token = create_token(state.jwt_key, subject=session_id, role=CLIENT_ROLE, kind=SESSION, ttl=ttl)
    return conversation, SessionOut(
        session_id=session_id, session_token=token, expires_in=int(ttl.total_seconds())
    )


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[chat_limit],
    tags=["sessions"],
)
def create_session(
    db: Session = Depends(get_db), state: AppState = Depends(get_state)
) -> SessionOut:
    """Open an anonymous conversation."""
    _, out = open_session(db, state)
    db.commit()
    return out


def own_conversation(db: Session, principal: Principal, session_id: str) -> Conversation:
    """The conversation of ``session_id``, only if it belongs to the caller."""
    if principal.subject != session_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cette session n'est pas la vôtre.")
    conversation = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session inconnue.")
    return conversation


@router.get("/sessions/{session_id}/messages", response_model=MessagePage, tags=["sessions"])
def session_messages(
    session_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_session),
    db: Session = Depends(get_db),
) -> MessagePage:
    """History of the caller's own conversation, oldest first (paginated)."""
    conversation = own_conversation(db, principal, session_id)
    where = Message.conversation_id == conversation.id
    total = db.scalar(select(func.count()).select_from(Message).where(where)) or 0
    rows = db.scalars(
        select(Message).where(where).order_by(Message.turn).limit(limit).offset(offset)
    )
    return MessagePage(
        items=[MessageOut.model_validate(m) for m in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/sessions/{session_id}/reset",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["sessions"],
)
def reset_session(
    session_id: str,
    principal: Principal = Depends(require_session),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> SessionOut:
    """Close the conversation and open a new one (history stays readable with the old token)."""
    own_conversation(db, principal, session_id).status = "close"
    _, out = open_session(db, state)
    db.commit()
    return out


def sse(event: str, data: Any) -> str:
    """One Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/chat",
    dependencies=[chat_limit],
    tags=["chat"],
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Flux SSE : `session`, `analysis`, `token` (répété), `sources`, `done`.",
        }
    },
)
def chat(
    body: TextIn,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> StreamingResponse:
    """Process a customer message and stream the analysis, the reply and its sources.

    Without a session token, a new conversation is opened and its token is sent in the
    first event. The reply comes from templates in one piece; it is streamed word by
    word so that the interface can display it progressively.
    """
    session_event: dict[str, Any]
    if principal is not None and principal.kind == SESSION:
        conversation = db.scalar(
            select(Conversation).where(Conversation.session_id == principal.subject)
        )
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session inconnue.")
        if conversation.status == "close":
            raise HTTPException(status.HTTP_409_CONFLICT, "Session close : ouvrez-en une nouvelle.")
        session_event = {"session_id": conversation.session_id}
    else:
        conversation, out = open_session(db, state)
        session_event = out.model_dump()
    session_event["conversation_id"] = str(conversation.id)

    exchange = state.chat.handle(db, conversation, body.text)
    message, escalation = exchange.message, exchange.escalation
    events = [
        sse("session", session_event),
        sse(
            "analysis",
            {
                "message_id": str(message.id),
                "script": message.script,
                "masked_text": message.text,
                "nlu": message.analysis,
                "decision": message.decision,
            },
        ),
        *(sse("token", {"text": piece}) for piece in TOKEN_RE.findall(message.reply)),
        sse("sources", message.sources),
        sse(
            "done",
            {
                "message_id": str(message.id),
                "turn": message.turn,
                "escalation": (
                    {
                        "case_number": escalation.case_number,
                        "priority_level": escalation.priority_level,
                        "status": escalation.status,
                    }
                    if escalation
                    else None
                ),
                "latency_ms": message.latency_ms,
            },
        ),
    ]
    return StreamingResponse(
        iter(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[chat_limit],
    tags=["feedback"],
)
def feedback(
    body: FeedbackIn,
    principal: Principal = Depends(require_session),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> FeedbackOut:
    """Rate a reply of the caller's own conversation ("Utile" / "Corriger")."""
    message = db.scalar(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id == body.message_id, Conversation.session_id == principal.subject)
    )
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message introuvable dans cette session.")
    if body.corrected_intent is not None and body.corrected_intent not in state.intents:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Intention inconnue.")
    row = message.feedback
    if row is not None and row.author == "conseiller":
        raise HTTPException(status.HTTP_409_CONFLICT, "Message déjà qualifié par un conseiller.")
    if row is None:
        row = Feedback(message_id=message.id, author="client")
        db.add(row)
    row.rating = body.rating
    row.corrected_intent = body.corrected_intent if body.rating == "a_corriger" else None
    comment = (body.comment or "").strip()
    row.comment = mask_pii(comment) if comment else None
    db.commit()
    return FeedbackOut.model_validate(row)
