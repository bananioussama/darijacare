# NLU — reproduction, baseline, calibration, ré-entraînement (Phase 2)

Tous les résultats sont **mesurés sur des données synthétiques** (jeu `mballouch/jev-darija-telecom`).
Le test officiel (1 107 messages) n'a servi qu'à l'évaluation ; aucun hyperparamètre ni seuil n'a
été choisi dessus. Rapports détaillés : `reports/nlu/<modèle>/<split>/README.md` ; runs MLflow :
expérience `darijacare-nlu`.

## 1. Quel modèle publié ?

Le dépôt `mballouch/jev-darija-telecom-model` contient deux versions :

| Version | Révision | Entraîné sur | Intention de bout en bout (fiche) |
|---|---|---|---|
| v3 | `704030997d` | 18 350 messages = **rondes 1, 2 et 3** (11 220 + 5 148 + 1 982) | 84,6 % |
| **v5** (actuelle, = `model.safetensors` fourni) | `8e694ecf` | 40 357 messages (train complet) | **89,6 %** |

Le cahier des charges citait les chiffres de la v3 ; la v5 a déjà été ré-entraînée par l'auteur
sur tout le train. Décision (validée) : reproduire les deux, servir la v5, et écrire notre propre
ré-entraînement sur **notre** découpage.

## 2. Reproduction sur le test officiel

Inférence identique au `predict.py` publié (deux passes, questions de la taxonomie mot pour mot,
`laya 0.3.28`, `transformers 4.57.6`). Tolérance : 1 point.

| Métrique | v3 mesuré | v3 publié | v5 mesuré | v5 publié |
|---|---|---|---|---|
| Intention de bout en bout | **84,6** | 84,6 | **89,6** | 89,6 |
| Catégorie | 89,3 | 89,4 | 92,7 | 92,7 |
| Intention avec la vraie catégorie ¹ | 93,4 | 93,3 | 95,9 | 95,9 |
| Produit | 89,9 | 89,9 | 89,1 | 89,1 |
| Urgence (niveau exact) | 80,8 | 80,8 | 80,8 | 80,8 |
| needs_human | 95,3 | 95,3 | 94,7 | 94,7 |
| Intention — arabe / arabizi / mixte | 84,6 / 82,9 / 86,5 | 84,8 / 82,9 / 86,5 | 89,7 / 88,7 / 90,5 | 89,7 / 88,7 / 90,5 |

IC 95 % (bootstrap, 1 000 tirages) de l'intention de bout en bout : v3 82,4–86,7 ; v5 87,8–91,4.

¹ La fiche ne définit pas « intent given the right category ». Deux définitions ont été mesurées :
(a) exactitude de l'intention parmi les messages dont la catégorie **prédite** est juste
(v3 94,6 ; v5 96,7) et (b) deuxième passe **forcée avec la vraie catégorie** pour tous les messages
(v3 93,4 ; v5 95,9). C'est (b) qui correspond aux chiffres publiés.

**Les deux modèles publiés sont reproduits à ≤ 0,2 point sur toutes les métriques.**

Points faibles de la v5 (test) : catégorie `out_of_scope` 60 % (15 messages seulement),
`mobile_money` 81 %, `sim_line` 82 % ; urgence F1 macro 72 % (QWK 0,857) ;
needs_human F1 macro 87,5 %. Les 3 intentions les plus confondues avec chaque intention sont dans
`reports/nlu/v5/test/neighbours.json` (utilisées par le RAG en Phase 3).

## 3. Baseline TF-IDF + SVM linéaire

n-grammes de caractères 2–5 (`char_wb`) sur `text_norm`, un `LinearSVC` par tâche, catégorie
déduite de l'intention. Hyperparamètres fixés a priori (`configs/train.yaml`).

| Test officiel | Baseline | v3 | v5 |
|---|---|---|---|
| Intention de bout en bout | **86,5** | 84,6 | 89,6 |
| Catégorie | 90,7 | 89,3 | 92,7 |
| Produit | 87,6 | 89,9 | 89,1 |
| Urgence (exacte / QWK) | 76,9 / 0,781 | 80,8 / 0,837 | 80,8 / 0,857 |
| needs_human (exactitude / F1 macro) | 92,6 / 84,5 | 95,3 / 88,1 | 94,7 / 87,5 |
| Intention arabe / arabizi / mixte | 87,2 / 84,6 / 87,4 | 84,6 / 82,9 / 86,5 | 89,7 / 88,7 / 90,5 |

