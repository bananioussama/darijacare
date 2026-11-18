# Évaluation de la recherche — test (1107 requêtes)

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v5`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.275 | 0.458 | 0.355 | 0.444 | 0.396 | 0.577 |
| Filtre intention prédite, classement recherche | 0.598 | 0.870 | 0.721 | 0.872 | 0.846 | 0.896 |
| Filtre prédit + priorité NLU par RRF | 0.661 | 0.879 | 0.761 | 0.887 | 0.850 | 0.896 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.896 | 0.916 | 0.905 | 0.917 | 0.904 | 0.928 |
| NLU seul (intention prédite puis voisines) | 0.896 | 0.917 | 0.905 | 0.921 | 0.904 | 0.923 |
| Filtre vraie intention, classement recherche (borne) | 0.642 | 0.944 | 0.779 | 0.948 | 0.918 | 0.968 |
