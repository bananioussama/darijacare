# Qualité, tests et évaluation finale (Phase 6)

Tous les chiffres sont **mesurés sur des données synthétiques** (jeu public
`mballouch/jev-darija-telecom`), avec le modèle publié v5. Le test officiel n'a servi
qu'à mesurer : aucun seuil ni hyperparamètre n'a été choisi dessus. Quand une cible du
cahier des charges n'est pas atteinte, le chiffre réel est donné avec son explication.

## 1. Synthèse des cibles

| Cible (cahier des charges) | Mesure | Statut |
|---|---|---|
| Couverture des tests ≥ 70 % | 80 % (285 tests réussis, 2 ignorés) | atteinte |
| Intégration API ↔ PostgreSQL ↔ Qdrant (Testcontainers) | 3/3 | atteinte |
| Parcours Playwright chat, analyse, console, tableau de bord | 4/4 sur la pile | atteinte |
| 50 attaques, aucune vulnérabilité critique ouverte | 50/50 défendues ; 0 avis critique | atteinte ([securite.md](securite.md)) |
| Aucune 5xx sur les entrées atypiques | 21/21 | atteinte (après correctif) |
| Non-régression : aucune baisse > 1 point de F1 macro sans justification | contrôle à la promotion | en place (§7) |
| Erreurs critiques : à minimiser, suivi dédié | 40/150 (26,7 %) | **suivi** (§2) |
| Repli approprié hors périmètre ≥ 90 % | 66,7 % (10 sur 15) | **non atteinte** (§2) |
| Robustesse : baisse de F1 ≤ 5 points | translittération 3,8 ; caractères exotiques 3,9 ; mixte 6,1 ; fautes 8,5 ; brièveté 31,8 | **atteinte pour 2 sur 5** (§3) |
| NLU p95 ≤ 300 ms (CPU), ≤ 50 ms (GPU) | CPU 2 514 ms ; GPU 356 ms | **non atteinte** (§4) |
| Première réponse ≤ 2 s | 1,8 s en médiane pour un client seul | atteinte hors charge (§5) |
| 20 requêtes simultanées sans dégradation notable | débit 0,42 msg/s, attente médiane 16 s à 20 clients | **non atteinte** (§5) |
| Redémarrage automatique, sondes de santé | backend relancé seul, API de retour en 70 s | atteinte (§6) |

## 2. Décision rejouée sur le test officiel

`python -m darijacare.quality.cli decision --split test` rejoue le filtre d'entrée et la
politique (`configs/decision.yaml`) sur les 1 107 messages du test, à partir des
prédictions v5 enregistrées en Phase 2 (`reports/quality/decision_test.md`).

| Mesure | Valeur |
|---|---|
| Messages à escalader (needs_human ou urgence 3) | 150 |
| **Erreurs critiques** (à escalader mais non escaladés) | **40 (26,7 %)** : arabe 24, arabizi 8, mixte 8 |
| Taux d'escalade / précision | 13,3 % / 74,8 % |
| Taux de clarification | 1,3 % |
| Réponses automatiques : taux / exactitude de la fiche | 84,4 % / 90,2 % |
| Hors périmètre : repli approprié | 66,7 % (10 sur 15) |

**Pourquoi 26,7 % d'erreurs critiques.** Elles viennent du rappel de needs_human du
modèle v5 (0,745 au test, Phase 2) : sur les 41 messages manqués par la règle
« needs_human ou urgence 3 », la probabilité needs_human médiane est de **0,06** (90e
centile 0,08). Le modèle est sûr de lui, à tort : aucun seuil entre 0,06 et 0,30 ne les
rattraperait sans escalader presque tout. Ce diagnostic est une mesure ; le seuil (0,30)
a été choisi en Phase 3 sur la validation et n'a pas été modifié. La correction passe par
le ré-entraînement (pondération de needs_human, données de fraude et de litige), à
re-mesurer sur la validation propre puis une seule fois sur le test.

