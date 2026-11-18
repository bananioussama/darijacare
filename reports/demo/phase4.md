# Démonstration de l'API (Phase 4)

API lancée avec les vrais modèles (NLU v5, BGE-M3, serveur Qdrant), PostgreSQL de
docker-compose. Messages **fictifs** ; données d'entraînement **synthétiques**.

## Santé

```json
{
  "status": "ok",
  "database": "ok",
  "qdrant": "ok",
  "models_loaded": true,
  "nlu_model": "v5@8e694ecf",
  "decision_config": "7c36b2a9aae0710a",
  "kb_fiches": 75
}
```

## Conversations

### arabe — « الكونيكسيون مقطوعة من البارح ف الدار والضو ديال الروتور حمر »

- NLU : `home_outage` (home_internet), confiance 0.88, urgence 2, p(conseiller) 0.07, écriture `arabic`
- Décision : règle 7 `reponse_ancree`
- Sources : KB-home_outage
- Escalade : non
- Latence : serveur 1882 ms, requête complète 1939 ms

```text
مرحبا! بخصوص «الأنترنيت ديال الدار مقطوع»، هادي الخطوات:
1. تأكد بلي البوكس مشعلة وشوف الضواو (الضو الحمر ولا الطافي كيعني الخط مقطوع).
2. شوف الكابلات (لافيبر ولا ADSL والضو) بلا ما تلوي الكابل ديال لافيبر.
3. طفي البوكس دقيقة ومن بعد شعلها، وتسنى حتى يتستقرو الضواو.
4. شوف فالتطبيق واش كاين شي عطب معلن فالحومة.
إلا بقا المشكل، نقدر نحولك لمستشار.
(المصدر، بطاقة خيالية : KB-home_outage, v1)
```

### arabizi — « chargit 20dh w ma wslatni walo, 3afak chofo lia »

- NLU : `recharge_failed` (prepaid_credit), confiance 0.86, urgence 2, p(conseiller) 0.06, écriture `arabizi`
- Décision : règle 7 `reponse_ancree`
- Sources : KB-recharge_failed
- Escalade : non
- Latence : serveur 1760 ms, requête complète 1804 ms

```text
Salam! 3la « Recharge ma wseltch wla lcode ma dazch », hadi lkhatawat :
1. Chouf solde men ba3d chi d9aye9 (solde y9der yt3ttel chwiya).
2. 3awed chouf lcode li dkhelti (ar9am m9loubin, espace zayed) w 3awed jerreb merra wa7da.
3. Ila charjiti f internet wla b mobile money, l9a la reference dyal l3amaliya wla lwasl.
4. Ila recharge ba9a ma wseltch, dir chkaya « Recharge ma wseltch » m3a lcode wla la reference.
Ila b9a lmochkil, n9der n7awlek l chi conseiller.
(Source, fiche fictive : KB-recharge_failed, v1)
```

### mixte — « Bonjour, ma facture de ce mois est trop élevée, je veux comprendre pourquoi »

- NLU : `invoice_dispute` (billing_payment), confiance 0.87, urgence 1, p(conseiller) 0.06, écriture `mixed`
- Décision : règle 7 `reponse_ancree`
- Sources : KB-invoice_dispute
- Escalade : non
- Latence : serveur 1753 ms, requête complète 1813 ms

```text
Salam ! À propos de « Contester une facture », voici les étapes :
1. Repérer sur la facture détaillée la ligne ou le montant contesté.
2. Rassembler les éléments utiles (date, service concerné, captures d'écran éventuelles).
3. Déposer une réclamation depuis l'espace client, rubrique « Réclamations », en choisissant « Contestation de facture ».
4. Noter le numéro de réclamation affiché pour le suivi.
Si le problème persiste, je peux vous mettre en relation avec un conseiller.
(Source, fiche fictive : KB-invoice_dispute, v1)
```

### arabe — « تسرق ليا التيليفون دابا، عافاك بلوكيو ليا الخط، النمرة ديالي <TEL> »

