# Tests de charge (Locust, via le frontal HTTPS)

| Scénario | Point d'accès | Requêtes | Échecs | Req/s | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|---|---|
| base | /chat | 10 | 0 | 0.09 | 1800 | 6100 | 6100 |
| base | /sessions | 1 | 0 | 0.01 | 56 | 56 | 56 |
| base | Aggregated | 11 | 0 | 0.1 | 1800 | 6100 | 6100 |
| realiste | /chat | 99 | 0 | 0.42 | 16000 | 30000 | 33000 |
| realiste | /sessions | 20 | 0 | 0.08 | 52 | 2100 | 2100 |
| realiste | Aggregated | 119 | 0 | 0.5 | 14000 | 30000 | 31000 |
| soutenu | /chat | 71 | 0 | 0.4 | 35000 | 42000 | 48000 |
| soutenu | /sessions | 20 | 0 | 0.11 | 2400 | 6000 | 6000 |
| soutenu | Aggregated | 91 | 0 | 0.51 | 33000 | 41000 | 48000 |
| abus | /chat | 1015 | 1000 | 17.09 | 6 | 18 | 4000 |
| abus | /sessions | 20 | 5 | 0.34 | 92 | 110 | 110 |
| abus | Aggregated | 1035 | 1005 | 17.42 | 6 | 21 | 4000 |

Erreurs (abus) : {"/chat : CatchResponseError('statut 429')": 1000, "/sessions : CatchResponseError('statut 429')": 5}
