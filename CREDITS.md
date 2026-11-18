# Crédits

## Jeu de données

- **Titre** : *Jev-Darija Telecom: Moroccan Darija Customer-Service Messages*
- **Auteur** : Mohamed Ballouch (2026)
- **Lien** : https://huggingface.co/datasets/mballouch/jev-darija-telecom
- **Révision utilisée** : `2d5de707e8a902b371f5925224f255984c3b34bc`
- **Licence** : [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

Données synthétiques générées par des modèles de langage, non relues par des
locuteurs natifs. 26 intentions reprennent la taxonomie du jeu Bitext telco
(taxonomie uniquement, aucun texte Bitext inclus).

### Modifications apportées par DarijaCare

1. **Dédoublonnage** : 2 paires de messages identiques aux intentions divergentes
   sont retirées du train (4 lignes : `ch7al b9a?` et `الخط باسم الكاري القديم`).
2. **Normalisation** : ajout d'une colonne `text_norm` (NFKC, diacritiques, tatweel,
   alef/ya, chiffres arabo-indiens, ponctuation arabe, minuscules, allongements,
   masquage `<TEL>` / `<URL>` / `<EMAIL>`). Le texte d'origine est conservé.
3. **Découpage** : jeu de validation de 10 % tiré du train officiel (stratifié par
   intention, script et générateur, graine 42). Le test officiel est inchangé.

Les fichiers originaux sont archivés sans modification dans `data/raw/` avec
`LICENSE.txt` et `ATTRIBUTION.md`.

```bibtex
@misc{ballouch2026jevdarijatelecom,
  author       = {Ballouch, Mohamed},
  title        = {Jev-Darija Telecom: Moroccan Darija Customer-Service Messages},
  year         = {2026},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/datasets/mballouch/jev-darija-telecom}}
}
```

## Modèles

| Modèle | Révision | Rôle dans DarijaCare | Licence |
|---|---|---|---|
| [`mballouch/jev-darija-telecom-model`](https://huggingface.co/mballouch/jev-darija-telecom-model) **v5** | `8e694ecf05de3ef6cd9de14317d996d38079af83` | Modèle servi (NLU), entraîné par l'auteur sur les 40 357 messages | Apache 2.0 |
| `mballouch/jev-darija-telecom-model` **v3** | `704030997d` | Référence historique (18 350 messages), reproduite pour comparaison | Apache 2.0 |
| [`mballouch/jev-darija`](https://huggingface.co/mballouch/jev-darija) | `bf18d80a39d03176849e68d0510a87112d321d2a` | Point de départ de notre ré-entraînement | **non déclarée** sur le Hub (voir ci-dessous) |
| [Laya multilingual](https://huggingface.co/convaiinnovations/laya) (Convai Innovations) | — | Modèle de base ; bibliothèque `laya` 0.3.28 | Apache 2.0 |
| [mmBERT](https://arxiv.org/abs/2509.06888) (`jhu-clsp/mmBERT-base`) | — | Encodeur de Laya multilingual | MIT |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) (BAAI) | `5617a9f61b028005a4858fdac845db406aefb181` | Embeddings dense + creux de la base de connaissances | MIT |

Auteur des modèles `jev-darija*` : Mohamed Ballouch (2026). Les poids publiés ne sont pas
modifiés ; notre ré-entraînement produit des poids distincts, identifiés comme tels.

**Licence de `mballouch/jev-darija`.** Ce point de départ ne déclare pas de licence sur le Hub ;
sa fiche indique seulement que le modèle de base est Apache-2.0 et son encodeur MIT. Il a été
affiné sur `atlasia/moroccan_darija_domain_classifier_dataset`, qui ne déclare pas non plus de
licence. Le modèle télécom publié (Apache-2.0) en dérive déjà. Pour un usage au-delà du cadre
académique, il faudrait la confirmation de l'auteur.

Citations demandées par la fiche du modèle :

```bibtex
@misc{ballouch2026jevdarijatelecommodel,
  title        = {Jev-Darija Telecom Model: Intent Classification for Moroccan Darija Telecom Customer Messages},
  author       = {Ballouch, Mohamed}, year = {2026}, publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/mballouch/jev-darija-telecom-model}}
}
@misc{ballouch2026jevdarija,
  title        = {Jev-Darija: A Laya Classifier for 25 Topic Domains in Moroccan Darija},
  author       = {Ballouch, Mohamed}, year = {2026}, publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/mballouch/jev-darija}}
}
@misc{convai2026laya,
  title        = {Laya: Multilingual, Non-Autoregressive System 1 Decision Model},
  author       = {{Convai Innovations}}, year = {2026}, publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/convaiinnovations/laya}}
}
@misc{marone2025mmbert,
  title  = {mmBERT: A Modern Multilingual Encoder with Annealed Language Learning},
  author = {Marone, Marc and Weller, Orion and Fleshman, William and Yang, Eugene and Lawrie, Dawn and Van Durme, Benjamin},
  year   = {2025}, eprint = {2509.06888}, archivePrefix = {arXiv}, primaryClass = {cs.CL}
}
```

## Logiciels

Python, PyTorch, Transformers, laya, FlagEmbedding (MIT), qdrant-client et Qdrant (Apache-2.0),
Jinja2 (BSD), pandas, Pandera, scikit-learn, matplotlib, DVC, MLflow, huggingface_hub,
PostgreSQL — chacun sous sa propre licence open source.

API (Phase 4) :

| Bibliothèque | Licence |
|---|---|
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| Pydantic, pydantic-settings | MIT |
| SQLAlchemy, Alembic | MIT |
| psycopg 3 | LGPL-3.0, utilisé comme bibliothèque, sans modification |
| argon2-cffi | MIT |
| PyJWT | MIT |

Interface (Phase 5) :

| Bibliothèque | Licence |
|---|---|
| React, React DOM, React Router | MIT |
| Recharts | MIT |
| Vite, @vitejs/plugin-react, Vitest | MIT |
| Tailwind CSS | MIT |
| TypeScript | Apache-2.0 |
| Testing Library, jsdom, Prettier | MIT |
| Playwright | Apache-2.0 |
| Polices Inter et Noto Sans Arabic (paquets @fontsource) | SIL Open Font License 1.1 |

## Base de connaissances

Les 75 fiches de `kb/` (français, darija en écriture arabe, darija en arabizi) ont été rédigées
pour ce projet. Elles sont **fictives** : elles ne
décrivent les procédures d'aucun opérateur réel et ne contiennent ni prix, ni numéro, ni
engagement réels.