Constat : sur ces données synthétiques, une baseline à n-grammes de caractères (1 min 30 sur CPU)
**dépasse la v3** en intention et n'est qu'à 3 points de la v5. Le modèle neuronal garde l'avantage
sur l'urgence, needs_human et l'arabizi. Hypothèse à vérifier sur le jeu gold (Phase 6) : les
messages synthétiques ont un vocabulaire régulier, plus facile pour les n-grammes que de vrais
messages clients.

## 4. Calibration et seuils

### 4.1 Le problème de la validation contaminée

Notre validation (4 036 messages) est tirée du train officiel, sur lequel la **v5 a été entraînée** :
elle obtient **98,8 %** d'intention de bout en bout sur notre validation contre 89,6 % au test.
Ajuster des températures sur cette validation rend le modèle **plus** confiant (T ≈ 0,54–0,67) et
**dégrade** la calibration au test :

| ECE au test | températures publiées | ajustées sur notre validation |
|---|---|---|
| Catégorie | **0,027** | 0,065 |
| Intention (passe 2) | **0,062** | 0,100 |
| Intention de bout en bout | **0,045** | 0,092 |
| Produit | **0,020** | 0,098 |
| Urgence | **0,023** | 0,167 |
| needs_human | **0,036** | 0,047 |

**Décision : la v5 garde les températures publiées par l'auteur** (ajustées sur sa propre partie
retenue) ; elles respectent déjà la cible ECE ≤ 0,05 sauf pour la passe 2 seule (0,062).

### 4.2 Mesure de la contamination par ronde (validation)

| Intention de bout en bout | ronde 1 | ronde 2 | ronde 3 | ronde 4 | ronde 6 (Gemini 4 Argon) |
|---|---|---|---|---|---|
| v3 (a vu les rondes 1–3) | 97,7 | 98,5 | 97,5 | **82,2** | **71,0** |
| v5 (a vu toutes les rondes) | 98,2 | 99,1 | 98,0 | 99,0 | 99,0 |
| effectif | 1 059 | 531 | 203 | 1 542 | 701 |

1. Sur des messages vus à l'entraînement, les deux modèles atteignent ~98 % : notre validation
   n'est **pas** une mesure de généralisation pour les modèles publiés.
2. Pour la v3, les rondes 4 et 6 sont propres (jamais vues). La ronde 6, écrite par un autre
   générateur (Gemini), est nettement plus difficile (71 % contre 82 %). Le test officiel, écrit
   par Claude Opus (ronde 1), peut donc **surestimer** la performance sur des messages d'un autre
   style — argument pour le jeu gold écrit par l'équipe (Phase 6).

### 4.3 Calibration de la v3 sur un sous-ensemble propre

`python -m darijacare.nlu.cli calibrate --model v3 --fit-rounds 4 6` (2 243 messages jamais vus) :
températures ajustées proches de 1 (catégorie 1,08 ; intention 0,88 ; produit 1,07 ; urgence 1,05 ;
needs_human 1,13) et ECE au test inchangé ou légèrement dégradé. Conclusion : **les températures
publiées par l'auteur sont déjà bien calibrées**, ce qui conforte leur conservation pour la v5.

Seuils choisis selon les cibles du cahier des charges sur ce sous-ensemble propre :
- rappel needs_human ≥ 0,85 → seuil 0,08, précision 0,24 (cible 0,70 non atteinte) ;
- exactitude ≥ 95 % sur les messages répondus → couverture 0,04 % (quasi nulle).

Avec une exactitude de bout en bout de ~78 % sur des messages réellement nouveaux, ces deux cibles
sont incompatibles avec une couverture utile : elles devront être arbitrées en Phase 3 (politique
de décision : combinaison de règles et de seuils, coût d'une escalade vs d'une erreur).

### 4.4 Seuils