**Repli hors périmètre.** 5 des 15 messages hors télécom reçoivent une réponse
automatique (4 fiches, 1 gabarit) : le NLU les a classés dans une intention télécom
(frais de résiliation, achat d'appareil, moyens de paiement…). 15 messages ne suffisent
pas à une conclusion solide, mais l'écart à la cible (90 %) est réel ; il dépend du NLU,
pas de la politique.

**Équité** (exactitude de l'intention de bout en bout) : par écriture arabe 0,897,
arabizi 0,887, mixte 0,905 ; par ville de 0,861 (Laâyoune) à 0,934 (El Jadida) ; les
strates par profession, générateur et ronde sont dans le rapport.

## 3. Test de perturbation (robustesse)

`make quality-robustness DEVICE=cuda` (`src/darijacare/quality/robustness.py`) perturbe
chaque message du test officiel de façon reproductible (graine 42, un générateur par
message), le fait passer par le chemin de production (assainissement, masquage, modèle
servi) et compare le F1 macro d'intention aux prédictions non perturbées. Les taux de
perturbation ont été fixés à l'avance, jamais ajustés sur le test
(`reports/quality/robustness_test.md`).

| Perturbation | Contenu | F1 macro intention | Baisse (points) | Cible ≤ 5 |
|---|---|---|---|---|
| aucune (référence) | — | 0,8948 | — | — |
| fautes | ~15 % des mots (inversion, oubli, doublement, touche voisine, lettre arabe proche), au moins une par message | 0,8103 | **8,45** | non atteinte |
| translittération | chiffres arabizi écrits en lettres (3 → a, 7 → h, 9 → q…), ch/sh, accents, variantes d'alef, ta marbuta, ya | 0,8568 | 3,80 | atteinte |
| caractères exotiques | deux parmi : allongement, tatweel, diacritiques, emojis, ponctuation répétée, majuscules, chiffres arabo-indiens, largeur nulle, pleine chasse | 0,8558 | 3,90 | atteinte |
| brièveté | seulement la première moitié des mots | 0,5770 | **31,78** | non atteinte |
| mixte | une des trois premières, tirée par message | 0,8343 | **6,05** | non atteinte |

Baisse par écriture (points) : l'**arabizi** est la plus fragile (fautes 11,7 ; mixte
12,4 ; translittération 6,5), l'écriture arabe la moins fragile sauf en brièveté (37,2).

**Lecture.** Le modèle tient les variantes d'orthographe « normales » (translittération,
emojis, allongements : moins de 4 points), mais pas les fautes de frappe (8,45 points) :
le jeu synthétique est écrit proprement et la fiche du modèle ne mentionne aucune
augmentation de données. La brièveté n'est pas une perturbation comme les autres :
couper la moitié du message retire souvent l'information (« Bonjour, ma facture de ce »),
la baisse mesure surtout cette perte. Le correctif prévu par le cahier (F-NLU,
« améliorer la robustesse aux variantes d'écriture ») est une augmentation par fautes de
frappe lors du ré-entraînement, à mesurer sur ce même test de perturbation **sans baisse
sur le test officiel**.

**Effet sur la décision** (politique rejouée sur les messages perturbés) :

| Perturbation | Réponses automatiques | dont fiche exacte | Clarification | Erreurs critiques |
|---|---|---|---|---|
| référence | 84,4 % | 90,1 % | 1,3 % | 40/150 |
| fautes | 81,9 % | 83,7 % | 3,1 % | 41/150 |
| caractères exotiques | 79,4 % | 87,4 % | 1,9 % | 30/150 |
| brièveté | 78,9 % | **64,1 %** | 6,5 % | **86/150** |
| mixte | 81,8 % | 84,5 % | 1,9 % | 38/150 |

La clarification ne compense qu'en partie : sur les messages tronqués, le modèle reste
trop confiant et la politique répond encore à 79 % des messages, dont un tiers avec une
mauvaise fiche. C'est une limite de la confiance du modèle hors de sa distribution, à
traiter avec le ré-entraînement (calibration par écriture et sur des messages courts).

## 4. Latence du NLU

`make quality-latency` (`src/darijacare/quality/latency.py`) : 200 messages tirés de la
validation (graine 42), passés par le chemin de production, prédits **un à un** comme
dans l'API (deux passes de laya), après 10 appels d'échauffement. Matériel : portable de
2018, Intel Core i7-8850H (6 cœurs, torch sur 6 threads) et Quadro P2000 Mobile
(Pascal, 4 Go), **sur secteur**. Une série CPU faussée par un passage sur batterie a été
écartée. Rapport : `reports/quality/latency.md`.

| Appareil | Variante | p50 | p95 | p99 | Cible p95 | Statut |
|---|---|---|---|---|---|---|
| CPU | float32 (servi) | 1 748 ms | 2 514 ms | 2 753 ms | 300 ms | **non atteinte** |
| CPU | int8 dynamique (encodeur) | 1 498 ms | 1 991 ms | 2 173 ms | 300 ms | non atteinte, **non retenue** |
| GPU | défaut de laya (autocast fp16) | 321 ms | 356 ms | 370 ms | 50 ms | **non atteinte** |
| GPU | float32 (diagnostic) | 305 ms | 343 ms | 359 ms | 50 ms | non atteinte |

**Essai int8.** La quantification dynamique int8 des couches linéaires de l'encodeur
(mmBERT) gagne 14 % sur la médiane et 21 % sur le p95, mais **les sorties changent** :
sur les 200 messages, l'intention diffère dans 8,5 % des cas, l'urgence dans 13 %,
needs_human dans 1,5 % (écart de probabilité jusqu'à 0,88), et seuls 74 % des messages
gardent les cinq sorties identiques ; l'exactitude d'intention passe de 0,995 à 0,920 sur
cet échantillon. Le cahier demande de vérifier que les sorties restent les mêmes : ce
n'est pas le cas, l'int8 n'est donc **pas adopté**. La tête de laya
(`nn.TransformerEncoderLayer`) reste en float32 : sa vérification interne échoue sur des
couches quantifiées avec torch 2.7.

**Diagnostic GPU.** laya active l'autocast fp16 sur les GPU de génération inférieure à 8,
dont cette carte Pascal. Le désactiver (diagnostic seulement, `--no-amp`) ne gagne que
5 % et donne des sorties identiques (100 % sur les cinq tâches) : la précision n'est pas
la cause de l'écart. Une première mesure GPU, prise juste après 1 h 30 de calcul continu
(carte bridée), donnait 540 ms en médiane : la latence GPU de ce portable varie aussi
avec son état thermique et d'alimentation.

**Pourquoi les cibles ne sont pas atteintes.** Le modèle est utilisé exactement comme
son `predict.py` (`backend='eager'`, sans compilation ni voie rapide) : chaque message
demande deux passages de l'encodeur sur le message suivi des questions et de leurs
options. Sur ce matériel d'entrée de gamme de 2017-2018, cela coûte environ 1,7 s sur
CPU et 0,3 s sur GPU ; la fiche du modèle annonce environ 30 ms « sur un GPU portable »
sans préciser lequel, et nous ne l'avons pas reproduit. La part de chaque étape
(tokenisation, deux passes, Python) n'a pas été profilée. Pistes, à mesurer avec
contrôle des sorties : un GPU récent (ou un T4) pour le service, le regroupement des
messages simultanés en lots, l'export ONNX (non fourni par laya), ou un modèle distillé
plus petit lors du ré-entraînement.

**Première réponse.** Dans la pile Docker, via nginx, la réponse complète arrive en
**1,8 s** en médiane pour un client seul (§5 ; 1,9 s au plus, hors premier message après
un redémarrage, 6,1 s à froid) : la cible de 2 s est tenue tant que les messages ne
s'accumulent pas, mais pas sous charge.

## 5. Charge (Locust)

`tests/load/locustfile.py` : chaque client simulé ouvre une session puis envoie les
phrases d'exemple de l'interface (trois écritures), avec une pause entre deux messages,
à travers le frontal HTTPS. Tous les clients simulés partageant une même adresse, les
scénarios de capacité relâchent les limites par adresse le temps du test
(`deploy/load/`) ; le scénario d'abus garde les limites normales. Mesures sur secteur,
pile Docker (NLU sur CPU). Rapport : `reports/quality/load.md`.

| Scénario | Clients | Pause | Messages | Échecs | Débit servi | p50 | p95 |
|---|---|---|---|---|---|---|---|
| base | 1 | 5–15 s | 10 | 0 | — | **1,8 s** | 6,1 s (1er message, à froid) |
| réaliste | 20 | 20–40 s | 99 | 0 | 0,42 msg/s | 16 s | 30 s |
| soutenu | 20 | 5–15 s | 72 | 0 | 0,40 msg/s | 35 s | 42 s |
| abus (limites normales) | 20 | 0,5–1,5 s | 1 015 | 1 000 refusés (429) | — | 6 ms | — |

**Lecture.** Le débit plafonne à **0,4–0,5 message par seconde** : l'API traite un appel
au modèle à la fois, et un message coûte environ 2 s de CPU (NLU et recherche). Avec 20
clients qui écrivent toutes les 20 à 40 s (environ 0,67 message/s demandé), la file
s'allonge et l'attente médiane atteint 16 s. La cible « 20 requêtes simultanées sans
dégradation notable » **n'est pas atteinte** sur ce CPU. Le service reste correct sous
charge : aucune erreur, aucun dépassement de délai, aucune 5xx ; seule la latence se
dégrade. Sous abus, les limites rejettent 98,5 % des messages en quelques
millisecondes (429), sans 5xx, et refusent aussi 5 ouvertures de session sur 20.

**Pistes**, à mesurer : servir le NLU sur GPU (0,3 s par message sur la P2000, beaucoup
moins sur une carte récente), regrouper les messages simultanés en lots, plusieurs
processus si la mémoire le permet, et afficher au client sa position dans la file.

## 6. Tests

| Niveau | Outil | Contenu | Résultat |
|---|---|---|---|
| Unitaires et API | pytest | normalisation, scripts, décision, priorité, gabarits, RAG, API (SQLite, NLU factice), sécurité, évaluations de la Phase 6, registre, jeu gold | 285 réussis (dont 3 d'intégration) |
| Données | pytest + Pandera | schéma, libellés, proximité des découpages | inclus |
| Intégration | Testcontainers 4.15 | PostgreSQL 16.4 et Qdrant 1.20.0 jetables : migrations, indexation idempotente, parcours client → escalade → conseiller | 3/3 |
| Fonctionnels | Playwright 1.64 | chat (exemple, flux, sources, analyse, « Utile », fiche), trois écritures, script refusé sans exécution, transfert ; console (prise en charge, clôture) ; tableau de bord | 4/4 sur la pile HTTPS |
| Interface | Vitest | composants et pages | 20/20 |
| Sécurité | pytest + pile | 50 attaques, entrées atypiques, isolation, rafale | voir [securite.md](securite.md) |
| Résilience | Docker | arrêt brutal du processus du backend | redémarrage automatique, API de retour en 70 s, interface toujours servie |

Couverture : 80 % (cible 70 %), vérifiée en CI (`--cov-fail-under=70`). Les deux tests
ignorés visent le PostgreSQL de `docker-compose` (`make dev-up`) ; Testcontainers couvre
désormais ce besoin sans serveur préalable.

Commandes : `make test`, `make integration`, `make e2e` (pile lancée), `make front-test`.

## 7. Registre de modèles et non-régression (F-OPS-01)

`python -m darijacare.nlu.registry` (MLflow 3.18, base `mlflow.db` ou `MLFLOW_TRACKING_URI`) :

- **register** : crée une version du modèle `darijacare-nlu` à partir du run
  d'évaluation `eval_<modèle>_test` ; étiquettes : révision du Hub, SHA-256 des poids,
  empreintes des données (`dvc.lock`), métriques. v5 = version 1, v3 = version 2.
- **promote** : déplace l'alias `champion` seulement si aucune métrique gardée (F1 macro
  intention, catégorie, produit, needs_human ; exactitude de bout en bout) ne baisse de
  plus d'**1 point** face au champion actuel, sauf justification écrite (enregistrée sur
  la version et dans `reports/nlu/registry.json`).
- **compare** : test de non-régression entre deux modèles évalués.

État : **v5 est champion** (run `caef31eb…`). Démonstration du garde-fou : la promotion
de v3 est refusée (F1 macro intention −4,91 points, bout en bout −5,06, catégorie −3,44).
L'API enregistre le run du modèle servi dans `modele_nlu.mlflow_run` et le renvoie dans
`GET /models` : tout modèle déployé est relié à un run et à une version des données.

## 8. Jeu gold

Outillage prêt (format, contrôles, kappa de Cohen, évaluation finale) ; les 300 messages
restent à écrire par l'équipe : [gold.md](gold.md).

---

Données : Mohamed Ballouch (2026), *Jev-Darija Telecom: Moroccan Darija Customer-Service
Messages*, https://huggingface.co/datasets/mballouch/jev-darija-telecom, licence
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Modifications apportées
(dédoublonnage, normalisation, découpage) et modèle utilisé : [CREDITS.md](../CREDITS.md).
