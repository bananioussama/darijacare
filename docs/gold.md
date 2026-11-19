# Jeu « gold » : protocole et outillage (F-DAT-06)

Le jeu gold mesure ce que le jeu synthétique ne peut pas mesurer : le transfert vers des
messages écrits par de vraies personnes (cahier des charges, §22.3 et Tableau 38). Il est
**rédigé par les membres de l'équipe, locuteurs de darija**, annoté selon la taxonomie,
jamais utilisé pour l'entraînement ni pour choisir un seuil, et ouvert **une seule fois**,
pour l'évaluation finale.

> Le dépôt ne contient aucun message gold. Ces messages doivent être écrits par des
> personnes : ni générés par un modèle, ni recopiés ou retouchés depuis le jeu
> synthétique. Seul l'outillage (format, contrôles, accord, évaluation) est fourni.

## 1. Composition cible (Tableau 38)

| Partie | Part | Objet |
|---|---|---|
| Messages en écriture arabe | 35 % | Cas nominal |
| Messages en arabizi | 30 % | Variabilité orthographique |
| Messages mixtes (darija + français) | 25 % | Alternance de langues |
| Cas limites (très courts, ambigus, hors télécom, fraude) | 10 % | Décision et robustesse |

Au moins **300 messages**. La validation tolère ± 5 points sur chaque part.

## 2. Format des fichiers (`data/gold/`, versionné par DVC, jamais par git)

`gold.jsonl` : un message par ligne.

| Champ | Valeurs |
|---|---|
| `id` | identifiant unique, ex. `gold-0001` |
| `text` | le message, tel qu'un client l'écrirait (aucune donnée personnelle réelle : numéros inventés au format `06XXXXXXXX`) |
| `script` | `arabic`, `arabizi` ou `mixed` |
| `category`, `intent`, `product` | libellés de `telecom_taxonomy.json` (l'intention doit appartenir à la catégorie) |
| `urgency` | 0 à 3 |
| `needs_human` | `true` / `false` |
| `cas_limite` | `true` pour les 10 % de cas limites |
| `annotateur` | initiales de la personne qui a annoté |

Exemple de ligne (forme seulement, les valeurs entre chevrons sont à remplacer) :

```json
{"id": "gold-0001", "text": "<message écrit par un membre de l'équipe>", "script": "arabizi", "category": "<catégorie>", "intent": "<intention>", "product": "<produit>", "urgency": 1, "needs_human": false, "cas_limite": false, "annotateur": "OB"}
```

`double.jsonl` : seconde annotation, **à l'aveugle**, d'un échantillon d'au moins
60 messages (20 %) par une autre personne : `id`, `category`, `intent`, `product`,
`urgency`, `needs_human`, `annotateur`.

## 3. Guide d'annotation

1. Écrire d'abord le message comme un client, sans regarder le jeu synthétique ;
   annoter ensuite.
2. Une seule intention par message : celle qui demande une action de l'opérateur. En
   cas d'hésitation entre deux intentions, garder la plus spécifique et le noter en
   commentaire de revue.
3. `urgency` : 0 information, 1 gêne, 2 service dégradé ou argent en jeu, 3 perte,
   vol, fraude ou coupure totale (critères de la taxonomie).
4. `needs_human` : `true` quand une réponse automatique ne peut pas suffire (litige,
   fraude, demande explicite d'un conseiller, cas non couvert).
5. `script` : l'écriture dominante ; `mixed` dès qu'une phrase mélange darija et français.
6. Les désaccords de la double annotation sont discutés, puis la décision finale est
   reportée dans `gold.jsonl` (le kappa est calculé **avant** cette discussion).

## 4. Commandes

```bash
make gold-validate      # schéma, composition, doublons, proximité au synthétique, kappa
python -m darijacare.data.gold evaluate --model v5 --device cuda   # une seule fois
```

`validate` écrit `reports/gold/validation.{json,md}` et refuse le jeu si :

- un libellé est inconnu, une intention est hors de sa catégorie, un champ manque ;
- il y a moins de 300 messages ou une part s'écarte de plus de 5 points de sa cible ;
- un message est trop proche d'un message synthétique (Jaccard ≥ 0,8 sur les trigrammes
  de caractères, même contrôle que les découpages de la Phase 1) ;
- la double annotation manque, ou le kappa de Cohen est inférieur à **0,70** sur la
  catégorie ou l'intention (kappa pondéré quadratique pour l'urgence, rapporté).

`evaluate` écrit `reports/gold/evaluation_<modèle>.json` : métriques par tâche et par
écriture, et **écart synthétique → gold** (F1 macro test officiel − F1 macro gold), à
analyser et non seulement à réduire (Tableau 39).

## 5. Statut

L'outillage est prêt et testé (`tests/unit/test_gold.py`). La rédaction des messages et
la double annotation restent à faire par l'équipe ; tant qu'elles manquent, l'écart
synthétique → gold n'est pas mesuré.
