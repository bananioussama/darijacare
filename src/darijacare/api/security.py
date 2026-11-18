"""Passwords (Argon2id), tokens (JWT HS256) and role checks done on the server.

Two kinds of tokens share the signing key:

* ``staff``: issued by ``POST /auth/login`` to an advisor, ML or admin account,
  valid 15 minutes (cahier des charges, Table 32);
* ``session``: issued to an anonymous customer when a conversation is opened; it
  only gives access to that conversation (a session sees only its own messages).

Roles follow the permission matrix of the cahier des charges (Table 14).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ALGORITHM = "HS256"
STAFF = "staff"
SESSION = "session"
CLIENT_ROLE = "client"

_hasher = PasswordHasher()  # Argon2id with the argon2-cffi defaults (RFC 9106 profile)


def hash_password(password: str) -> str:
    """Argon2id hash of ``password`` (salted, encoded with its parameters)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """``True`` when ``password`` matches ``password_hash``."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# A valid hash checked when the user does not exist, so that the answer time does not
# reveal which usernames exist.
DUMMY_HASH = hash_password("compte-inexistant")


@dataclass(frozen=True)
class Principal:
    """Who is calling: a staff account or an anonymous customer session."""

    kind: str
    subject: str
    """User id (staff) or session id (customer)."""
    role: str


class TokenError(Exception):
    """Invalid, expired or wrongly typed token."""


def create_token(key: str, *, subject: str, role: str, kind: str, ttl: timedelta) -> str:
    """Signed JWT with ``sub``, ``role``, ``typ``, ``iat`` and ``exp`` claims."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def decode_token(key: str, token: str) -> Principal:
    """Verify the signature and expiry of ``token`` and return its principal."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token, key, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub", "typ"]}
        )
    except jwt.InvalidTokenError as e:  # includes ExpiredSignatureError
        raise TokenError(str(e)) from e
    kind, role = claims.get("typ"), claims.get("role")
    if kind not in (STAFF, SESSION) or not isinstance(role, str):
        raise TokenError("type de jeton inconnu")
    if kind == SESSION and role != CLIENT_ROLE:
        raise TokenError("jeton de session incohérent")
    return Principal(kind, str(claims["sub"]), role)
