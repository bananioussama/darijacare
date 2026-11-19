# Test de perturbation du NLU — `test` (modèle v5)

Mesure finale sur le test officiel, aucun réglage (données synthétiques). Chemin de production : assainissement et masquage de l'entrée, puis modèle servi. Graine 42. Cible : baisse du F1 macro d'intention ≤ 5 points.

| Perturbation | Messages modifiés | F1 macro intention | Baisse (points) | Exactitude bout en bout | Cible |
|---|---|---|---|---|---|
| aucune (référence) | — | 0.8948 | — | 0.8961 | — |
| fautes | 99.8% | 0.8103 | 8.45 | 0.8121 | NON atteinte |
| translitteration | 91.0% | 0.8568 | 3.80 | 0.8573 | atteinte |
| caracteres_exotiques | 100.0% | 0.8558 | 3.90 | 0.8573 | atteinte |
| brievete | 99.2% | 0.5770 | 31.78 | 0.5827 | NON atteinte |
| mixte | 96.8% | 0.8343 | 6.05 | 0.8365 | NON atteinte |

## Baisse par écriture (points de F1 macro d'intention)

| Perturbation | arabic | arabizi | mixed |
|---|---|---|---|
| fautes | 7.37 | 11.73 | 8.83 |
| translitteration | 2.44 | 6.47 | 4.56 |
| caracteres_exotiques | 3.22 | 5.79 | 4.36 |
| brievete | 37.15 | 30.81 | 22.96 |
| mixte | 3.24 | 12.38 | 6.12 |

## Exemples (phrases d'exemple de l'interface, pas le test)

- **fautes** : `chargit 20dh w ma wslatni walo, 3afak chofo lka` · `كيفاش نشري بباس ديال الأنترنيت`
- **translitteration** : `chargit 20dh w ma wslatni walo, aafak shofo lia` · `كيفاش نشري باس ديال الانترنيت`
- **caracteres_exotiques** : `chargit 20dh w ma wslatni walo, 3afak chofo lia??? 💸` · `كيفاش نشري باس ديال اـلأنترنيت 💸`
- **brievete** : `chargit 20dh w ma wslatni` · `كيفاش نشري باس`
- **mixte** : `chargit 20dh w ma wslatnii walo, 3afak chofo lia` · `كيفاش نشري باس ديال الانترنيت`
