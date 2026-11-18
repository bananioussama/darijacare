# Évaluation de la recherche — val (4036 requêtes)

Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. Intention prédite par le modèle NLU `v5`. Données synthétiques. Mode de production : `nlu_prior: first`.

| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0.273 | 0.447 | 0.350 | 0.472 | 0.266 | 0.583 |
| Filtre intention prédite, classement recherche | 0.631 | 0.929 | 0.764 | 0.934 | 0.885 | 0.964 |
| Filtre prédit + priorité NLU par RRF | 0.718 | 0.950 | 0.823 | 0.947 | 0.936 | 0.974 |
| Filtre prédit + fiche de l'intention prédite en tête | 0.988 | 0.990 | 0.989 | 0.990 | 0.988 | 0.994 |
| NLU seul (intention prédite puis voisines) | 0.988 | 0.989 | 0.988 | 0.989 | 0.985 | 0.994 |
| Filtre vraie intention, classement recherche (borne) | 0.636 | 0.938 | 0.771 | 0.944 | 0.896 | 0.970 |
