# Moteur de décision (Phase 3)

Références du cahier des charges : F-DEC-01 à F-DEC-03, Tableau 24. Configuration :
[configs/decision.yaml](../configs/decision.yaml). Code : `src/darijacare/decision/`,
`src/darijacare/guards/input_guard.py`, orchestration dans `src/darijacare/pipeline.py`.

## 1. Règles, évaluées dans l'ordre

La première règle qui s'applique décide. Chaque décision porte le numéro et le nom de la règle,
une explication en français, et elle est journalisée (`darijacare.decision`).

| # | Condition | Action | Réponse |
|---|---|---|---|
| 1 | Entrée vide, < 4 ou > 500 caractères, ou motif d'injection de prompt | Refus poli | gabarit `refuse` (raison adaptée) |
| 2 | p(needs_human) ≥ **0,30** ou urgence = 3 | Escalade prioritaire | gabarit `escalate` (+ étapes de sécurité si l'intention est `lost_stolen` ou `scam_spam_report`) |
| 3 | Intention `scam_spam_report` ou `lost_stolen` | Procédure de sécurité + escalade | gabarit `escalate` avec les étapes de la fiche |
| 4 | Intention `non_telecom` | Cadrage poli | gabarit `out_of_scope` |
| 5 | Confiance conjointe (catégorie × intention) < **0,80** | Clarification (top-2) ; si déjà clarifié au tour précédent → escalade | gabarit `clarify` (titres des deux fiches) |
| 6 | `greeting_thanks`, `agency_location`, `customer_service_contact` | Gabarit direct | `greeting` ou fiche de l'intention |
| 7 | Sinon | Réponse ancrée | fiche de l'intention (voir [rag.md](rag.md)) |

Choix documentés :

- **Ordre des règles 2 et 3** : conservé comme dans le cahier. Un vol signalé avec urgence 3
  déclenche la règle 2 ; pour ne jamais priver le client des consignes de sécurité, la réponse
  d'escalade inclut quand même les étapes de la fiche (`include_safety_procedure`).
- **Une seule clarification par tour** (F-DEC-03) : si la confiance reste basse après une
  clarification, la politique escalade au lieu de répondre au hasard (prudence).
- **Longueur minimale 4** : valeur du cahier, cohérente avec les données (le message le plus court
  du jeu fait 4 caractères, `أهلا`).

## 2. Seuils : arbitrage « prudence »

Les cibles du cahier des charges (rappel needs_human ≥ 0,85 à précision ≥ 0,70 ; 95 % d'exactitude
sur les messages répondus) sont incompatibles entre elles au niveau de précision réel du modèle
sur des messages nouveaux (voir [nlu.md](nlu.md) §4). L'arbitrage validé est la **prudence** :
escalader plutôt que risquer une mauvaise réponse automatique.

| Seuil | Valeur | Justification |
|---|---|---|
| needs_human | 0,30 | La v5 donne des probabilités très polarisées : le seuil change peu de choses ; 0,30 penche vers l'escalade. |
| confiance d'intention | 0,80 | Au test v5 (mesure d'information, non utilisée pour le choix), ~1,5 % des messages passent en clarification et n'auraient été justes qu'à 23,5 %. |
| urgence d'escalade | 3 | Cahier des charges. |

Ces valeurs sont **provisoires** : elles seront re-choisies sur la validation propre du modèle
ré-entraîné (Phase 2, entraînement sur T4).

## 3. Priorité des escalades (F-DEC-02)

```
score = 100 × (0,5 · urgence/3 + 0,3 · p(needs_human) + 0,2 · (1 − confiance)) / (0,5 + 0,3 + 0,2)
        + bonus (lost_stolen 25, scam_spam_report 25, mm_transaction_issue 10, catégorie mobile_money 5)
        plafonné à 100
```

Niveaux : critique ≥ 75, haute ≥ 50, normale ≥ 25, basse sinon. La file est triée par score
décroissant puis par ordre d'arrivée. Chaque score est accompagné de ses contributions
(urgence, needs_human, incertitude, bonus), affichables dans la console conseiller.

## 4. Garde d'entrée

- Longueur, texte vide, et 7 motifs d'injection (français / anglais : « ignore … instructions »,
  « oublie tes consignes », « system prompt », « tu es maintenant », balises `<script>`…).
- Masquage `<TEL>` / `<URL>` / `<EMAIL>` **avant** tout stockage ; le modèle NLU reçoit les numéros
  sous la forme vue à l'entraînement (`06XXXXXXXX`).
- Vérifié sur les 41 460 messages du jeu : **aucun message légitime refusé**.
- Liste volontairement courte et explicable ; elle sera éprouvée en Phase 6 (50 attaques).

## 5. Tests

`tests/unit/test_decision.py` : un test par règle (1 à 7), deux tests d'ordre des règles, la
limite de clarification, la journalisation, la priorité (bornes, monotonie, bonus), l'ordre de la
file, la garde (injection, masquage, messages courts légitimes, emojis).
