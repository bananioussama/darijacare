# Évaluation de la recherche — val (2243 requêtes, rondes [4, 6])

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v3`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.274 | 0.446 | 0.350 | 0.450 | 0.356 | 0.533 |
| Filtre intention prédite, classement recherche | 0.539 | 0.772 | 0.644 | 0.780 | 0.714 | 0.812 |
| Filtre prédit + priorité NLU par RRF | 0.600 | 0.790 | 0.686 | 0.802 | 0.728 | 0.822 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.787 | 0.814 | 0.799 | 0.823 | 0.773 | 0.833 |
| NLU seul (intention prédite puis voisines) | 0.787 | 0.816 | 0.800 | 0.824 | 0.779 | 0.833 |
| Filtre vraie intention, classement recherche (borne) | 0.626 | 0.937 | 0.765 | 0.938 | 0.917 | 0.953 |
