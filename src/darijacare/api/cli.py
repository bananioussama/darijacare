"""Command line of the API.

    python -m darijacare.api.cli db-upgrade                      # Alembic migrations
    python -m darijacare.api.cli create-user --username admin --role admin
    python -m darijacare.api.cli serve [--host 127.0.0.1] [--port 8000]
    python -m darijacare.api.cli start                           # container entry point

``create-user`` reads the password from ``DARIJACARE_NEW_PASSWORD`` or asks for it
(never on the command line, so that it does not end up in the shell history).

``start`` prepares and runs the service in its container: migrations, initial admin
account (``DARIJACARE_ADMIN_USERNAME`` / ``DARIJACARE_ADMIN_PASSWORD``, only if
missing), Qdrant index (only if missing or outdated), then the server on 0.0.0.0.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os

from darijacare.api.logging_json import configure_json_logging

MIN_PASSWORD_CHARS = 12
log = logging.getLogger("darijacare.api")


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


def add_user(username: str, role: str, password: str, *, exist_ok: bool = False) -> bool:
    """Create a staff account (Argon2id hash); return ``False`` if it already exists."""
    from sqlalchemy import select

    from darijacare.api.db import make_engine, make_session_factory
    from darijacare.api.models import Utilisateur
    from darijacare.api.security import hash_password
    from darijacare.api.settings import Settings

    if len(password) < MIN_PASSWORD_CHARS:
        raise SystemExit(f"Mot de passe trop court ({MIN_PASSWORD_CHARS} caractères minimum).")
    engine = make_engine(Settings().sqlalchemy_url())
    try:
        with make_session_factory(engine)() as db:
            if db.scalar(select(Utilisateur).where(Utilisateur.username == username)):
                if exist_ok:
                    return False
                raise SystemExit(f"Le compte {username!r} existe déjà.")
            db.add(Utilisateur(username=username, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        engine.dispose()
    log.info("compte créé (%s, rôle %s)", username, role)
    return True


def create_user(username: str, role: str) -> None:
    """Create a staff account; the password comes from the environment or a prompt."""
    password = os.environ.get("DARIJACARE_NEW_PASSWORD") or getpass.getpass(
        f"Mot de passe de {username} ({MIN_PASSWORD_CHARS} caractères minimum) : "
    )
    add_user(username, role, password)


def ensure_admin() -> None:
    """Create the initial admin account from the environment, only if it is missing."""
    username = os.environ.get("DARIJACARE_ADMIN_USERNAME", "").strip()
    password = os.environ.get("DARIJACARE_ADMIN_PASSWORD", "")
    if not username or not password:
        log.info("pas de compte admin initial (DARIJACARE_ADMIN_USERNAME/PASSWORD absents)")
        return
    if not add_user(username, "admin", password, exist_ok=True):
        log.info("compte admin initial déjà présent")


def ensure_index() -> None:
    """Index the knowledge base in Qdrant when the collection is missing or outdated."""
    from darijacare.api.settings import Settings
    from darijacare.config import get_paths
    from darijacare.rag.cli import load_rag_config, make_embedder
    from darijacare.rag.index import chunk_fiches, get_client, index_chunks, index_is_current
    from darijacare.rag.kb import load_kb

    settings = Settings()
    paths = get_paths()
    cfg = load_rag_config(paths)
    chunks = chunk_fiches(load_kb(paths.root / cfg["kb_dir"]))
    collection = cfg["qdrant"]["collection"]
    client = get_client(cfg["qdrant"], paths.root, settings.qdrant_url)
    try:
        if index_is_current(client, collection, chunks):
            log.info("index Qdrant à jour (%d passages)", len(chunks))
            return
        log.info("indexation de %d passages (BGE-M3, quelques minutes sur CPU)", len(chunks))
        stats = index_chunks(client, collection, chunks, make_embedder(paths, cfg, settings.device))
        log.info("index Qdrant : %s", stats)
    finally:
        client.close()


def serve(host: str, port: int) -> None:
    """Run the API with uvicorn (one worker: the models are loaded in memory once).

    Behind the nginx edge, ``X-Forwarded-For`` gives the client address used by the rate
    limiter; it is trusted only from ``FORWARDED_ALLOW_IPS`` (default: 127.0.0.1).
    """
    import uvicorn

    uvicorn.run(
        "darijacare.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        workers=1,
        log_config=None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
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
    sub.add_parser("ensure-index", help="indexer la base dans Qdrant si besoin")
    # serve : poste local (127.0.0.1) ; start : conteneur, joignable par le frontal seulement.
    for name, default_host in (("serve", "127.0.0.1"), ("start", "0.0.0.0")):
        sv = sub.add_parser(name, help="lancer l'API" if name == "serve" else "conteneur")
        sv.add_argument("--host", default=default_host)
        sv.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.cmd == "db-upgrade":
        db_upgrade()
    elif args.cmd == "create-user":
        create_user(args.username, args.role)
    elif args.cmd == "ensure-index":
        ensure_index()
    elif args.cmd == "start":
        db_upgrade()
        ensure_admin()
        ensure_index()
        serve(args.host, args.port)
    else:
        serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
