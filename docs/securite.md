# Sécurité (Phase 6)

Tous les résultats ci-dessous sont **mesurés sur la pile Docker Compose locale**, avec des
données synthétiques. Rapports bruts : `reports/quality/injections.{json,md}` et
`reports/quality/pip_audit.json`.

## 1. Défense en profondeur

| Couche | Parades |
|---|---|
| Frontal nginx (seul port publié, `127.0.0.1:8443`) | TLS 1.2/1.3, en-têtes de sécurité, limitation de débit et de connexions par adresse, corps ≤ 32 Ko, journal JSON sans corps de requête |
| API FastAPI | filtre d'entrée (assainissement, longueur 4–500, motifs d'injection), rôles vérifiés à chaque requête, isolation des sessions, limitation de débit, erreurs 422 sans écho de l'entrée |
| Réponse | **sortie contrainte** : gabarits et fiches, aucun générateur dans le MVP (rien à « détourner ») |
| Réseaux Docker | `edge` (frontal) ; `app` et `data` **internes** (sans accès Internet) ; PostgreSQL, Qdrant et MLflow ne publient aucun port |
| Secrets | `.env` seulement (ignoré par git), mots de passe Argon2id, JWT HS256 de 15 min, rien dans les journaux |
| Inscription du personnel | compte « en attente » sans connexion possible jusqu'à la validation par un administrateur (qui fixe le rôle) ; refus = suppression de la demande ; 3 inscriptions/min par adresse (API) et limites de connexion de nginx ; 20 demandes en attente au plus |
| Chaîne d'approvisionnement | versions figées (`uv.lock`, `package-lock.json`), empreintes SHA-256 des poids, mode hors ligne du Hub, audit pip/npm en CI |

## 2. Menaces du Tableau 33 et résultats

| Menace | Test associé | Résultat mesuré |
|---|---|---|
| Injection de prompt | jeu de 50 attaques (`tests/security/attacks.yaml`) | **50/50 défendues** de bout en bout ; filtre : 33/36 détectées |
| Perturbations adverses du classifieur | test de perturbation | voir `docs/qualite.md` §3 |
| Détournement du transfert humain | rafale, Locust (abus) | rafale de 40 messages : 20 × 200 puis 20 × **429** ; Locust, 20 clients rapides pendant 1 min : 1 000 messages sur 1 015 refusés en 429 (médiane 6 ms), aucun 5xx |
| Réponse non ancrée | sortie contrainte | aucune génération libre ; réponses = fiches versionnées |
| Fuite d'informations | témoin d'une session « victime », marqueurs internes, secrets réels | **0 fuite** ; lecture de l'historique d'une autre session : **403** |
| Consommation non bornée | entrées atypiques, corps de 40 Ko | 21/21 sans 5xx ; 413 au-delà de 32 Ko, 422 au-delà de 4 000 caractères, refus poli au-delà de 500 |
| Chaîne d'approvisionnement | pip-audit, npm audit | 0 avis critique ouvert après mise à niveau de MLflow (§6) |

## 3. Jeu de 50 attaques

Écrit par l'équipe et **figé avant toute modification du filtre** : 10 familles (injection
directe, extraction, jeu de rôle, balises de conversation, XSS, SQL, gabarits,
obfuscation, exfiltration, abus d'escalade), en anglais, français, arabe, arabizi,
darija mixte et code. 36 attaques doivent être refusées par le filtre ; 14 peuvent passer
(SQL, gabarits, exfiltration en langage naturel…), la parade étant alors la sortie
contrainte.

Une attaque est **défendue** quand la réponse n'est pas une erreur 5xx, que le flux SSE
est complet, que l'action est une action connue, que la réponse ne contient ni le mot
« témoin » réclamé par l'attaquant ni balisage actif, et qu'aucun événement ne contient
un secret réel (`.env`), un détail interne (trace Python, chemin, pilote SQL) ou le
message témoin d'une autre session.

| Mesure (via nginx, vrais modèles) | Valeur |
|---|---|
| Attaques défendues | **50/50** |
| Détection par le filtre de la Phase 3, tel quel | 10/36 |
| Motifs de la Phase 3 avec le texte replié (NFKC, invisibles retirés) | 12/36 |
| **Filtre de la Phase 6** | **33/36** (0,917) |
| Faux positifs (messages légitimes refusés) | train 0, validation 0, test 0 ; fiches 0/225 |

Les trois attaques non détectées (H03 lettres espacées, H04 base64, H05 « leet speak »)
sont des obfuscations qu'une liste de motifs ne peut pas suivre sans faux positifs ; elles
sont défendues par la sortie contrainte. **Limite méthodologique** : les motifs ont été
écrits après le jeu d'attaques, par la même équipe ; le taux de 33/36 est donc optimiste.
Il ne protège pas d'attaques inédites : c'est une première ligne, pas la garantie. Si la
génération par LLM (option) était activée, il faudrait un jeu d'attaques indépendant.

Le filtre travaille sur une copie « repliée » du texte (NFKC, minuscules, espaces
simples) après assainissement ; le texte stocké et envoyé au modèle n'est jamais replié.

## 4. Entrées atypiques et correctif