Les seuils définitifs (needs_human, confiance d'intention pour la clarification) seront choisis sur
la validation **propre** de notre modèle ré-entraîné. À titre d'information, la v5 mesurée au test :

- needs_human : rappel 0,745, précision 0,82 au seuil 0,5, quasiment insensible au seuil
  (probabilités très polarisées) : la cible rappel ≥ 0,85 **n'est pas atteignable par seuillage**
  avec la v5. Les règles de décision (urgence 3, fraude, vol) compléteront en Phase 3.
- confiance conjointe d'intention : 98,5 % des messages ont une confiance ≥ 0,8 ; au seuil 0,8,
  les 1,5 % restants sont justes à 23,5 % (la clarification est utile), mais l'exactitude des
  messages répondus ne passe que de 89,6 à 90,6 % : la cible « 95 % sur les messages répondus »
  n'est pas atteignable avec ce seul seuil.

## 5. Ré-entraînement sur notre découpage

`python -m darijacare.nlu.train` (et `notebooks/retrain_kaggle.ipynb`) applique le protocole de la
fiche v5 avec les briques de `laya.train` :

| Élément | Valeur | Source |
|---|---|---|
| Point de départ | `mballouch/jev-darija` @ `bf18d80a` | fiche v5 |
| Paramètres entraînés | 125 300 995 (22 blocs + têtes) ; 196 608 000 gelés (embeddings de jetons) | fiche : « 125M parameters » |
| Perte | entropie croisée souple, lissage 0,05 | fiche |
| Options | ordre mélangé (questions `choice`) | fiche |
| Optimiseur | AdamW, 3e-5 (encodeur) / 1e-4 (têtes), décroissance 0,01 | fiche ; décroissance = défaut laya |
| Planning | échauffement 6 % puis cosinus | fiche (ajouté : laya n'a que le cosinus) |
| Batch | effectif 32 (8 × 4) | fiche |
| Précision | fp16 (AMP) | fiche |
| Époques | 9, meilleure sur la validation (intention de bout en bout, inférence en deux passes) | fiche v5 |
| Températures | ajustées sur notre validation (propre pour ce modèle), `laya.calibrate` | fiche |
| Graines | 42, 43, 44 | consigne |

Questions par message : catégorie, produit, urgence, needs_human et la question d'intention de sa
propre catégorie (note de la taxonomie). Reprise automatique à la dernière époque (`state.pt`),
estimation de durée après 200 pas.

**Statut** : test de fumée réussi en local (1 époque, 64 messages : chargement, entraînement,
validation, sélection, calibration, checkpoint relu par `laya.load`). L'entraînement complet est à
lancer sur GPU T4 (Kaggle/Colab) : le GPU local (Quadro P2000, Pascal, 4 Go) exécute le fp16 à
1/64 de sa vitesse et ne convient pas. Objectif : retrouver ~89,6 % (v5) ; ≥ 88 % reste la cible du
cahier des charges. **Aucun chiffre n'est affirmé avant mesure.**

## 6. Performances d'inférence (mesurées)

| Matériel | Mode | ms / message (deux passes) |
|---|---|---|
| CPU (6 threads) | unitaire / lots | ~1 700 / ~1 850 |
| GPU Quadro P2000 | unitaire / lots de 8 | ~410 / ~280 |

Les prédictions en lots sont identiques au mode unitaire (vérifié : mêmes labels, écart de
probabilité nul). Coût élevé : chaque question embarque toutes les définitions de la taxonomie
(séquences de plusieurs centaines de jetons). Les cibles du cahier des charges (≤ 300 ms p95 CPU,
≤ 50 ms GPU) ne sont **pas** atteintes ; pistes en Phase 6 : quantification int8, GPU plus récent,
mise en cache de l'encodage de l'état.

**ONNX** : `laya` sait *exécuter* un graphe ONNX (`laya.load(backend="onnx")`, `ONNXAgent`) mais
le paquet ne fournit pas de fonction d'*export* ; un export maison serait nécessaire (option Phase 6).

## 7. Reproduire

```bash
uv sync --locked --extra pipeline --extra nlu --extra cpu      # ou --extra cu126
python -m darijacare.nlu.cli baseline
python -m darijacare.nlu.cli evaluate --model v5 --split test   # vérifie l'empreinte des poids
python -m darijacare.nlu.cli evaluate --model v5 --split val
python -m darijacare.nlu.cli calibrate --model v5
python -m darijacare.nlu.cli predict --model v5 "chargit 20dh w ma wslatni walo"
python -m darijacare.nlu.train --seeds 42                      # GPU T4 conseillé
```

Les poids ne sont pas dans git : `models/jev-darija-telecom-model/` (v5, fourni), `models/
jev-darija-telecom-model-v3/` et `models/jev-darija/` se téléchargent aux révisions figées
(voir `configs/train.yaml`, empreintes SHA-256 vérifiées).