- NLU : `lost_stolen` (sim_line), confiance 0.88, urgence 3, p(conseiller) 0.09, écriture `arabic`
- Décision : règle 2 `escalade`
- Sources : KB-lost_stolen
- Escalade : DC-7F19B411 (critique)
- Latence : serveur 1502 ms, requête complète 1576 ms

```text
فهمتك، غادي نحولك لمستشار بالأولوية. ما تحتاجش تعاود كلشي، الطلب ديالك غادي يكون عندو.
فهاد الوقت، باش تحمي راسك:
1. طلب فالحين البلوكاج ديال الخط (الزر «بلوكي الخط ديالي» فالفضاء ديال الكليان ولا مستشار).
2. إلا كانت شي محفظة إلكترونية مربوطة مع الخط، طلب حتى هي تتبلوكا.
3. بدل كلمات السر ديال الحسابات اللي كانو محلولين فالتيليفون (الإيميل، الريزو سوسيو، البنكة).
4. صرح بالسرقة عند السلطات واحتافظ بالوصل.
5. من بعد طلب سيم جديدة بنفس النمرة فالوكالة (شوف «نبدل السيم»).
(المصدر، بطاقة خيالية : KB-lost_stolen, v1)
رقم الملف ديالك : DC-7F19B411
```

### arabizi — « bghit nhder m3a chi conseiller daba »

- NLU : `human_agent` (customer_care), confiance 0.88, urgence 2, p(conseiller) 0.94, écriture `arabizi`
- Décision : règle 2 `escalade`
- Sources : aucune
- Escalade : DC-CFCEFDCF (haute)
- Latence : serveur 1414 ms, requête complète 1452 ms

```text
Fhamtek, ghadi n7awlek l chi conseiller b l2awlawiya. Ma t7tajch t3awd kolchi, talab dyalek ghadi ykoun 3ndo.
Numero dyal dossier dyalek : DC-CFCEFDCF
```

## Session et isolation

- Deuxième message dans la même session : tour 2 ; historique : 2 messages.
- Lecture de la session d'un autre client : HTTP 403.

## Console conseiller

| Dossier | Priorité | Niveau | Intention | Écriture |
|---|---|---|---|---|
| DC-7F19B411 | 80.1 | critique | lost_stolen | arabic |
| DC-CFCEFDCF | 64.0 | haute | human_agent | arabizi |

Dossier en tête : DC-7F19B411 ; fiche proposée `KB-lost_stolen` ; statuts : nouveau → en_cours → cloture.

## Latence (20 messages, CPU)

| Mesure | Médiane | p95 |
|---|---|---|
| Traitement serveur (garde, NLU, décision, recherche, gabarit) | 1759 ms | 1839 ms |
| Requête complète vue du client (dont enregistrement) | 1810 ms | 1900 ms |

## Tableau de bord (rôle ml)

```json
{
  "periode_jours": 30,
  "messages": 26,
  "escalades": 2,
  "taux_escalade": 0.0769,
  "latence_ms": {
    "p50": 1755.8,
    "p95": 1870.8
  },
  "par_script": {
    "mixed": 9,
    "arabic": 6,
    "arabizi": 11
  },
  "par_decision": {
    "clarification": 1,
    "reponse_ancree": 23,
    "escalade": 2
  },
  "top_intentions": [
    {
      "intent": "balance_deducted",
      "messages": 4
    },
    {
      "intent": "data_pass_buy",
      "messages": 4
    },
    {
      "intent": "home_slow",
      "messages": 4
    },
    {
      "intent": "international_calls",
      "messages": 4
    },
    {
      "intent": "plan_offers_info",
      "messages": 4
    },
    {
      "intent": "home_outage",
      "messages": 1
    },
    {
      "intent": "human_agent",
      "messages": 1
    },
    {
      "intent": "invoice_dispute",
      "messages": 1
    },
    {
      "intent": "lost_stolen",
      "messages": 1
    },
    {
      "intent": "pay_bill",
      "messages": 1
    }
  ],
  "feedback": {
    "utile": 1
  },
  "modele": {
    "version": "v5@8e694ecf",
    "evaluation": {
      "dataset": "test",
      "f1_macro": 0.8947733183529385,
      "ece": 0.04479345188234751
    }
  }
}
```
