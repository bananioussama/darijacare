"""Command line of the API.

    python -m darijacare.api.cli db-upgrade                      # Alembic migrations
    python -m darijacare.api.cli create-user --username admin --role admin
    python -m darijacare.api.cli serve [--host 127.0.0.1] [--port 8000]

``create-user`` reads the password from ``DARIJACARE_NEW_PASSWORD`` or asks for it
(never on the command line, so that it does not end up in the shell history).
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os

from darijacare.api.logging_json import configure_json_logging

MIN_PASSWORD_CHARS = 12


def alembic_config() -> object:
    """Alembic configuration of the repository (``alembic.ini``)."""
    from alembic.config import Config

    from darijacare.config import get_paths

    return Config(str(get_paths().root / "alembic.ini"))


def db_upgrade() -> None:
    """Apply every migration (``alembic upgrade head``)."""
    from alembic import command

    config = alembic_config()
    config.attributes["configure_logger"] = False  # type: ignore[attr-defined]
    command.upgrade(config, "head")  # type: ignore[arg-type]


def create_user(username: str, role: str) -> None:
    """Create a staff account; the password is hashed with Argon2id."""
    from sqlalchemy import select

    from darijacare.api.db import make_engine, make_session_factory
    from darijacare.api.models import Utilisateur
    from darijacare.api.security import hash_password
    from darijacare.api.settings import Settings

    password = os.environ.get("DARIJACARE_NEW_PASSWORD") or getpass.getpass(
        f"Mot de passe de {username} ({MIN_PASSWORD_CHARS} caractères minimum) : "
    )
    if len(password) < MIN_PASSWORD_CHARS:
        raise SystemExit(f"Mot de passe trop court ({MIN_PASSWORD_CHARS} caractères minimum).")
    engine = make_engine(Settings().sqlalchemy_url())
    try:
        with make_session_factory(engine)() as db:
            if db.scalar(select(Utilisateur).where(Utilisateur.username == username)):
                raise SystemExit(f"Le compte {username!r} existe déjà.")
            db.add(Utilisateur(username=username, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        engine.dispose()
    logging.getLogger("darijacare.api").info("compte créé (%s, rôle %s)", username, role)


def serve(host: str, port: int) -> None:
    """Run the API with uvicorn (one worker: the models are loaded in memory once)."""
    import uvicorn

    uvicorn.run(
        "darijacare.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        workers=1,
        log_config=None,
        access_log=False,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    configure_json_logging()
    parser = argparse.ArgumentParser(prog="python -m darijacare.api.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("db-upgrade", help="appliquer les migrations Alembic")
    cu = sub.add_parser("create-user", help="créer un compte conseiller, ml ou admin")
    cu.add_argument("--username", required=True)
    cu.add_argument("--role", required=True, choices=["conseiller", "ml", "admin"])
    sv = sub.add_parser("serve", help="lancer l'API (uvicorn)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.cmd == "db-upgrade":
        db_upgrade()
    elif args.cmd == "create-user":
        create_user(args.username, args.role)
    else:
        serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
