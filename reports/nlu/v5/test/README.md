# Évaluation — v5 — test

Messages : 1107 — résultats mesurés sur des données **synthétiques**.

**Intention de bout en bout : 89.6 %** (IC 95 % bootstrap : 87.8–91.4)

## Comparaison avec les chiffres publiés

| métrique | mesuré (%) | publié (%) | écart (pts) | ok |
|---|---|---|---|---|
| Intention de bout en bout | 89.6 | 89.6 | 0.0 | ✅ |
| Catégorie | 92.7 | 92.7 | 0.0 | ✅ |
| Intention sachant la catégorie (catégorie prédite juste) | 96.7 | 95.9 | 0.8 | ✅ |
| Intention avec la vraie catégorie (passe 2 forcée) | 95.9 | 95.9 | 0.0 | ✅ |
| Produit | 89.1 | 89.1 | 0.0 | ✅ |
| Urgence (niveau exact) | 80.8 | 80.8 | 0.0 | ✅ |
| needs_human | 94.7 | 94.7 | 0.0 | ✅ |
| Intention — arabic | 89.7 | 89.7 | 0.0 | ✅ |
| Intention — arabizi | 88.7 | 88.7 | 0.0 | ✅ |
| Intention — mixed | 90.5 | 90.5 | 0.0 | ✅ |


## Toutes les tâches

| tâche | exactitude (%) | F1 macro (%) |
|---|---|---|
| category | 92.7 | 90.7 |
| intent | 89.6 | 89.5 |
| product | 89.1 | 88.9 |
| urgency | 80.8 | 72.3 |
| needs_human | 94.7 | 87.5 |

QWK urgence : 0.857

## Par script

| script | n | intention bout en bout (%) | catégorie (%) | needs_human (%) |
|---|---|---|---|---|
| arabic | 592 | 89.7 | 93.6 | 94.6 |
| arabizi | 293 | 88.7 | 91.5 | 94.5 |
| mixed | 222 | 90.5 | 91.9 | 95.0 |

## Par catégorie

| catégorie | n | intention bout en bout (%) |
|---|---|---|
| billing_payment | 117 | 94.0 |
| customer_care | 100 | 93.0 |
| devices | 45 | 84.4 |
| home_internet | 103 | 97.1 |
| home_line | 103 | 89.3 |
| mobile_money | 75 | 81.3 |
| network_calls | 117 | 93.2 |
| out_of_scope | 15 | 60.0 |
| plans_subscription | 134 | 90.3 |
| prepaid_credit | 73 | 94.5 |
| sim_line | 120 | 81.7 |
| usage_mobile_data | 105 | 87.6 |

