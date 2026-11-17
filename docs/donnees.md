# Pipeline de données — choix et règles (Phase 1)

Références du cahier des charges : F-DAT-01 à F-DAT-04, §12 (Tableaux 18 à 20).
Tous les paramètres sont dans [configs/data.yaml](../configs/data.yaml).

## 1. Ingestion (`ingest`)

- Source : `mballouch/jev-darija-telecom`, révision `2d5de707…` (commit du Hub).
- Modes : `auto` (copie locale si présente, sinon Hub), `local`, `hub`.
- Les 4 fichiers fournis dans le dossier du projet ont été comparés au Hub :
  ils sont **identiques** à cette révision (SHA-256 LFS pour `train.jsonl`,
  identifiant de blob git pour les autres). Les deux modes produisent le même `data/raw/`.
- Le manifeste ne contient ni date ni chemin local : deux exécutions donnent les mêmes empreintes.

## 2. Validation (`validate`) — tableau 20

| Contrôle | Seuil | Action | Résultat mesuré |
|---|---|---|---|
| Labels valides (script, catégorie, intention, produit, urgence, générateur, types) | 100 % | échec | ✅ |
| Intention ∈ catégorie | 100 % | échec | ✅ |
| Ids uniques ; aucun id ni texte commun train/test | 100 % | échec | ✅ |
| Cohérence script/texte | ≥ 99 % | échec ; exceptions listées | train 99,58 %, test 99,82 % |
| Doublons exacts dans un split | 0 | dédoublonnage | 2 paires (4 lignes) retirées |
| Quasi-doublons train/test même intention (Jaccard 3-grammes ≥ 0,8, texte normalisé) | 0 | échec | 0 paire |

**Doublons exacts.** Les deux paires trouvées ont des intentions différentes
(`ch7al b9a?` : `balance_check` / `check_usage` ; `الخط باسم الكاري القديم` :
`line_identification` / `ownership_transfer`). Un même texte ne peut pas avoir deux
bonnes réponses : les 4 lignes sont retirées (`duplicate_conflict_policy: drop_all`).
Le train passe de 40 357 à **40 353** lignes. `keep_first` est disponible.

**Cohérence script/texte.** Règles de la fiche du dataset : l'arabizi n'a aucune
lettre arabe ; l'arabe n'est pas majoritairement latin ; le « mixte » contient du
français (lexique de mots fréquents, élisions `l'`, `d'`, accents) ou les deux
écritures. Les exceptions (≈ 0,4 %, surtout des messages « mixtes » très courts comme
`5G f Tanger, kayna?`) sont dans `reports/validation/script_exceptions_*.csv` pour revue.

## 3. Normalisation (`normalize`) — tableau 19

Ordre fixe (chaque règle se désactive dans la config ; `enabled: false` = ablation,
seul le masquage reste actif) :

| # | Règle | Exemple |
|---|---|---|
| 1 | Unicode NFKC | `ｓａｌａｍ` → `salam` |
| 2 | Chiffres arabo-indiens → ASCII | `٢٠٠ درهم` → `200 درهم` |
| 3 | Diacritiques arabes supprimés | `بْغِيتْ` → `بغيت` |
| 4 | Tatweel supprimé | `شكـــرا` → `شكرا` |
| 5 | Alef (أ إ آ ٱ → ا), ya (ى ی → ي) | `إلى` → `الي` |
| 6 | Ponctuation arabe → latine | `،` `؟` → `,` `?` |
| 7 | Minuscules (latin) ; jetons `<TEL>` préservés | `FACTURE` → `facture` |
| 8 | Masquage URL / e-mail / téléphone | `06XXXXXXXX`, `+212 6…`, `0034XXXXXX` → `<TEL>` |
| 9 | Allongements réduits à 2 (lettres seulement) | `saaaafi` → `saafi` |
| 10 | Espaces fusionnés | |

Les chiffres ASCII ne sont **jamais** modifiés : `3lach`, `n9der`, `7ta`, `5edma`
et les montants (`1000 dh`) restent intacts. Le masquage passe avant la réduction des
allongements (sinon `06XXXXXXXX` deviendrait `06xx`). La normalisation est idempotente
et déterministe (tests unitaires). Résultat : 383 messages du train contiennent `<TEL>`.

## 4. Découpage (`split`) — §12.5

- Test officiel : **1 107 lignes inchangées** (seule la colonne `text_norm` est ajoutée).
- Validation : 10 % du train dédoublonné, stratifiée par intention × script × générateur
  (graine 42). Les strates de moins de 10 lignes passent à intention × script, puis à
  l'intention ; le reliquat forme une strate commune.
- Contrôle de proximité : toute ligne de validation à Jaccard ≥ 0,8 d'une ligne
  d'entraînement est rendue au train, puis le contrôle est revérifié.
- Écart de distribution train/validation ≤ 2 points (intention, catégorie, script,
  générateur, produit, urgence, needs_human), sinon échec.

| Split | Lignes | Remarques |
|---|---|---|
| train | 36 317 | 425–585 par intention |
| val | 4 036 | 75 intentions, 47–66 par intention ; écart max 0,54 pt |
| test | 1 107 | officiel, 13–15 par intention |

## 5. EDA (`eda`)

[reports/eda/README.md](../reports/eda/README.md) : contrôle croisé avec le Tableau 5
(toutes les valeurs concordent exactement), distributions, longueurs, déséquilibres,
co-occurrences et performance du détecteur de script heuristique.

## 6. Reproductibilité

- Toutes les sorties sont déterministes (UTF-8, fins de ligne `\n`, ordre stable,
  pas d'horodatage, PNG sans métadonnées).
- Vérifié : suppression de `data/` et `reports/`, puis `dvc repro --force` → `dvc.lock`
  **identique octet pour octet**.
- La CI rejoue le pipeline depuis le Hub sous Linux et compare les empreintes des
  données avec `tools/check_lock.py` (les figures sont exclues de cette comparaison,
  leur rendu pouvant varier d'un système à l'autre).
