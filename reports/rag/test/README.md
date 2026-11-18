# Évaluation de la recherche — test (1107 requêtes)

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v5`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.285 | 0.451 | 0.355 | 0.458 | 0.253 | 0.694 |
| Filtre intention prédite, classement recherche | 0.611 | 0.868 | 0.728 | 0.875 | 0.826 | 0.905 |
| Filtre prédit + priorité NLU par RRF | 0.708 | 0.892 | 0.791 | 0.890 | 0.874 | 0.919 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.896 | 0.916 | 0.905 | 0.919 | 0.904 | 0.923 |
| NLU seul (intention prédite puis voisines) | 0.896 | 0.917 | 0.905 | 0.921 | 0.904 | 0.923 |
| Filtre vraie intention, classement recherche (borne) | 0.660 | 0.945 | 0.789 | 0.948 | 0.911 | 0.982 |
