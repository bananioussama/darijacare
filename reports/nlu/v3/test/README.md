# Évaluation — v3 — test

Messages : 1107 — résultats mesurés sur des données **synthétiques**.

**Intention de bout en bout : 84.6 %** (IC 95 % bootstrap : 82.4–86.7)

## Comparaison avec les chiffres publiés

| métrique | mesuré (%) | publié (%) | écart (pts) | ok |
|---|---|---|---|---|
| Intention de bout en bout | 84.6 | 84.6 | 0.0 | ✅ |
| Catégorie | 89.3 | 89.4 | -0.1 | ✅ |
| Intention sachant la catégorie (catégorie prédite juste) | 94.6 | 93.3 | 1.3 | ✅ |
| Intention avec la vraie catégorie (passe 2 forcée) | 93.4 | 93.3 | 0.1 | ✅ |
| Produit | 89.9 | 89.9 | 0.0 | ✅ |
| Urgence (niveau exact) | 80.8 | 80.8 | 0.0 | ✅ |
| needs_human | 95.3 | 95.3 | 0.0 | ✅ |
| Intention — arabic | 84.6 | 84.8 | -0.2 | ✅ |
| Intention — arabizi | 82.9 | 82.9 | 0.0 | ✅ |
| Intention — mixed | 86.5 | 86.5 | 0.0 | ✅ |


## Toutes les tâches

| tâche | exactitude (%) | F1 macro (%) |
|---|---|---|
| category | 89.3 | 87.3 |
| intent | 84.6 | 84.6 |
| product | 89.9 | 89.4 |
| urgency | 80.8 | 71.9 |
| needs_human | 95.3 | 88.1 |

QWK urgence : 0.837

## Par script

| script | n | intention bout en bout (%) | catégorie (%) | needs_human (%) |
|---|---|---|---|---|
| arabic | 592 | 84.6 | 89.2 | 95.3 |
| arabizi | 293 | 82.9 | 88.7 | 94.9 |
| mixed | 222 | 86.5 | 90.5 | 95.9 |

## Par catégorie

| catégorie | n | intention bout en bout (%) |
|---|---|---|
| billing_payment | 117 | 86.3 |
| customer_care | 100 | 88.0 |
| devices | 45 | 73.3 |
| home_internet | 103 | 88.3 |
| home_line | 103 | 89.3 |
| mobile_money | 75 | 68.0 |
| network_calls | 117 | 86.3 |
| out_of_scope | 15 | 60.0 |
| plans_subscription | 134 | 88.8 |
| prepaid_credit | 73 | 89.0 |
| sim_line | 120 | 82.5 |
| usage_mobile_data | 105 | 82.9 |

