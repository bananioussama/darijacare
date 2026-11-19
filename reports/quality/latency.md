# Latence du NLU (deux passes, un message à la fois)

Échantillon de la validation passé par le chemin de production (assainissement, masquage). Cibles : p95 ≤ 300 ms sur CPU, ≤ 50 ms sur GPU.

| Appareil | Variante | Threads | p50 (ms) | p95 (ms) | p99 (ms) | Exactitude intention | Cible p95 |
|---|---|---|---|---|---|---|---|
| cpu (Intel64 Family 6 Model 158 Stepping 10, GenuineIntel) | float32 (servi) | 6 | 1748.1 | 2514.2 | 2753.0 | 0.995 | NON atteinte (300 ms) |
| cpu (Intel64 Family 6 Model 158 Stepping 10, GenuineIntel) | int8 dynamique | 6 | 1497.9 | 1991.1 | 2172.8 | 0.92 | NON atteinte (300 ms) |
| cuda (Quadro P2000) | autocast fp16 (défaut de laya) | 6 | 320.7 | 356.0 | 370.1 | 0.995 | NON atteinte (50 ms) |
| cuda (Quadro P2000) | float32 (diagnostic) | 6 | 304.9 | 342.5 | 359.4 | 0.995 | NON atteinte (50 ms) |

Accord int8 / défaut (cpu) sur 200 messages : {"category": 0.95, "ecart_max_confiance_intention": 0.6738, "ecart_max_p_needs_human": 0.8842, "identiques_sur_les_5_taches": 0.74, "intent": 0.915, "needs_human": 0.985, "product": 0.945, "urgency": 0.87}

Accord fp32 / défaut (cuda) sur 200 messages : {"category": 1, "ecart_max_confiance_intention": 0.0003, "ecart_max_p_needs_human": 0.0001, "identiques_sur_les_5_taches": 1, "intent": 1, "needs_human": 1, "product": 1, "urgency": 1}
