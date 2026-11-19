"""Staff routes: login, advisor console (escalations), analytics, administration.

Permissions follow the matrix of the cahier des charges (Table 14):

==============================  ==========  ===========  =======  ======
Function                        Customer    Advisor      ML       Admin
==============================  ==========  ===========  =======  ======
Handle an escalation            --          yes          --       read
Dashboard                       --          queue only   yes      yes
Export corrections, KB, models  --          --           yes      yes
Users, validate registrations   --          --           --       yes
==============================  ==========  ===========  =======  ======

Thresholds and the decision policy are changed in ``configs/decision.yaml`` (versioned,
identified by its hash on every message), not through the API.

Staff members may register themselves (``POST /auth/register``): the account stays
``pending`` and cannot log in until an administrator validates it and sets its role
(``PATCH /admin/users/{id}``) or refuses it (``DELETE /admin/users/{id}``, the request is
deleted). Customers stay anonymous.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from darijacare.api.deps import AppState, get_db, get_state, rate_limit, require_staff
from darijacare.api.models import (
    ESCALATION_STATUSES,
    ConfigDecision,
    Escalade,
    ExecutionEvaluation,
    Feedback,
    FicheKB,
    Message,
    ModeleNLU,
    Utilisateur,
    utcnow,
)
from darijacare.api.schemas import (
    EscalationDetail,
    EscalationOut,
    EscalationUpdate,
    LoginIn,
    MessageOut,
    RegisterIn,
    RegisterOut,
    TokenOut,
    UserIn,
    UserOut,
    UserValidation,
)
from darijacare.api.security import (
    DUMMY_HASH,
    STAFF,
    create_token,
    hash_password,
    verify_password,
)

log = logging.getLogger("darijacare.api.staff")
router = APIRouter()

ADVISOR = require_staff("conseiller")
QUEUE_READERS = require_staff("conseiller", "admin")
DASHBOARD = require_staff("ml", "admin")
QUEUE_STATS = require_staff("conseiller", "ml", "admin")
ML_ADMIN = require_staff("ml", "admin")
ADMIN = require_staff("admin")
ANY_STAFF = require_staff("conseiller", "ml", "admin")
login_limit = Depends(rate_limit("login", "rate_limit_login_per_minute"))
register_limit = Depends(rate_limit("register", "rate_limit_register_per_minute"))
REGISTERED = (
    "Demande enregistrée : un administrateur doit valider le compte avant la première connexion."
)


# --- authentication ------------------------------------------------------------------


@router.post("/auth/login", response_model=TokenOut, dependencies=[login_limit], tags=["auth"])
def login(
    body: LoginIn, db: Session = Depends(get_db), state: AppState = Depends(get_state)
) -> TokenOut:
    """Staff login: Argon2id check, then a 15-minute access token."""
    user = db.scalar(select(Utilisateur).where(Utilisateur.username == body.username))
    # Same work whether the account exists or not (no username enumeration by timing).
    valid = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if user is None or not valid or not user.active:
        log.warning("connexion refusée", extra={"action": "connexion_refusee"})
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Identifiants invalides.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.pending:
        # Told only to someone who knows the password: no enumeration of pending accounts.
        log.warning(
            "connexion refusée : compte en attente", extra={"action": "connexion_en_attente"}
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Compte en attente de validation par un administrateur."
        )
    ttl = timedelta(minutes=state.settings.jwt_ttl_minutes)
    token = create_token(state.jwt_key, subject=str(user.id), role=user.role, kind=STAFF, ttl=ttl)
    log.info("connexion", extra={"action": "connexion"})
    return TokenOut(access_token=token, expires_in=int(ttl.total_seconds()), role=user.role)


@router.post(
    "/auth/register",
    response_model=RegisterOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[register_limit],
    tags=["auth"],
)
def register(
    body: RegisterIn, db: Session = Depends(get_db), state: AppState = Depends(get_state)
) -> RegisterOut:
    """Staff self-registration: a pending account that an administrator must validate."""
    waiting = db.scalar(
        select(func.count()).select_from(Utilisateur).where(Utilisateur.pending.is_(True))
    )
    if (waiting or 0) >= state.settings.max_pending_registrations:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de demandes d'inscription en attente : réessayez plus tard.",
        )
    if db.scalar(select(Utilisateur).where(Utilisateur.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Identifiant déjà utilisé.")
    db.add(
        Utilisateur(
            username=body.username,
            password_hash=hash_password(body.password),
            role=body.requested_role,
            pending=True,
        )
    )
    try:
        db.commit()
    except IntegrityError:  # same username registered at the same moment
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Identifiant déjà utilisé.") from None
    log.info("inscription demandée", extra={"action": "inscription_demandee"})
    return RegisterOut(detail=REGISTERED)


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: Utilisateur = Depends(ANY_STAFF)) -> UserOut:
    """The connected staff account."""
    return UserOut.model_validate(user)


# --- advisor console -----------------------------------------------------------------


def escalation_out(e: Escalade) -> EscalationOut:
    return EscalationOut(
        id=e.id,
        case_number=e.case_number,
        status=e.status,
        priority=round(e.priority, 2),
        priority_level=e.priority_level,
        reason=e.reason,
        summary=e.summary,
        created_at=e.created_at,
        taken_at=e.taken_at,
        closed_at=e.closed_at,
        advisor=e.advisor.username if e.advisor else None,
        intent=e.message.intent,
        script=e.message.script,
        corrected_intent=e.corrected_intent,
    )


@router.get("/escalades", response_model=list[EscalationOut], tags=["escalades"])
def escalation_queue(
    statuses: list[str] = Query(["nouveau", "en_cours"], alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: Utilisateur = Depends(QUEUE_READERS),
    db: Session = Depends(get_db),
) -> list[EscalationOut]:
    """Queue sorted by priority (highest first), then by arrival time."""
    unknown = set(statuses) - set(ESCALATION_STATUSES)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Statut inconnu : {sorted(unknown)}"
        )
    rows = db.scalars(
        select(Escalade)
        .where(Escalade.status.in_(statuses))
        .order_by(Escalade.priority.desc(), Escalade.created_at.asc(), Escalade.case_number)
        .limit(limit)
        .offset(offset)
    )
    return [escalation_out(e) for e in rows]


def get_escalation(db: Session, escalation_id: uuid.UUID) -> Escalade:
    escalation = db.get(Escalade, escalation_id)
    if escalation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escalade introuvable.")
    return escalation


@router.get("/escalades/{escalation_id}", response_model=EscalationDetail, tags=["escalades"])
def escalation_detail(
    escalation_id: uuid.UUID,
    _user: Utilisateur = Depends(QUEUE_READERS),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> EscalationDetail:
    """Case file: message, NLU analysis, proposed fiche and conversation history."""
    e = get_escalation(db, escalation_id)
    message = e.message
    fiche = state.fiches.get(message.intent) if message.intent else None
    proposed = (
        {
            "id": fiche.id,
            "version": fiche.version,
            "title": fiche.titles["fr"],
            "etapes": list(fiche.sections["fr"]["etapes"]),
            "escalade": fiche.sections["fr"]["escalade"],
        }
        if fiche
        else None
    )
    history = db.scalars(
        select(Message).where(Message.conversation_id == e.conversation_id).order_by(Message.turn)
    )
    return EscalationDetail(
        **escalation_out(e).model_dump(),
        priority_contributions=e.priority_contributions,
        message=MessageOut.model_validate(message),
        analysis=message.analysis,
        proposed_fiche=proposed,
        history=[MessageOut.model_validate(m) for m in history],
    )


@router.patch("/escalades/{escalation_id}", response_model=EscalationOut, tags=["escalades"])
def update_escalation(
    escalation_id: uuid.UUID,
    body: EscalationUpdate,
    user: Utilisateur = Depends(ADVISOR),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> EscalationOut:
    """``prendre`` (nouveau -> en_cours), then ``cloturer`` (en_cours -> cloture).

    Closing may correct the intent: the correction is stored on the escalation and as
    advisor feedback on the triggering message (exportable to enrich the gold set).
    """
    e = get_escalation(db, escalation_id)
    now = utcnow()
    if body.action == "prendre":
        if e.status != "nouveau":
            raise HTTPException(status.HTTP_409_CONFLICT, "Escalade déjà prise ou clôturée.")
        e.status, e.advisor_id, e.taken_at = "en_cours", user.id, now
    else:
        if e.status != "en_cours":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Seule une escalade en cours peut être clôturée."
            )
        if e.advisor_id != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Escalade prise par un autre conseiller."
            )
        if body.corrected_intent is not None:
            if body.corrected_intent not in state.intents:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Intention inconnue.")
            e.corrected_intent = body.corrected_intent
            message = e.message
            row = message.feedback or Feedback(message_id=message.id, author="conseiller")
            row.author = "conseiller"
            row.rating = "utile" if body.corrected_intent == message.intent else "a_corriger"
            row.corrected_intent = body.corrected_intent
            row.comment = None
            db.add(row)
        e.status, e.closed_at = "cloture", now
        if e.conversation.status == "escaladee":
            e.conversation.status = "ouverte"
    db.commit()
    log.info("escalade mise à jour", extra={"escalation": e.case_number, "action": body.action})
    return escalation_out(e)


# --- analytics -----------------------------------------------------------------------


@router.get("/analytics/summary", tags=["analytique"])
def analytics_summary(
    days: int = Query(30, ge=1, le=365),
    _user: Utilisateur = Depends(DASHBOARD),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Volume, escalation rate, latency, split by script / decision / intent, feedback."""
    since = utcnow() - timedelta(days=days)
    recent = Message.created_at >= since

    def counts(column: Any) -> dict[str, int]:
        rows = db.execute(select(column, func.count()).where(recent).group_by(column)).all()
        return {str(k): int(n) for k, n in rows}

    total = int(db.scalar(select(func.count()).select_from(Message).where(recent)) or 0)
    escalations = int(
        db.scalar(select(func.count()).select_from(Escalade).where(Escalade.created_at >= since))
        or 0
    )
    top = db.execute(
        select(Message.intent, func.count())
        .where(recent, Message.intent.is_not(None))
        .group_by(Message.intent)
        .order_by(func.count().desc(), Message.intent)
        .limit(10)
    ).all()
    latencies = [
        float(lat["total"])
        for lat in db.scalars(
            select(Message.latency_ms).where(recent).order_by(Message.created_at.desc()).limit(5000)
        )
        if lat and "total" in lat
    ]
    ratings = db.execute(
        select(Feedback.rating, func.count())
        .where(Feedback.created_at >= since)
        .group_by(Feedback.rating)
    ).all()
    evaluation = None
    if state.model_version:
        ev = db.scalar(
            select(ExecutionEvaluation)
            .where(ExecutionEvaluation.model_version == state.model_version)
            .order_by(ExecutionEvaluation.evaluated_at.desc())
        )
        if ev is not None:
            evaluation = {"dataset": ev.dataset, "f1_macro": ev.f1_macro, "ece": ev.ece}
    return {
        "periode_jours": days,
        "messages": total,
        "escalades": escalations,
        "taux_escalade": round(escalations / total, 4) if total else 0.0,
        "latence_ms": {
            "p50": round(float(np.percentile(latencies, 50)), 1) if latencies else None,
            "p95": round(float(np.percentile(latencies, 95)), 1) if latencies else None,
        },
        "par_script": counts(Message.script),
        "par_decision": counts(Message.decision_action),
        "top_intentions": [{"intent": k, "messages": int(n)} for k, n in top],
        "feedback": {str(k): int(n) for k, n in ratings},
        "modele": {"version": state.model_version, "evaluation": evaluation},
    }


