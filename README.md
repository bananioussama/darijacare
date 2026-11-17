# DarijaCare

Plateforme de service client télécom pour la **darija marocaine** : écriture arabe,
arabizi (lettres latines et chiffres 2/3/5/7/9) et darija mêlée de français.

Projet académique de fin d'année (PFA) réalisé chez inwi par Oussama BANANI,
Aymene ESSIFI et Houssam SABER. **Aucune donnée ni aucun système interne d'inwi
n'est utilisé** : le projet repose uniquement sur un jeu de données et un modèle
publics. Les données sont **synthétiques** ; tous les résultats sont donc mesurés
sur des données synthétiques.

> État : **Phase 1 — socle et pipeline de données** terminée. Les phases suivantes
> (NLU, décision, base de connaissances, API, interface) restent à faire.

## Démarrage rapide

Prérequis : [uv](https://docs.astral.sh/uv/) ≥ 0.10, Git, Docker (facultatif en Phase 1).

```bash
cd darijacare
uv sync --locked --all-extras      # Python 3.11 + dépendances figées (uv.lock)
cp .env.example .env               # puis adapter
uv run dvc repro                   # rejoue tout le pipeline de données
uv run pytest                      # tests unitaires + tests sur les données
```

Sous Windows, sans `make` : `.\tasks.ps1 repro`, `.\tasks.ps1 test`, etc.
Pensez à `PYTHONUTF8=1` si la console affiche mal l'arabe (déjà fait par
`tasks.ps1` et le `Makefile`).

### Source des données

L'étape `ingest` cherche d'abord `train.jsonl`, `test.jsonl`,
`telecom_taxonomy.json` et la fiche du dataset dans le dossier parent du dépôt
(`source.local_dir` dans [configs/data.yaml](configs/data.yaml), ou la variable
`DARIJACARE_SOURCE_DIR`). S'ils sont absents, elle les télécharge depuis le Hub
Hugging Face à la **révision figée** `2d5de707`. Dans les deux cas, chaque fichier
doit avoir l'empreinte SHA-256 attendue, sinon le pipeline s'arrête.

## Pipeline de données (Phase 1)

```
ingest ──► validate ──► normalize ──► split ──► eda
data/raw   data/interim/validated   data/processed (train / val / test)
(bronze)   data/interim/normalized  (or)          reports/
           (argent)
```

| Étape | Rôle | Sorties |
|---|---|---|
| `ingest` | Copie ou téléchargement à la révision figée, vérification SHA-256, archivage de la licence et de l'attribution | `data/raw/` |
| `validate` | Contrôles Pandera **bloquants** : labels, intention ∈ catégorie, cohérence script/texte ≥ 99 %, doublons, fuite et proximité train/test | `data/interim/validated/`, `reports/validation/` |
| `normalize` | Colonne `text_norm` (le texte d'origine est conservé) | `data/interim/normalized/`, `reports/normalize/` |
| `split` | Test officiel intact ; validation stratifiée de 10 % ; contrôle de proximité | `data/processed/`, `reports/split/` |
| `eda` | Rapport d'EDA automatique et contrôle croisé avec le Tableau 5 du cahier des charges | [reports/eda/README.md](reports/eda/README.md) |

Détails, règles et choix de conception : [docs/donnees.md](docs/donnees.md).

## Arborescence

```
darijacare/
  configs/data.yaml        paramètres du pipeline (paramètres DVC)
  src/darijacare/
    config.py, io.py       chemins, E/S déterministes
    data/                  ingest, validate, normalize, split, eda, scripts, proximity, taxonomy, cli
  tests/unit/              tests unitaires (données fictives)
  tests/data/              tests sur les vraies données (ignorés si `dvc repro` n'a pas tourné)
  reports/                 rapports générés (versionnés dans git)
  data/                    données (DVC, jamais dans git)
  tools/check_lock.py      comparaison des empreintes (CI)
  dvc.yaml, dvc.lock       pipeline et empreintes figées
  docker-compose.yml       PostgreSQL, Qdrant, MLflow
  Makefile, tasks.ps1      commandes usuelles
```

## Qualité

- `ruff` + `black` + `mypy --strict` ; hooks `pre-commit` (`make install`).
- GitHub Actions : lint et typage, tests unitaires avec couverture, et **rejeu
  complet du pipeline DVC** depuis le Hub avec comparaison des empreintes des données.

## Services (Docker Compose)

```bash
make up    # ou .\tasks.ps1 up — PostgreSQL :5432, Qdrant :6333, MLflow :5000 (localhost uniquement)
```

## Licences et crédits

Code : Apache-2.0. Données : **CC BY 4.0**, Mohamed Ballouch, *Jev-Darija Telecom*.
Voir [CREDITS.md](CREDITS.md) pour l'attribution complète et la liste des modifications.
