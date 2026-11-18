# Base de connaissances et RAG (Phase 3)

Références du cahier des charges : F-KB-01 à F-KB-04, §13, Tableau 21. Configuration :
[configs/rag.yaml](../configs/rag.yaml). Code : `src/darijacare/rag/`. Résultats mesurés sur des
données **synthétiques** ; les fiches sont **fictives**.

## 1. Les 75 fiches (`kb/`)

- Une fiche par intention de la taxonomie : `kb/<catégorie>/<intention>.md`.
- Front matter : `id`, `intent`, `category`, `version`, `status: fictif`, `langs`, `reviewed_by`.
- Avertissement « fiche fictive » en tête de chaque partie ; aucune donnée réelle (ni prix, ni
  numéro, ni nom d'opérateur, ni engagement).
- Deux parties : français et darija en écriture arabe ; cinq sections chacune : **Objet, Étapes,
  Conditions, Limites, Escalade** (الهدف، الخطوات، الشروط، الحدود، التحويل لمستشار).
- 150 à 258 mots par fiche (FR + AR ; cible 150–300).
- Validation automatique (`make kb-validate`) : une fiche par intention et aucune en trop,
  catégorie conforme, statut fictif, sections non vides dans les deux langues, longueur, aucun
  numéro de téléphone.

**Relecture.** Le contenu initial a été rédigé dans `kb/_source/*.yaml` puis rendu en Markdown.
**Les fichiers Markdown font foi** : relisez et corrigez-les directement, puis ajoutez votre nom
dans `reviewed_by` et incrémentez `version` si le fond change. `generate-kb` ne réécrit jamais une
fiche existante sans `--force`. Le darija écrit par l'assistant **doit être relu par des
locuteurs natifs** (critère F-KB-01 : 75 fiches relues par deux membres).

## 2. Index (`index.py`)

| Élément | Choix |
|---|---|
| Découpage | une section = un passage, préfixé par le titre de la fiche ; 75 × 2 langues × 5 sections = **750 passages** (375 par langue, soit 5 par fiche comme prévu au Tableau 21) |
| Embeddings | BGE-M3 (`BAAI/bge-m3` @ `5617a9f6`, MIT) via `FlagEmbedding` : vecteur dense 1024 + poids lexicaux creux |
| Base | Qdrant, vecteurs nommés `dense` (cosinus) et `sparse`, payload `fiche_id, intent, category, lang, section, version, status, text` |
| Idempotence | identifiants UUID5 de `intention/langue/section` ; une ré-indexation remplace les points et supprime ceux qui n'existent plus (testé) |
| Déploiement | `QDRANT_URL` (serveur docker-compose) ou mode local embarqué `data/qdrant` (sans Docker) |

Indexation complète : 2 min 30 sur CPU.

**Serveur et mode local donnent les mêmes résultats.** Le serveur docker-compose (Qdrant 1.20.0,
même version mineure que `qdrant-client`) a été comparé au mode local sur les 1 107 requêtes du
test, pour 4 réglages de recherche :
- aucun classement ni aucun drapeau « fiable » ne diffère ;
- l'écart de score dense est au plus 2·10⁻⁷ ;
- en mode production, une recherche prend 34 ms en médiane sur le serveur, contre 42 ms en local.

Le mode local n'accepte qu'un processus à la fois : l'API (Phase 4) utilise donc le serveur.

## 3. Recherche (`retrieve.py`)

1. **Filtre d'intention** : intention prédite + ses 3 voisines les plus confondues.
   Les voisines viennent des erreurs de la v3 sur les rondes 4 et 6 de la validation, jamais vues
   par la v3 ; le test officiel n'est pas utilisé, il reste disponible pour l'évaluation.
2. Recherche **dense** et **creuse** (10 passages chacune) dans les fiches autorisées.
3. Fusion **RRF** (k = 60) au niveau des passages ; une fiche prend le score de son meilleur passage.
4. **Priorité NLU** (`nlu_prior`) : `first` = la fiche de l'intention prédite passe en tête et la
   recherche ordonne les alternatives ; `rrf` = classement NLU ajouté comme 3ᵉ liste RRF ;
   `none` = classement de la recherche seul.
5. 3 fiches renvoyées ; « fiable » si la similarité dense de la fiche retenue atteint le seuil.

### Choix du mode de priorité, sur des données propres

La v5 a été entraînée sur notre validation (98,8 % d'exactitude dessus) : elle ne peut pas servir à
choisir. Le choix a été fait avec la **v3 sur les rondes 4 et 6 de la validation** (2 243 messages
jamais vus, exactitude NLU ≈ 79 %) :

| Mode (filtre sur l'intention prédite par v3) | Recall@1 | Recall@3 | MRR |
|---|---|---|---|
| Classement de la recherche seul (`none`) | 0,550 | 0,775 | 0,650 |
| Priorité NLU par RRF (`rrf`) | 0,613 | 0,787 | 0,691 |
| **Fiche prédite en tête (`first`)** | **0,787** | **0,815** | **0,800** |
| NLU seul, sans recherche | 0,787 | 0,816 | 0,800 |

`first` l'emporte nettement (+17 points de Recall@1 sur `rrf`) : **retenu**.

**Leçon.** Avec une fiche par intention, choisir la fiche revient à classer l'intention, et le
classifieur spécialisé le fait bien mieux que la recherche sémantique (les messages clients
ressemblent peu au texte procédural des fiches). La recherche garde trois rôles : vérifier que la
fiche est étayée par le message (score dense), ordonner les fiches alternatives affichées comme
sources, et préparer une base plus riche (plusieurs fiches ou versions par intention), où elle
deviendra indispensable.

## 4. Résultats sur le test officiel (1 107 requêtes, intention prédite par la v5)

Requête = message ; fiche attendue = fiche de l'intention annotée. Mesure unique, après le choix
du mode.

| Réglage | Recall@1 | **Recall@3** | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0,285 | 0,451 | 0,355 | 0,458 | 0,253 | 0,694 |
| Filtre prédit, classement recherche | 0,611 | 0,868 | 0,728 | 0,875 | 0,826 | 0,905 |
| Filtre prédit + RRF | 0,708 | 0,892 | 0,791 | 0,890 | 0,874 | 0,919 |
| **Filtre prédit + fiche prédite en tête (production)** | **0,896** | **0,916** | **0,905** | **0,919** | **0,904** | **0,923** |
| Filtre sur la vraie intention, classement recherche (borne) | 0,660 | 0,945 | 0,789 | 0,948 | 0,911 | 0,982 |

- **Cible Recall@3 ≥ 0,90 atteinte** (0,916), et pour chaque script.
- **Hypothèse H4 confirmée** : le filtre d'intention apporte **+46,5 points** de Recall@3.
- Sans filtre, l'arabizi est le plus difficile (R@3 0,253) : BGE-M3 rapproche mal l'arabizi du
  texte des fiches.

## 5. Seuil de fiabilité

La fiche retenue est jugée « fiable » si sa meilleure similarité dense avec le message atteint
`min_dense_score` ; sinon la réponse est prudente (« pas d'information fiable », proposition de
conseiller). Seuil choisi sur la validation propre (v3, rondes 4 et 6) :

| Seuil | Messages non fiables | Exactitude si fiable | Exactitude si non fiable |
|---|---|---|---|
| 0,25 | 0,2 % | 0,787 | 0,500 |
| **0,30 (retenu)** | **1,3 %** | **0,789** | **0,667** |
| 0,35 | 5,3 % | 0,790 | 0,733 |
| 0,40 | 15,2 % | 0,806 | 0,682 |

Le score dense est un **signal faible** (AUC 0,62 pour prédire si la fiche est la bonne) : c'est un
**plancher de sécurité**, pas un filtre de qualité. À 0,30, il écarte les 1,3 % de messages les
moins étayés (justes à 67 % seulement) ; au-delà, il détournerait trop de bonnes réponses.
La vraie garde contre les erreurs reste la règle 5 (confiance NLU basse → clarification).

Correctif trouvé pendant cette analyse : quand la fiche prédite n'était retrouvée que par la voie
creuse, son score dense n'était pas calculé (valeur -1, ~3 % des messages faussement « non
fiables ») ; il est désormais mesuré par une requête dense ciblée (test unitaire dédié).

Mesure au test (sans réglage) : 99,0 % des réponses jugées fiables ; les 11 messages écartés
(1,0 %) étaient en fait tous corrects. Sur cet échantillon, le plancher coûte donc 1 % de réponses
qui auraient été justes, alors qu'il écartait des réponses justes à 67 % sur la validation propre.
Les effectifs sont faibles ; le seuil sera revu sur la validation propre du modèle ré-entraîné et
sur le jeu gold (Phase 6).

## 6. Réponses par gabarits (`respond.py`, `templates/`)

- Un gabarit Jinja2 par action et par script : `answer`, `clarify`, `escalate`, `out_of_scope`,
  `refuse`, `greeting`, `no_source` × `arabic` / `arabizi` / `mixed` ; surcharge possible par
  intention (`templates/<script>/intents/<intention>.j2`).
- **Contenu** : le titre de la fiche (ouverture tournée vers le client) et ses étapes ; le gabarit
  n'ajoute que salutations, mots de liaison et la proposition d'un conseiller (une capacité de
  l'assistant, pas une affirmation sur la procédure). Chaque réponse cite la fiche et sa version.
  Les sections « Objet » et « Escalade » sont rédigées en style procédure interne (« Aider le
  client… ») : elles servent à la recherche et aux conseillers, pas au texte envoyé au client.
- **Script** : écriture arabe → partie darija de la fiche ; mixte → partie française avec
  formules darija ; arabizi → formules en arabizi autour des étapes en français (les fiches n'ont
  pas de version arabizi et une translittération automatique ne serait pas fiable).
- Clarification : propose les **titres** des deux fiches les plus probables.
- Escalade d'une intention de sécurité : inclut les étapes de protection de la fiche.

## 7. Reproduire

```bash
make kb-validate     # 0 problème attendu
make rag-index       # ~2 min 30 sur CPU ; QDRANT_URL pour le serveur docker-compose
python -m darijacare.rag.cli neighbours                       # voisines (v3, rondes 4 et 6)
python -m darijacare.rag.cli evaluate --split val --nlu-model v3 --rounds 4 6   # choix propre
python -m darijacare.rag.cli evaluate --split test            # mesure finale
python -m darijacare.rag.cli search "ma kaynach connexion f dar" --intent home_outage
```
