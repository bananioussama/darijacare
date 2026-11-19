# Interface (Phase 5)

Références du cahier des charges :
- exigences : F-UI-01 à F-UI-08 ;
- tableaux : 29 (pages), 30 (palette), 31 (identité visuelle) ;
- figures : 12 (maquette du chat), 13 (maquette du tableau de bord) ;
- § 16.3 (comportements d'interaction).

Code : `frontend/`, avec React 19, TypeScript strict, Vite, Tailwind CSS 4, React Router 7 et
Recharts. L'interface est en français ; les échanges se font en arabe, en arabizi ou en darija
mêlée de français.

## 1. Lancer

```bash
docker compose up -d postgres qdrant && make db-upgrade && make api   # API sur le port 8000
make front-install        # npm ci : versions figées par package-lock.json
make front-dev            # http://127.0.0.1:5173 ; /api est relayé vers l'API
make front-test           # types, formatage (Prettier) et tests (Vitest)
```

Sous Windows : `.\tasks.ps1 front-install`, `.\tasks.ps1 front-dev`, etc.

En développement, le serveur Vite relaie `/api` vers l'API : le navigateur ne parle qu'à une seule
origine. En production (Phase 6), nginx servira `frontend/dist` et relaiera `/api`.

## 2. Pages (Tableau 29)

| Page | Adresse | Accès | Contenu |
|---|---|---|---|
| Assistant | `/` | tous | chat, panneau d'analyse NLU, sources, retours, conseiller (§3) |
| Historique de session | `/historique` | tous | sessions de ce navigateur, fil de chacune, reprise, réinitialisation (F-UI-05) |
| Console conseiller | `/console` | conseiller, admin (lecture seule) | file triée par priorité, dossier complet, prise en charge, clôture avec correction (F-UI-06) |
| Tableau de bord | `/tableau-de-bord` | ml, admin ; conseiller : file seulement | 4 indicateurs (messages, F1 macro du test, taux d'escalade, latence p95), répartitions, décisions, retours, file (F-UI-07) |
| Base et modèles | `/administration` | ml, admin | 75 fiches (recherche, consultation), modèles et évaluations, configuration de décision (lecture), comptes (admin) : demandes d'inscription en attente (valider avec un rôle, ou refuser), liste et création des comptes |
| Connexion | `/connexion` | personnel | jeton de 15 minutes, déconnexion automatique à l'expiration ; bouton « S'inscrire » (F-UI-08) |
| Inscription | `/inscription` | visiteurs | demande de compte du personnel (identifiant, mot de passe de 12 caractères au moins, confirmation, rôle demandé) ; le compte attend la validation d'un administrateur |
| Crédits | `/credits` | tous | attribution CC BY 4.0 du jeu de données et licences des modèles |

Les droits réels sont vérifiés par l'API à chaque requête (Tableau 14). Côté interface, les pages
non autorisées sont simplement masquées ou redirigées vers la connexion.

## 3. Chat (F-UI-01 à F-UI-04, Figure 12)

- **Saisie** :
  - multiligne, avec `dir="auto"` : le texte s'aligne à droite en arabe, à gauche en arabizi et
    en français ;
  - de 4 à 500 caractères ;
  - Entrée envoie, Maj+Entrée va à la ligne.
- **Exemples cliquables** dans les trois écritures.
- **Flux SSE** :
  - la réponse s'affiche au fil de l'eau ;
  - états explicites : en cours, terminé, erreur (avec un message en français) ;
  - badges : hors périmètre, confiance faible avec précision demandée, transmis à un conseiller
    avec le numéro de dossier.
- **Sous chaque réponse** :
  - la mention « Réponse automatique » ;
  - le badge de confiance, en toutes lettres et en pourcentage ;
  - l'encart **Sources** (identifiant, version et titre de la fiche), consultable dans une
    fenêtre ;
  - les boutons **Utile** / **Corriger**. La correction ouvre la liste des 75 intentions, groupées
    par catégorie, avec un commentaire facultatif masqué par l'API.
- **Panneau d'analyse NLU** :
  - il montre l'écriture, la catégorie, l'intention, les deux intentions les plus probables, le
    produit, l'urgence, le besoin d'un conseiller, la confiance de chaque tâche, la règle de
    décision et la priorité ;
  - il se masque, et il l'est par défaut sur mobile.
- **Parler à un conseiller** : le bouton envoie la demande dans l'écriture du client, avec
  `request_human` ; la règle 2 l'escalade toujours (voir [decision.md](decision.md)).
- **Sessions** :
  - le jeton de session (24 h) est gardé dans le navigateur ;
  - la conversation reprend après un rechargement ;
  - une session close ou expirée est remplacée au message suivant.

## 4. Identité visuelle et accessibilité

| Point | Choix |
|---|---|
| Palette (Tableau 30) | violet nuit (barre latérale), violet profond (titres, bouton principal), violet vif (éléments interactifs, focus), lavande, gris clair, texte `#1E1530`. Les couleurs d'inwi sont une inspiration ; **pas de logo**. |
| Contrastes (WCAG 2.2 AA, calculés) | texte sur fond : 13,4 à 17,7:1 ; blanc sur violet vif : 7,1:1 ; texte secondaire : 6,8:1 ; pastilles d'état : 6,9 à 8,1:1. Le violet lumineux (2,9:1 sur blanc) ne sert que sur fond sombre (6,1:1). |
| Polices | Inter et Noto Sans Arabic, hébergées localement (paquets `@fontsource`, aucun appel externe) |
| Composants | cartes arrondies à 16 px, boutons à 12 px, cibles tactiles d'au moins 44 px, focus visible |
| Mise en page | mobile d'abord ; points de rupture à 640, 1024 et 1280 px ; chat plein écran et menu repliable sur mobile |
| Accessibilité | lien d'évitement, étiquettes et rôles ARIA, zone `aria-live` pour la réponse, fenêtre de fiche fermée par Échap avec gestion du focus, « mouvement réduit » respecté |
| États | jamais signalés par la seule couleur : chaque pastille porte son libellé |
| Graphiques | une seule teinte par graphique (une série), barres fines aux extrémités arrondies, infobulle, tableau « Voir les données » sous chaque graphique |

## 5. Sécurité côté interface

- **Réponses affichées comme du texte** : React échappe le contenu, et aucun HTML n'est
  interprété. Un test vérifie qu'une réponse contenant `<img onerror>` reste du texte.
- **Jeton du personnel** (15 min) :
  - gardé dans `sessionStorage`, il disparaît à la fermeture de l'onglet ;
  - une réponse 401 déconnecte ;
  - la déconnexion est automatique à l'expiration.
- **Jetons de session client** : gardés dans `localStorage`, ils n'ouvrent que leur propre
  conversation. Si le stockage est indisponible (navigation privée), l'interface fonctionne sans
  persistance.
- **Dépendances** :
  - versions publiées depuis au moins 14 jours, installées avec `npm install --before`, et figées
    dans `package-lock.json` ;
  - les dépendances livrées au navigateur n'ont **aucune vulnérabilité connue** (`npm audit
    --omit=dev`, contrôlé en CI).
  - Un avis sur `picomatch` (ReDoS, GHSA-fc5q-39xc-vjpf) touche seulement les outils de
    développement (Vite, Vitest). Aucune version corrigée n'existe en novembre 2026, et aucune
    donnée d'utilisateur n'atteint ces outils. À revoir en Phase 6.

## 6. Performances

- **Pages chargées à la demande** : le chat (300 Ko de JavaScript, 95 Ko compressés)
  n'embarque ni Recharts ni la console. Le tableau de bord se charge seulement pour le personnel.
- **Réponse avec les vrais modèles, sur CPU** : médiane 1,8 s, p95 1,9 s, mesurées en Phase 4.

## 7. Tests et vérification

- **Vitest et Testing Library** (`npm test`), avec un faux `fetch` dont le flux SSE est découpé en
  morceaux de 7 octets (qui coupent aussi les caractères arabes). Les tests couvrent :
  - l'analyseur SSE (découpages arbitraires, CRLF, données sur plusieurs lignes) ;
  - le chat : flux, sources, badges, panneau, jeton de session, bouton conseiller, réponse hostile
    affichée comme du texte, panneau masquable, erreurs, longueur minimale, exemples ;
  - les retours « Utile » et « Corriger » ;
  - la console (prise en charge, lecture seule de l'admin) ;
  - les gardes de rôles, la connexion et la déconnexion sur 401 ;
  - les crédits et le stockage des sessions.
- **Vérification visuelle** avec les vrais modèles : `npm run captures` (`scripts/captures.mjs`,
  Playwright avec Chromium sans interface), qui produit les captures de
  [reports/demo/phase5/](../reports/demo/phase5/).
  - Il demande l'API et l'interface lancées, et les comptes `conseiller1` et `admin1` ; le mot de
    passe se passe par la variable `DARIJACARE_CAPTURE_PASSWORD`.
  - Cette vérification a corrigé un défaut : la zone de saisie, collée en bas de l'écran, masquait
    la fin du dernier message après le défilement automatique.
- **Audit d'accessibilité automatique** : `npm run audit:a11y` (`scripts/audit-a11y.mjs`) exécute
  axe-core sur le rendu réel de 13 vues. Ces vues couvrent le chat (vide, réponse, correction,
  escalade), la fenêtre de fiche, l'historique, les crédits, la page introuvable, la connexion, le
  menu mobile, la console, le tableau de bord et la base et les modèles.
  - **Résultat : 0 violation** des règles WCAG 2.0, 2.1 et 2.2 de niveaux A et AA.
  - L'audit a fait corriger trois points :
    - le nom accessible des pastilles de source contient désormais le texte visible (critère
      2.5.3) ;
    - la case à cocher de la console passe à 24 px (critère 2.5.8, taille de cible) ;
    - la couche clavier de Recharts est coupée dans les graphiques masqués aux technologies
      d'assistance, dont le tableau « Voir les données » est l'équivalent.
  - Un audit automatique ne remplace pas les vérifications manuelles (lecteur d'écran, ordre de
    tabulation) : elles restent à faire par l'équipe, avec les tests utilisateurs (SUS).
- **Tests de bout en bout** (Phase 6) : `make e2e` (`e2e/parcours.spec.ts`, Playwright) sur la
  pile Docker lancée, via `https://127.0.0.1:8443`, avec les vrais modèles. Quatre parcours :
  chat (exemple cliquable, réponse en flux, sources, panneau d'analyse masquable, « Utile »,
  fiche), trois écritures avec un message `<img onerror>` refusé et affiché comme du texte
  (aucune boîte de dialogue ne s'ouvre), transfert à un conseiller ; console (le conseiller
  prend puis clôture ce dossier) ; tableau de bord (indicateurs et graphiques). Le compte
  conseiller `e2e.conseiller` est créé au premier lancement par le compte administrateur
  (`e2e/global-setup.ts`, mots de passe lus dans `.env`). Résultat : 4/4.
