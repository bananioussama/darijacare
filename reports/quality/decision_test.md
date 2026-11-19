# Moteur de décision rejoué sur `test` (prédictions v5)

1107 messages. Mesure seule, aucun réglage (données synthétiques).

| Mesure | Valeur |
|---|---|
| Messages à escalader (needs_human ou urgence 3) | 150 |
| **Erreurs critiques** (non escaladés) | **40** (0.2667) |
| Taux d'escalade / précision | 0.1328 / 0.7483 |
| Taux de clarification | 0.0126 |
| Réponses automatiques : taux / exactitude | 0.8437 / 0.9015 |
| Hors périmètre : repli approprié | 0.6667 |

Actions : {"clarification": 14, "escalade": 132, "gabarit_direct": 44, "hors_perimetre": 12, "reponse_ancree": 890, "securite_escalade": 15}

Erreurs critiques par écriture : {"arabic": 24, "arabizi": 8, "mixed": 8}

Intentions des erreurs critiques : {"file_complaint": 4, "invoice_dispute": 4, "payment_not_reflected": 3, "data_not_working": 2, "refund_compensation": 2, "mm_transaction_issue": 2, "device_repair_warranty": 2, "complaint_followup": 2, "change_provider": 2, "excess_charges": 2}

## Exactitude de l'intention par `script`

| Strate | Exactitude | n |
|---|---|---|
| arabic | 0.897 | 592 |
| arabizi | 0.887 | 293 |
| mixed | 0.905 | 222 |

## Exactitude de l'intention par `ville`

| Strate | Exactitude | n |
|---|---|---|
| El Jadida | 0.934 | 167 |
| Errachidia | 0.887 | 159 |
| Laâyoune | 0.861 | 165 |
| Oujda | 0.921 | 216 |
| Safi | 0.879 | 207 |
| Tétouan | 0.891 | 193 |

## Exactitude de l'intention par `profession`

| Strate | Exactitude | n |
|---|---|---|
| café owner | 0.903 | 195 |
| construction foreman | 1.000 | 1 |
| construction site foreman | 1.000 | 1 |
| construction worker | 0.891 | 156 |
| delivery driver | 0.891 | 184 |
| elderly man helped by grandson | 1.000 | 5 |
| elderly man helped by his daughter | 1.000 | 8 |
| elderly man helped by his granddaughter | 1.000 | 14 |
| elderly man helped by his grandson | 0.889 | 27 |
| elderly man helped by his nephew | 1.000 | 1 |
| elderly man helped by his son | 0.857 | 14 |
| elderly man helped by son | 0.500 | 2 |
| elderly man's son | 1.000 | 1 |
| elderly woman helped by daughter | 1.000 | 4 |
| elderly woman helped by granddaughter | 1.000 | 1 |
| elderly woman helped by grandson | 1.000 | 1 |
| elderly woman helped by her daughter | 0.923 | 13 |
| elderly woman helped by her granddaughter | 1.000 | 16 |
| elderly woman helped by her grandson | 0.808 | 26 |
| elderly woman helped by her nephew | 0.667 | 3 |
| elderly woman helped by her niece | 0.500 | 2 |
| elderly woman helped by her son | 1.000 | 13 |
| elderly woman helped by niece | 1.000 | 1 |
| elderly woman helped by son | 1.000 | 3 |
| former café owner | 1.000 | 1 |
| high-school teacher | 0.867 | 188 |
| young graduate | 0.911 | 225 |
| young graduate paying his grandmother's line | 1.000 | 1 |

## Exactitude de l'intention par `generator`

| Strate | Exactitude | n |
|---|---|---|
| claude-opus-5.5 | 0.896 | 1107 |

## Exactitude de l'intention par `round`

| Strate | Exactitude | n |
|---|---|---|
| 1 | 0.896 | 1107 |