@router.get("/analytics/escalades", tags=["analytique"])
def analytics_escalations(
    _user: Utilisateur = Depends(QUEUE_STATS), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Queue counts by status and priority level (advisors' limited view of the dashboard)."""
    by_status = db.execute(select(Escalade.status, func.count()).group_by(Escalade.status)).all()
    by_level = db.execute(
        select(Escalade.priority_level, func.count())
        .where(Escalade.status != "cloture")
        .group_by(Escalade.priority_level)
    ).all()
    return {
        "par_statut": {str(k): int(n) for k, n in by_status},
        "ouvertes_par_niveau": {str(k): int(n) for k, n in by_level},
    }


# --- ML / data -----------------------------------------------------------------------


@router.get("/feedback/export", tags=["feedback"])
def export_corrections(
    _user: Utilisateur = Depends(ML_ADMIN), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """Intent corrections (customers and advisors), to enrich the gold set."""
    rows = db.execute(
        select(Feedback, Message)
        .join(Message, Feedback.message_id == Message.id)
        .where(Feedback.corrected_intent.is_not(None))
        .order_by(Feedback.created_at)
    ).all()
    return [
        {
            "message_id": str(m.id),
            "text": m.text,
            "script": m.script,
            "predicted_intent": m.intent,
            "corrected_intent": f.corrected_intent,
            "author": f.author,
            "model_version": m.model_version,
            "created_at": f.created_at,
        }
        for f, m in rows
    ]


@router.get("/kb/fiches", tags=["base de connaissances"])
def kb_fiches(
    _user: Utilisateur = Depends(ML_ADMIN), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """Fiches of the knowledge base (edited in ``kb/``, mirrored at start-up)."""
    rows = db.scalars(select(FicheKB).order_by(FicheKB.fiche_id, FicheKB.lang))
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        item = out.setdefault(
            r.fiche_id,
            {"id": r.fiche_id, "intent": r.intent, "version": r.version, "status": r.status},
        )
        item.setdefault("titles", {})[r.lang] = r.title
    return list(out.values())


@router.get("/models", tags=["modèles"])
def models(
    _user: Utilisateur = Depends(ML_ADMIN), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """NLU model versions and their evaluations."""
    return [
        {
            "version": m.version,
            "encoder": m.encoder,
            "status": m.status,
            "mlflow_run": m.mlflow_run,
            "metrics": m.metrics,
            "evaluations": [
                {"dataset": e.dataset, "f1_macro": e.f1_macro, "ece": e.ece, "source": e.source}
                for e in m.evaluations
            ],
        }
        for m in db.scalars(select(ModeleNLU).order_by(ModeleNLU.registered_at))
    ]


@router.get("/config/decision", tags=["configuration"])
def decision_config(
    _user: Utilisateur = Depends(ML_ADMIN), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Active decision configuration (read only: it lives in ``configs/decision.yaml``)."""
    row = db.scalar(select(ConfigDecision).where(ConfigDecision.active.is_(True)))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune configuration active.")
    return {"id": row.id, "content": row.content, "created_at": row.created_at}


# --- administration ------------------------------------------------------------------


@router.post(
    "/admin/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["administration"],
)
def create_user(
    body: UserIn, _admin: Utilisateur = Depends(ADMIN), db: Session = Depends(get_db)
) -> UserOut:
    """Create a staff account (password stored as an Argon2id hash)."""
    if db.scalar(select(Utilisateur).where(Utilisateur.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Identifiant déjà utilisé.")
    user = Utilisateur(
        username=body.username, password_hash=hash_password(body.password), role=body.role
    )
    db.add(user)
    db.commit()
    log.info("compte créé", extra={"action": "creation_compte"})
    return UserOut.model_validate(user)


@router.get("/admin/users", response_model=list[UserOut], tags=["administration"])
def list_users(
    _admin: Utilisateur = Depends(ADMIN), db: Session = Depends(get_db)
) -> list[UserOut]:
    """Staff accounts, pending registrations first."""
    return [
        UserOut.model_validate(u)
        for u in db.scalars(
            select(Utilisateur).order_by(Utilisateur.pending.desc(), Utilisateur.username)
        )
    ]


def pending_account(db: Session, user_id: uuid.UUID) -> Utilisateur:
    """The pending account ``user_id`` (404 if unknown, 409 if already validated)."""
    user = db.get(Utilisateur, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    if not user.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ce compte n'est pas en attente de validation."
        )
    return user


@router.patch("/admin/users/{user_id}", response_model=UserOut, tags=["administration"])
def validate_user(
    user_id: uuid.UUID,
    body: UserValidation,
    _admin: Utilisateur = Depends(ADMIN),
    db: Session = Depends(get_db),
) -> UserOut:
    """Validate a self-registration and set its role: the account can then log in."""
    user = pending_account(db, user_id)
    user.pending = False
    user.role = body.role
    db.commit()
    log.info("inscription validée", extra={"action": "inscription_validee"})
    return UserOut.model_validate(user)


@router.delete(
    "/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["administration"]
)
def refuse_user(
    user_id: uuid.UUID, _admin: Utilisateur = Depends(ADMIN), db: Session = Depends(get_db)
) -> Response:
    """Refuse a self-registration: the request is deleted, nothing about it is kept."""
    db.delete(pending_account(db, user_id))
    db.commit()
    log.info("inscription refusée", extra={"action": "inscription_refusee"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
