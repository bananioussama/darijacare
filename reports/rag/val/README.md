# Évaluation de la recherche — val (4036 requêtes)

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v5`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.270 | 0.450 | 0.349 | 0.461 | 0.362 | 0.521 |
| Filtre intention prédite, classement recherche | 0.624 | 0.933 | 0.762 | 0.939 | 0.910 | 0.944 |
| Filtre prédit + priorité NLU par RRF | 0.699 | 0.955 | 0.814 | 0.964 | 0.930 | 0.957 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.988 | 0.990 | 0.989 | 0.990 | 0.988 | 0.994 |
| NLU seul (intention prédite puis voisines) | 0.988 | 0.989 | 0.988 | 0.989 | 0.985 | 0.994 |
| Filtre vraie intention, classement recherche (borne) | 0.629 | 0.943 | 0.769 | 0.949 | 0.922 | 0.949 |
