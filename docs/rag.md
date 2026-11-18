# Base de connaissances et RAG (Phase 3)

Références du cahier des charges : F-KB-01 à F-KB-04, §13, Tableau 21. Configuration :
[configs/rag.yaml](../configs/rag.yaml). Code : `src/darijacare/rag/`. Résultats mesurés sur des
données **synthétiques** ; les fiches sont **fictives**.

## 1. Les 75 fiches (`kb/`)

- Une fiche par intention de la taxonomie : `kb/<catégorie>/<intention>.md`.
- Front matter : `id`, `intent`, `category`, `version`, `status: fictif`, `langs`, `reviewed_by`.
- Avertissement « fiche fictive » en tête de chaque partie ; aucune donnée réelle (ni prix, ni
  numéro, ni nom d'opérateur, ni engagement).
- Trois parties, avec cinq sections chacune : **Objet, Étapes, Conditions, Limites, Escalade**.

  | Partie | Statut | Titres des sections |
  |---|---|---|
  | Français | exigée par le cahier | Objet, Étapes, Conditions, Limites, Escalade |
  | Darija en écriture arabe | exigée par le cahier | الهدف، الخطوات، الشروط، الحدود، التحويل لمستشار |
  | Darija en arabizi | ajoutée | Lhadaf, Lkhatawat, Chorout, L7oudoud, Ta7wil l conseiller |

- **Partie arabizi.** C'est le même contenu que la partie en écriture arabe, écrit à la main (pas de
  translittération automatique). L'orthographe suit celle des 8 644 messages arabizi du jeu
  d'entraînement :
  - `9` pour ق (5 038 occurrences contre 618 pour `q`) ;
  - `dyal`, `wach`, `ch`, `khass`, `3afak` ;
  - l'article collé au mot (`lfatoura`, `lkhat`) ;
  - des mots français sans accents (`reseau`, `forfait`, `solde`).

  Elle permet de répondre aux clients arabizi dans leur écriture (voir §6).
- 150 à 258 mots par fiche pour le français et l'arabe (cible du cahier : 150–300). La partie
  arabizi compte de 1,09 à 1,32 fois les mots de la partie arabe, car `فالدار` devient `f dar`.
- Validation automatique (`make kb-validate`) :
  - une fiche par intention et aucune en trop, catégorie conforme, statut fictif ;
  - sections non vides dans les trois parties, longueur, aucun numéro de téléphone ;
  - la partie arabizi reflète la partie arabe : même nombre d'étapes, de conditions et de limites,
    rapport de longueur entre 0,8 et 1,6, aucune lettre arabe.

**Relecture.** Le contenu initial a été rédigé dans `kb/_source/*.yaml` puis rendu en Markdown.
**Les fichiers Markdown font foi** : relisez et corrigez-les directement, puis ajoutez votre nom
dans `reviewed_by` et incrémentez `version` si le fond change. `generate-kb` ne réécrit jamais une
fiche existante sans `--force`. Le darija écrit par l'assistant, en écriture arabe comme en
arabizi, **doit être relu par des locuteurs natifs** (critère F-KB-01 : 75 fiches relues par deux
membres). Aucune relecture n'a encore eu lieu : `reviewed_by` est vide partout.

## 2. Index (`index.py`)

| Élément | Choix |
|---|---|
| Découpage | une section = un passage, préfixé par le titre de la fiche ; 75 fiches × 3 parties × 5 sections = **1 125 passages**, soit 5 par fiche et par partie (le Tableau 21 prévoit 3 à 5 passages par fiche ; ses « ≈ 300 au total » supposaient une seule langue) |
| Embeddings | BGE-M3 (`BAAI/bge-m3` @ `5617a9f6`, MIT) via `FlagEmbedding` : vecteur dense 1024 + poids lexicaux creux |
| Base | Qdrant, vecteurs nommés `dense` (cosinus) et `sparse`, payload `fiche_id, intent, category, lang, section, version, status, text` |
| Idempotence | identifiants UUID5 de `intention/langue/section` ; une ré-indexation remplace les points et supprime ceux qui n'existent plus (testé) |
| Déploiement | `QDRANT_URL` (serveur docker-compose) ou mode local embarqué `data/qdrant` (sans Docker) |

Indexation complète : 3 min 40 sur CPU.

**Serveur et mode local donnent les mêmes résultats.** Le serveur docker-compose (Qdrant 1.20.0,
même version mineure que `qdrant-client`) a été comparé au mode local sur les 1 107 requêtes du
test, pour 4 réglages de recherche (index final de 1 125 passages) :
- aucun classement ni aucun drapeau « fiable » ne diffère ;
- l'écart de score dense est au plus 1,9·10⁻⁷ ;
- en mode production, une recherche prend 8,8 ms en médiane sur le serveur (p95 12,7 ms),
  contre 61,4 ms en local (p95 85,9 ms).

