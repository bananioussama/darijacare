# API et base de données (Phase 4)

Références du cahier des charges :
- exigences : F-API-01, F-API-02, F-UI-04 à F-UI-06 (côté serveur), F-UI-08 (avancé) ;
- tableaux : 13 (acteurs), 14 (permissions), 32 (sécurité) ;
- figures : 3 (séquence d'escalade), 6 (diagramme de classes).

Code : `src/darijacare/api/`, migrations : `migrations/`. Données **synthétiques**, fiches **fictives**.

## 1. Lancer

Il faut un fichier `.env`, copié depuis [.env.example](../.env.example), qui contient :
- `POSTGRES_PASSWORD` ;
- `JWT_SECRET`, d'au moins 32 caractères ;
- `QDRANT_URL`.

```bash
docker compose up -d postgres qdrant
make db-upgrade      # migrations Alembic (crée les 10 tables)
python -m darijacare.api.cli create-user --username admin --role admin   # mot de passe demandé
QDRANT_URL=http://127.0.0.1:6333 make rag-index     # 1 125 passages dans le serveur Qdrant
make api             # http://127.0.0.1:8000, documentation OpenAPI sur /docs
make api-smoke       # démonstration de bout en bout -> reports/demo/phase4.md
```

Sous Windows sans `make` : `.\tasks.ps1 db-upgrade`, `.\tasks.ps1 api`, etc.

Au démarrage, environ 25 s sur CPU, l'API :
- charge **une seule fois** les modèles : NLU v5, BGE-M3 et le client Qdrant ;
- synchronise les tables de référence (voir §4).

Le conteneur de l'API est prévu en Phase 6, avec nginx et l'interface.

## 2. Routes

| Méthode et chemin | Accès | Rôle |
|---|---|---|
| `GET /health` | libre | état de la base, de Qdrant et des modèles |
| `POST /predict` | libre, limité | analyse NLU d'un message, **sans stockage** |
| `POST /sessions` | libre, limité | ouvre une conversation anonyme et renvoie un jeton de session |
| `POST /chat` | jeton de session (ou aucun : nouvelle session) | traite un message ; flux SSE (§3). `request_human: true` = bouton « Parler à un conseiller » : escalade garantie (règle 2) |
| `GET /sessions/{id}/messages` | jeton de **cette** session | historique paginé (F-UI-05) |
| `POST /sessions/{id}/reset` | jeton de cette session | ferme la conversation et en ouvre une autre |
| `POST /feedback` | jeton de session | « Utile » / « Corriger », sur ses propres messages (F-UI-04) |
| `GET /intents` | libre | les 75 intentions, leur catégorie et les titres des fiches (liste « Corriger », Phase 5) |
| `GET /fiches/{id}?lang=fr\|ar\|arabizi` | libre | une fiche (fictive) dans une langue : ce que cite une source (F-UI-03) |
| `POST /auth/login` | libre, limité | connexion du personnel : jeton de 15 minutes ; compte en attente : 403 |
| `POST /auth/register` | libre, limité | inscription du personnel (rôle demandé : conseiller ou ml) : compte **en attente**, sans connexion possible avant validation (202) |
| `GET /auth/me` | personnel | compte connecté |
| `GET /escalades` | conseiller, admin (lecture) | file triée par priorité puis par arrivée (F-UI-06) |
| `GET /escalades/{id}` | conseiller, admin (lecture) | dossier : message, analyse NLU, fiche proposée, historique |
| `PATCH /escalades/{id}` | conseiller | `prendre`, puis `cloturer` (avec correction d'intention éventuelle) |
| `GET /analytics/summary` | ml, admin | volume, taux d'escalade, latence, répartitions, feedback |
| `GET /analytics/escalades` | conseiller, ml, admin | file par statut et par niveau (vue limitée des conseillers) |
| `GET /feedback/export` | ml, admin | corrections d'intention, pour enrichir le jeu gold |
| `GET /kb/fiches`, `GET /models`, `GET /config/decision` | ml, admin | fiches, versions du modèle et évaluations, configuration active |
| `GET /admin/users`, `POST /admin/users` | admin | comptes du personnel (demandes en attente en tête) |
| `PATCH /admin/users/{id}` | admin | valider une inscription en attente et fixer son rôle (`{"action": "valider", "role": …}`) |
| `DELETE /admin/users/{id}` | admin | refuser une inscription en attente : la demande est supprimée (204) |

Les contrats (schémas Pydantic) sont publiés par FastAPI sur `/openapi.json` et `/docs`.

## 3. Flux SSE de `POST /chat`

Les événements arrivent dans cet ordre :

| Événement | Contenu |
|---|---|
| `session` | identifiant de session ; pour une nouvelle session, le jeton (24 h) |
| `analysis` | texte masqué, écriture, analyse NLU complète (top-2, probabilités), décision (règle, explication, priorité) |
| `token` (répété) | morceaux de la réponse, mot par mot |
| `sources` | fiches citées (identifiant, version et titre dans la langue de la réponse) |
| `done` | identifiant du message, tour, escalade (numéro de dossier, niveau), latences |

Les gabarits produisent la réponse d'un seul coup ; le flux la découpe pour un affichage
progressif. Avec la génération par LLM (option non activée), les morceaux suivraient la génération.

**Escalade** (séquence de la Figure 3) :
1. Le dossier est créé avec sa priorité, ses contributions et un résumé pour le conseiller.
2. Le client reçoit son **numéro de dossier** dans son écriture, par exemple
   `رقم الملف ديالك : DC-7F19B411`, `Numero dyal dossier dyalek : …` ou
   `Votre numéro de dossier : …`.
3. Une conversation n'a qu'un dossier : une nouvelle demande sur un dossier clôturé le rouvre.

## 4. Modèle de données (diagramme de classes, Figure 6)

| Classe du cahier | Table | Remarques |
|---|---|---|
| Utilisateur | `utilisateur` | personnel seulement (conseiller, ml, admin) ; hachage Argon2id ; `pending` = inscription en attente de validation (migration `0002`) ; les clients restent anonymes |
| Conversation | `conversation` | `session_id` aléatoire ; statut ouverte / escaladee / close ; état « clarification en attente » (règle 5) |
| Message | `message` | texte **masqué**, écriture, intention, catégorie, produit, urgence, needs_human, confiance, `model_version`, `decision_config_id`, règle et action, analyse complète, réponse, sources, fiche proposée, latences |
| Feedback | `feedback` | 0..1 par message ; note `utile` / `a_corriger`, intention corrigée, commentaire masqué, auteur client ou conseiller |
| Escalade | `escalade` | 0..1 par conversation ; numéro de dossier, priorité (score, niveau, contributions), motif, statut nouveau → en_cours → cloture, conseiller, résumé |
| FicheKB, Chunk | `fiche_kb`, `chunk` | copie de `kb/` (une ligne par fiche et par langue) et des 1 125 points Qdrant, réécrite au démarrage |
| ModèleNLU | `modele_nlu` | version `v5@8e694ecf`, encodeur lu dans les fichiers du modèle (`jhu-clsp/mmBERT-base`), métriques publiées et reproduites |
| ExécutionÉvaluation | `execution_evaluation` | évaluation du test officiel importée de `reports/nlu/` (F1 macro de l'intention 0,895, ECE 0,045) |
| ConfigDécision | `config_decision` | `configs/decision.yaml`, identifiée par l'empreinte SHA-256 de son contenu ; une seule active |

Chaque message enregistre la version du modèle et la configuration de décision qui l'ont
produit : un résultat est donc toujours reproductible. Les contraintes vérifient les statuts,
les rôles, l'écriture et l'urgence (0 à 3).

Le schéma vient de la migration `0001`, générée par Alembic puis relue. Un test sur PostgreSQL
vérifie qu'Alembic ne détecte aucune différence entre la migration et les modèles.

## 5. Sécurité (Tableau 32)

**Données personnelles**
- `<TEL>`, `<URL>` et `<EMAIL>` sont masqués **avant** tout stockage : messages, commentaires,
  résumés.
- Les journaux sont en JSON ; ils ne contiennent ni les messages ni les mots de passe (testé).
- Les journaux d'accès gardent la méthode, le chemin, le statut, la durée et un identifiant de
  requête.

**Mots de passe et jetons**
- Mots de passe : Argon2id (argon2-cffi). Une connexion refusée prend le même temps et donne le
  même message, que le compte existe ou non.
- Jetons JWT HS256 :
  - personnel : 15 minutes ;
  - session client : 24 h, valable pour **une seule** conversation.
- La clé de signature vient de `.env` ; l'API refuse de démarrer si elle fait moins de
  32 caractères.

**Rôles**
- Ils sont vérifiés côté serveur à chaque requête, selon le Tableau 14.
- Le compte est relu en base : un compte désactivé ou un rôle modifié prend effet tout de suite.

**Inscription du personnel**
- `POST /auth/register` crée un compte **en attente** (`pending`) avec le rôle demandé (conseiller ou ml ; personne ne peut demander le rôle admin).
- Tant qu'il n'est pas validé, le compte ne peut pas se connecter : avec le bon mot de passe, la connexion répond 403 « Compte en attente de validation par un administrateur. » ; avec un mauvais mot de passe, la réponse habituelle (401), ce qui n'apprend rien sur les comptes en attente.
- L'administrateur valide (`PATCH /admin/users/{id}`, il choisit le rôle final) ou refuse (`DELETE /admin/users/{id}` : la demande est supprimée, rien n'est conservé).
- Garde-fous : 3 inscriptions par minute et par adresse (API) en plus des limites de connexion de nginx ; au-delà de 20 demandes en attente (`max_pending_registrations`), les nouvelles sont refusées (429) ; journaux sans identifiant ni mot de passe.

**Exposition**
- Limitation de débit par adresse : 30 messages par minute ; 5 tentatives de connexion par minute.
  Derrière le frontal nginx (Phase 6), l'adresse vient de `X-Forwarded-For`, accepté seulement
  depuis le frontal ; nginx ajoute ses propres limites (`deploy/edge/limits/`).
- CORS strict : seules les origines configurées sont acceptées (l'interface Vite en développement).
- En-tête `X-Content-Type-Options: nosniff`.
- Entrées assainies avant tout stockage (Phase 6) : caractères de contrôle et invisibles
  retirés, filtre d'injection sur le texte replié (voir [securite.md](securite.md)).
- Erreur 422 sans écho de l'entrée reçue :
  `{"detail": "Requête invalide.", "errors": [{"loc": [...], "type": "..."}]}`.
- Depuis la Phase 6, seul le frontal nginx publie un port (`127.0.0.1:8443`) ; l'API n'est
  joignable que par lui (voir [deploiement.md](deploiement.md)).

## 6. Choix et limites

| Point | Choix |
|---|---|
| Matrice des permissions | Les lignes « lancer pipeline et entraînement », « publier un modèle » et « consulter les journaux » passent par DVC, MLflow et `docker logs`, pas par l'API. Les seuils de décision se changent dans `configs/decision.yaml`, fichier versionné et tracé sur chaque message par son empreinte, puis au redémarrage. |
| ONNX Runtime (F-API-01) | laya fournit `ONNXAgent` mais aucune fonction d'export : l'API sert le modèle en PyTorch. La quantification int8 a été essayée en Phase 6 et **n'est pas retenue** : les sorties changent (voir [qualite.md](qualite.md) §4). |
| Un seul processus | Les modèles sont en mémoire, un appel au modèle à la fois. La limitation de débit de l'API est en mémoire ; nginx en applique une seconde, commune à tous les processus. |
| Modèle servi | `GET /models` donne aussi `mlflow_run` : le run d'évaluation du modèle quand il est le champion du registre MLflow (`reports/nlu/registry.json`, voir [qualite.md](qualite.md) §7). |
| Qdrant | L'API utilise le serveur, avec réutilisation des connexions (voir [rag.md](rag.md) §2) : le mode local n'accepte qu'un processus. |
| Comptes | Le premier compte admin se crée en ligne de commande. Le mot de passe est demandé ou lu dans `DARIJACARE_NEW_PASSWORD`, jamais passé en argument. Ensuite, `POST /admin/users`, ou l'inscription du personnel (`POST /auth/register`) validée par un administrateur. |

## 7. Tests et mesures

- `tests/api/`, sur SQLite en mémoire, avec un NLU factice à mots-clés et les vraies politique,
  garde, fiches et gabarits. Ils couvrent :
  - l'ordre des événements SSE et le masquage ;
  - l'isolation des sessions ;
  - le feedback limité à ses messages ;
  - le cycle complet d'escalade et l'ordre de la file ;
  - la matrice des permissions, route par route et rôle par rôle ;
  - les jetons expirés, falsifiés ou désactivés ;
  - la limitation de débit et CORS ;
  - les entrées limites, qui ne renvoient jamais d'erreur 5xx (vide, un caractère, émojis,
    600 caractères, injection) ;
  - les journaux sans texte client.
- `tests/api/test_postgres.py` (marqueur `postgres`) : sur le PostgreSQL de docker-compose, une
  base temporaire est migrée, comparée aux modèles, utilisée pour un cycle complet, puis
  supprimée. Ces tests sont ignorés si le serveur est absent, comme en CI.
- Démonstration avec les vrais modèles ([reports/demo/phase4.md](../reports/demo/phase4.md)),
  en arabe, arabizi et mixte, avec escalades, console et isolation.

  Latence sur CPU, sur 20 messages :

  | Mesure | Médiane | p95 |
  |---|---|---|
  | Traitement serveur | 1,76 s | 1,84 s |
  | Requête complète vue du client | 1,81 s | 1,90 s |

  La cible « première réponse ≤ 2 s » est tenue, mais de peu : la marge viendra de la
  quantification ou du GPU (Phase 6).
