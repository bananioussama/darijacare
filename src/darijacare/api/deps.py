"""Shared state and FastAPI dependencies: database session, caller identity, roles, limits.

Role checks are done on the server for every request (cahier des charges, Table 14):
the token says who calls, and the account is re-read from the database so that a
deactivated user or a changed role takes effect at once.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from darijacare.api.models import Utilisateur
from darijacare.api.ratelimit import RateLimiter
from darijacare.api.security import SESSION, STAFF, Principal, TokenError, decode_token
from darijacare.api.service import ChatService
from darijacare.api.settings import Settings
from darijacare.rag.kb import Fiche


@dataclass
class AppState:
    """Everything loaded once at start-up and shared by the requests."""

    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    jwt_key: str
    limiter: RateLimiter
    chat: ChatService
    fiches: dict[str, Fiche]
    decision_config_id: str
    model_version: str | None
    qdrant_status: Callable[[], str]
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def intents(self) -> frozenset[str]:
        """Valid intents (one fiche per taxonomy intent, checked by ``validate-kb``)."""
        return frozenset(self.fiches)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.dc
    return state


def get_db(state: AppState = Depends(get_state)) -> Iterator[Session]:
    with state.sessions() as db:
        yield db


_bearer = HTTPBearer(auto_error=False, description="Jeton de session client ou jeton conseiller")


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    state: AppState = Depends(get_state),
) -> Principal | None:
    """Caller identity from the ``Authorization: Bearer`` header (``None`` if absent)."""
    if creds is None:
        return None
    try:
        return decode_token(state.jwt_key, creds.credentials)
    except TokenError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Jeton invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_session(principal: Principal | None = Depends(get_principal)) -> Principal:
    """An anonymous customer session."""
    if principal is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Session requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if principal.kind != SESSION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à une session client.")
    return principal


def require_staff(*roles: str) -> Callable[..., Utilisateur]:
    """Dependency accepting active staff accounts whose role is in ``roles``."""

    def dependency(
        principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db)
    ) -> Utilisateur:
        if principal is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Authentification requise.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if principal.kind != STAFF or principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rôle insuffisant.")
        try:
            user = db.get(Utilisateur, uuid.UUID(principal.subject))
        except ValueError:
            user = None
        if user is None or not user.active or user.role != principal.role:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Compte inactif ou modifié : reconnectez-vous.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    return dependency


def rate_limit(bucket: str, setting: str) -> Callable[..., None]:
    """Dependency limiting each client address to ``settings.<setting>`` calls per minute."""

    def dependency(request: Request, state: AppState = Depends(get_state)) -> None:
        limit = int(getattr(state.settings, setting))
        key = request.client.host if request.client else "inconnu"
        wait = state.limiter.hit(bucket, key, limit)
        if wait is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Trop de requêtes, réessayez dans un instant.",
                headers={"Retry-After": str(int(wait) + 1)},
            )

    return dependency