Le mode local n'accepte qu'un processus à la fois : l'API (Phase 4) utilise donc le serveur.

**Connexions au serveur.** Pour un serveur sur `localhost` ou `127.0.0.1`, `qdrant-client`
désactive la réutilisation des connexions HTTP (`max_keepalive_connections=0` dans
`QdrantRemote`). Chaque requête ouvre donc une connexion TCP, et Windows la garde ensuite
quelques minutes avant de libérer son port.

Conséquence : une évaluation complète (environ 40 000 requêtes) épuisait les ports de la
machine et s'arrêtait avec l'erreur `WinError 10048`. `get_client` réactive la réutilisation des
connexions (test unitaire dédié). Mesure sur 300 recherches en mode production :

| Client | Recherche (médiane) | Connexions laissées ouvertes |
|---|---|---|
| Par défaut | 30,4 ms | 611 |
| Avec réutilisation des connexions | 8,5 ms | 2 |

L'évaluation complète passe alors en 4 minutes.

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
| Classement de la recherche seul (`none`) | 0,539 | 0,772 | 0,644 |
| Priorité NLU par RRF (`rrf`) | 0,600 | 0,790 | 0,686 |
| **Fiche prédite en tête (`first`)** | **0,787** | **0,814** | **0,799** |
| NLU seul, sans recherche | 0,787 | 0,816 | 0,800 |

`first` l'emporte nettement (+19 points de Recall@1 sur `rrf`) : **retenu**. Le choix avait été
fait sur l'index de 750 passages, avec le même écart (`first` 0,787, `rrf` 0,613, `none` 0,550) ;
le tableau donne les chiffres de l'index final.

### Indexer aussi la partie arabizi ? Décision prise sur la validation propre

Même validation propre (v3, rondes 4 et 6, 2 243 messages) :

| Mesure | Index FR + AR (750 passages) | Index FR + AR + arabizi (1 125 passages) |
|---|---|---|
| Production : Recall@1 / Recall@3 / MRR | 0,787 / 0,815 / 0,800 | 0,787 / 0,814 / 0,799 |
| Production, messages arabizi : Recall@3 | 0,779 | 0,773 |
| Sans filtre, messages arabizi : Recall@3 | 0,266 | **0,356** |
| Score dense médian de la fiche retenue, messages arabizi | 0,43 | **0,55** |
| Messages arabizi jugés « non fiables » (seuil 0,30) | 2,8 % | **0 %** |

La partie arabizi est **indexée** :
- le classement de production ne change pas (moins de 0,1 point, et 3 messages arabizi sur 503) ;
- les clients arabizi ne sont plus écartés à tort comme « non fiables » ;
- la recherche sans filtre progresse de 9 points sur l'arabizi.

**Leçon.** Avec une fiche par intention, choisir la fiche revient à classer l'intention, et le
classifieur spécialisé le fait bien mieux que la recherche sémantique (les messages clients
ressemblent peu au texte procédural des fiches). La recherche garde trois rôles : vérifier que la
fiche est étayée par le message (score dense), ordonner les fiches alternatives affichées comme
sources, et préparer une base plus riche (plusieurs fiches ou versions par intention), où elle
deviendra indispensable.

## 4. Résultats sur le test officiel (1 107 requêtes, intention prédite par la v5)

Requête = message ; fiche attendue = fiche de l'intention annotée. Les choix (mode, index
arabizi, seuil) sont faits sur la validation ; le test n'est que mesuré, une fois avec l'index de
750 passages puis une fois avec l'index final, sans aucun réglage.

| Réglage (index final, 1 125 passages) | Recall@1 | **Recall@3** | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |
|---|---|---|---|---|---|---|
| Sans filtre (75 fiches) | 0,275 | 0,458 | 0,355 | 0,444 | 0,396 | 0,577 |
| Filtre prédit, classement recherche | 0,598 | 0,870 | 0,721 | 0,872 | 0,846 | 0,896 |
| Filtre prédit + RRF | 0,661 | 0,879 | 0,761 | 0,887 | 0,850 | 0,896 |
| **Filtre prédit + fiche prédite en tête (production)** | **0,896** | **0,916** | **0,905** | **0,917** | **0,904** | **0,928** |
| Filtre sur la vraie intention, classement recherche (borne) | 0,642 | 0,944 | 0,779 | 0,948 | 0,918 | 0,968 |

- **Cibles atteintes** : Recall@3 0,916 ≥ 0,90 (et pour chaque script), MRR 0,905 ≥ 0,85.
- **Hypothèse H4 confirmée** : le filtre d'intention apporte **+45,8 points** de Recall@3.
- La production est inchangée par rapport à l'index de 750 passages (0,896 / 0,916 / 0,905).
- **Sans filtre**, l'index arabizi fait passer l'arabizi de 0,253 à 0,396. En contrepartie, les
  messages mixtes descendent de 0,694 à 0,577 : ils tombent parfois sur la partie arabizi d'une
  autre fiche. Ce réglage n'est pas celui de production, où le filtre d'intention l'emporte.

