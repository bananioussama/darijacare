# Déploiement local avec Docker Compose (Phase 6)

Une commande lance tout : **`make up`** (ou `.\tasks.ps1 up` sous Windows). L'interface
est ensuite servie sur **https://127.0.0.1:8443** (certificat auto-signé : le navigateur
demande une confirmation la première fois).

## 1. Prérequis

- Docker Desktop (moteur 29, Compose v5) démarré ; environ 8 Go de mémoire pour Docker.
- Les modèles dans `models/` (DVC, jamais git) : `jev-darija-telecom-model` (v5) et
  `bge-m3`. Ils sont montés **en lecture seule** dans le conteneur, pas copiés dans l'image.
- Un fichier `.env` à la racine, copié de `.env.example`, avec au moins :

| Variable | Rôle |
|---|---|
| `POSTGRES_PASSWORD` | mot de passe de la base (aléatoire) |
| `JWT_SECRET` | clé de signature des jetons (32 caractères minimum) |
| `DARIJACARE_ADMIN_USERNAME` / `DARIJACARE_ADMIN_PASSWORD` | compte administrateur créé au premier démarrage s'il n'existe pas (12 caractères minimum) |
| `EDGE_BIND` / `EDGE_PORT` | adresse et port publiés du frontal (défaut `127.0.0.1:8443`) |
| `DARIJACARE_E2E_PASSWORD` | compte conseiller des tests E2E (facultatif) |

## 2. Architecture

```
navigateur ──HTTPS──▶ edge (nginx, 127.0.0.1:8443)
                        ├── /api/* ──▶ backend (FastAPI + NLU + BGE-M3, port 8000)
                        └── /*     ──▶ frontend (nginx, fichiers statiques, port 8080)
backend / worker ──▶ postgres (16.4) · qdrant (1.20.0) · mlflow (3.18.0)
```

| Service | Image | Réseaux | Port publié | Santé |
|---|---|---|---|---|
| `edge` | nginx-unprivileged 1.31.2 | edge, app | **8443** (HTTPS) | `/healthz` (port interne 8081) |
| `frontend` | `darijacare-frontend:local` (84 Mo) | app | — | page d'accueil |
| `backend` | `darijacare-backend:local` (2,9 Go, torch CPU) | app, data | — | `/health` (base, Qdrant, modèles) |
| `worker` | même image (profil `worker`) | data | — | tâches ponctuelles |
| `postgres` | postgres 16.4-alpine | data | — | `pg_isready` |
| `qdrant` | qdrant v1.20.0 | data | — | port 6333 |
| `mlflow` | mlflow v3.18.0 | data | — | `/health` |

- **Réseaux** : `edge` porte le seul port publié ; `app` (frontal ↔ interface et API) et
  `data` (API et worker ↔ données) sont **internes** : ces conteneurs n'ont pas accès à
  Internet, et le Hub est en mode hors ligne (`HF_HUB_OFFLINE=1`).
- **Redémarrage** : `restart: unless-stopped` partout ; l'ordre de démarrage suit les
  sondes de santé (données → backend → frontal).
- **Démarrage du backend** (`python -m darijacare.api.cli start`) : migrations Alembic,
  compte administrateur initial (s'il manque), indexation Qdrant (seulement si l'index est
  absent ou différent des fiches), puis uvicorn. Il faut environ une minute pour charger
  le NLU et BGE-M3 ; la sonde de santé tolère dix minutes (première indexation sur CPU).
- **Images** : construction en plusieurs étapes ; dépendances Python figées par `uv.lock`
  (`uv sync --locked`), interface construite avec `npm ci` ; utilisateurs non root
  (UID 10001 pour l'API, nginx « unprivileged »).

## 3. Commandes

| Commande | Effet |
|---|---|
| `make up` | certificat (si absent), construction des images, lancement de la pile |
| `make down` / `make logs` | arrêt / journaux (JSON) |
| `make dev-up` | PostgreSQL, Qdrant et MLflow seuls, publiés sur `127.0.0.1` (API lancée hors conteneur avec `make api`, interface avec `make front-dev`) |
| `docker compose run --rm worker darijacare.rag.cli evaluate --split val` | tâche ponctuelle dans le conteneur `worker` |
| `docker compose exec backend python -m darijacare.api.cli create-user --username … --role conseiller` | compte supplémentaire (mot de passe demandé, jamais en argument) |
| `make certs` | régénère le certificat auto-signé (`tools/make_certs.py`, EC P-256, 365 jours, `localhost` et `127.0.0.1`) |

## 4. Vérifications faites (Phase 6)

- Les 6 services démarrent sains ; `GET /api/health` → base, Qdrant et modèles « ok ».
- L'index Qdrant existant est reconnu à jour au démarrage (1 125 passages) : pas de
  ré-indexation inutile.
- Chat en flux SSE à travers nginx : premier octet en 1,5 s environ (NLU sur CPU dans le
  conteneur) ; connexion administrateur avec le mot de passe de `.env`.
- Parcours E2E Playwright (chat, analyse, console, tableau de bord) : 4/4 sur la pile.
- MLflow 3.18 : accessible par le nom de service, en-tête `Host` étranger refusé (403).

## 5. Test de charge

Locust envoie tous les clients simulés depuis la même adresse ; les limites par adresse
(nginx et API) les bloqueraient. Le test de capacité relâche donc ces limites, le temps
du test seulement :

```bash
make load-capacity     # deploy/load/docker-compose.load.yml, puis retour aux limites normales
make load-abuse        # limites normales : des 429 sont attendus
```

Résultats : `docs/qualite.md` §5.

## 6. Dépannage

- **Port 8443 occupé** : changer `EDGE_PORT` dans `.env`.
- **Backend « unhealthy » au premier lancement** : vérifier que `models/` contient les
  poids (empreintes contrôlées au chargement) ; la première indexation prend plusieurs
  minutes sur CPU.
- **Mise à jour du code** : `docker compose build backend && docker compose up -d backend`
  (le frontal retrouve le nouveau conteneur sans redémarrer).
- **Aucun GPU dans les conteneurs** : l'image utilise torch CPU ; les évaluations lourdes
  (perturbations, latence GPU) se lancent hors conteneur avec `.venv-gpu`.
