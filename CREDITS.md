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

## Modèle (utilisé à partir de la Phase 2)

- `mballouch/jev-darija-telecom-model` (révision `8e694ecf05de3ef6cd9de14317d996d38079af83`),
  fine-tune de Laya multilingual (`convaiinnovations/laya`) — **Apache 2.0**.

## Logiciels

Python, pandas, Pandera, scikit-learn, matplotlib, DVC, huggingface_hub,
PostgreSQL, Qdrant, MLflow — chacun sous sa propre licence open source.