## 5. Seuil de fiabilité

La fiche retenue est jugée « fiable » si sa meilleure similarité dense avec le message atteint
`min_dense_score` ; sinon la réponse est prudente (« pas d'information fiable », proposition de
conseiller). Seuil choisi sur la validation propre (v3, rondes 4 et 6) :

| Seuil | Index 750 : non fiables | Index 750 : exact. si fiable / non fiable | **Index final : non fiables** | **Index final : exact. si fiable / non fiable** |
|---|---|---|---|---|
| 0,25 | 0,2 % | 0,787 / 0,500 | 0,1 % | 0,787 / 0,500 |
| **0,30 (retenu)** | 1,3 % | 0,789 / 0,667 | **0,3 %** | **0,787 / 0,857** |
| 0,35 | 5,3 % | 0,790 / 0,733 | 1,6 % | 0,787 / 0,771 |
| 0,40 | 15,2 % | 0,806 / 0,682 | 5,4 % | 0,791 / 0,711 |

Le score dense est un **signal faible** (AUC 0,61 pour prédire si la fiche est la bonne) : c'est un
**plancher de sécurité**, pas un filtre de qualité.

Le seuil de 0,30 a été choisi sur l'index de 750 passages, où il écartait les 1,3 % de messages
les moins étayés (justes à 67 % seulement). Avec l'index final, les scores sont plus hauts (surtout
en arabizi), et le seuil de 0,30 n'écarte plus que 0,3 % des messages. Il est **conservé** :
- à 0,35, il écarterait 1,6 % de réponses presque aussi justes que les autres (0,771 contre 0,787) ;
- à 0,40, 5,4 %, pour un gain d'exactitude minime.

La vraie garde contre les erreurs reste la règle 5 (confiance NLU basse → clarification).

Correctif trouvé pendant cette analyse : quand la fiche prédite n'était retrouvée que par la voie
creuse, son score dense n'était pas calculé (valeur -1, ~3 % des messages faussement « non
fiables ») ; il est désormais mesuré par une requête dense ciblée (test unitaire dédié).

Mesure au test (sans réglage) avec l'index final : 99,3 % des réponses sont jugées fiables. Les 8
messages écartés (0,7 %) étaient en fait tous corrects, tous en écriture arabe ; avec l'index de
750 passages, c'étaient 11 messages (1,0 %), eux aussi tous corrects. Sur cet échantillon, le
plancher coûte donc 0,7 % de réponses qui auraient été justes. Les effectifs sont faibles : le
seuil sera revu sur la validation propre du modèle ré-entraîné et sur le jeu gold (Phase 6).

## 6. Réponses par gabarits (`respond.py`, `templates/`)

- Un gabarit Jinja2 par action et par script : `answer`, `clarify`, `escalate`, `out_of_scope`,
  `refuse`, `greeting`, `no_source` × `arabic` / `arabizi` / `mixed` ; surcharge possible par
  intention (`templates/<script>/intents/<intention>.j2`).
- **Contenu** : le titre de la fiche (ouverture tournée vers le client) et ses étapes ; le gabarit
  n'ajoute que salutations, mots de liaison et la proposition d'un conseiller (une capacité de
  l'assistant, pas une affirmation sur la procédure). Chaque réponse cite la fiche et sa version.
  Les sections « Objet » et « Escalade » sont rédigées en style procédure interne (« Aider le
  client… ») : elles servent à la recherche et aux conseillers, pas au texte envoyé au client.
- **Écriture du client** : la réponse utilise la partie de la fiche écrite comme le client.

  | Le client écrit en… | La réponse reprend… |
  |---|---|
  | écriture arabe | la partie darija en écriture arabe |
  | arabizi | la partie darija en arabizi (le titre et les étapes) |
  | mixte | la partie française, avec des formules en darija |

  Avant l'ajout de la partie arabizi, un client arabizi recevait les étapes en français.
- Clarification : propose les **titres** des deux fiches les plus probables.
- Escalade d'une intention de sécurité : inclut les étapes de protection de la fiche.

## 7. Reproduire

```bash
make kb-validate     # 0 problème attendu
make rag-index       # ~3 min 40 sur CPU ; QDRANT_URL pour le serveur docker-compose
python -m darijacare.rag.cli neighbours                       # voisines (v3, rondes 4 et 6)
python -m darijacare.rag.cli evaluate --split val --nlu-model v3 --rounds 4 6   # choix propre
python -m darijacare.rag.cli evaluate --split test            # mesure finale
python -m darijacare.rag.cli search "ma kaynach connexion f dar" --intent home_outage
```