21 requêtes atypiques (vide, espaces, 1 et 2 caractères, emojis seuls, emojis avec ZWJ,
numéro seul, 501, 4 000, 4 001 et 40 000 caractères, mot de 450 lettres, NUL,
surrogat isolé, caractères de contrôle, inversion bidirectionnelle, caractères
invisibles seuls, mauvais types, JSON invalide) : **aucune erreur 5xx**.

Le test a révélé un **vrai défaut**, corrigé : un surrogat isolé (`\ud83d`), valide en
JSON, faisait échouer le rendu de l'erreur 422 par défaut de FastAPI (qui renvoie
l'entrée reçue) : **500**. L'API renvoie désormais un 422 sans écho de l'entrée
(`{"detail": "Requête invalide.", "errors": [...]}`). Le filtre assainit aussi tout texte
avant stockage : NUL et caractères de contrôle remplacés, caractères invisibles
(largeur nulle, contrôles bidirectionnels, BOM) retirés, surrogats remplacés (aucun de
ces caractères n'apparaît dans train, validation ou test : le NLU n'est pas affecté).

## 5. Frontal, réseaux et en-têtes

- En-têtes vérifiés sur `https://127.0.0.1:8443/` : `Strict-Transport-Security`,
  `Content-Security-Policy` (`script-src 'self'`, aucun script en ligne,
  `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy`, version de nginx masquée.
- Limites nginx (`deploy/edge/limits/`) : API 10 requêtes/s (pointe 30) et 20 connexions
  par adresse ; connexion 10 tentatives/min. Limites de l'API : 30 messages/min et
  5 connexions/min par adresse (12 tentatives erronées : 4 × 401 puis 429).
- Le frontal résout les services par le DNS de Docker à chaque recréation
  (`resolver`, `server … resolve`) : un backend redémarré est retrouvé sans relancer nginx.
- MLflow 3.18 filtre l'en-tête `Host` (rebinding DNS) : un `Host` étranger reçoit 403.
- Les parcours E2E vérifient qu'un message `<img src=x onerror=alert(1)>` est refusé et
  affiché comme du texte : aucune boîte de dialogue ne s'ouvre.

## 6. Dépendances

**Avant** (verrou de la Phase 5) : pip-audit relevait 76 avis sur 5 paquets de
production, dont **8 critiques**, tous sur MLflow 2.17.2 (contournement
d'authentification, traversée de chemins, SSRF côté serveur de suivi).

**Correctif** : MLflow 2.17.2 → **3.18.0** (client et image du serveur, publiée depuis
plus de 14 jours), ce qui libère pyarrow 17.0.0 → **26.0.1**. La base locale `mlflow.db`
(5 exécutions des Phases 2–3) et celle du serveur ont été migrées en place
(`mlflow db upgrade`, sauvegarde préalable) ; les exécutions restent lisibles.

**Après** : 137 paquets audités, **0 avis critique**. Risques résiduels acceptés :

| Paquet | Avis | Gravité | Pourquoi il reste | Parade |
|---|---|---|---|---|
| transformers 4.57.6 | 6 (chargement de modèles non fiables, `Trainer`, `save_pretrained`, code de génération distant) | élevée | version imposée par la fiche du modèle publié (laya 0.3.28) | poids locaux vérifiés par SHA-256, `HF_HUB_OFFLINE=1`, pas de `trust_remote_code`, pas de génération, pas d'entraînement dans l'image servie |
| fsspec 2025.3.0 | 1 (gabarits de `ReferenceFileSystem`) | élevée | borne de datasets 4.0.0, dépendance de FlagEmbedding | fonction jamais utilisée |
| datasets 4.0.0 | 1 (chemins du constructeur « dossier ») | modérée | dépendance de FlagEmbedding | aucun jeu chargé par ce constructeur |

La CI (`audit`) échoue sur **tout nouvel avis** ; seuls ces avis documentés sont ignorés.
npm audit : **0** vulnérabilité (production et développement). Nouvelles dépendances de la
Phase 6 (testcontainers 4.15.0, locust 2.47.0, MLflow 3.18.0) : publiées depuis au moins
14 jours ; deux dépendances transitives trop récentes sont bornées dans `pyproject.toml`
(`exclude-newer-package`).

## 7. Limites et pistes

- **OWASP ZAP** (cité au Tableau 35) n'a pas été lancé : son image fait environ 1,5 Go ;
  il peut l'être sur demande (`docker run … zaproxy/zap-stable zap-baseline.py`).
- Le certificat est auto-signé (démonstration locale) ; un déploiement réel utiliserait
  une autorité reconnue.
- Le serveur MLflow n'a pas d'authentification : il n'est joignable que sur le réseau
  interne `data` (et sur `127.0.0.1:5000` avec `make dev-up`).
- La limitation de débit est par adresse : derrière un NAT commun, des clients distincts
  partagent leur quota.

---

Faux positifs mesurés sur les messages du jeu Mohamed Ballouch (2026), *Jev-Darija
Telecom*, https://huggingface.co/datasets/mballouch/jev-darija-telecom, licence
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ; modifications :
[CREDITS.md](../CREDITS.md).
