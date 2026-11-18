# Évaluation de la recherche — val (2243 requêtes, rondes [4, 6])

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v3`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.277 | 0.438 | 0.347 | 0.464 | 0.266 | 0.552 |
| Filtre intention prédite, classement recherche | 0.550 | 0.775 | 0.650 | 0.781 | 0.722 | 0.816 |
| Filtre prédit + priorité NLU par RRF | 0.613 | 0.787 | 0.691 | 0.788 | 0.750 | 0.822 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.787 | 0.815 | 0.800 | 0.823 | 0.779 | 0.831 |
| NLU seul (intention prédite puis voisines) | 0.787 | 0.816 | 0.800 | 0.824 | 0.779 | 0.833 |
| Filtre vraie intention, classement recherche (borne) | 0.632 | 0.938 | 0.768 | 0.937 | 0.915 | 0.968 |
