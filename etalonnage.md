# Banc d'essai du modèle VM_R (version 2)

Généré le 13/11/2026 03:45 · 15614 matchs passés · 8 championnats · durée 211 s

Réglage sur les saisons **2122, 2223, 2324, 2425**, jugement sur **2526, 2627** (3802 matchs jamais vus pendant le réglage). Pour chaque match, le modèle ne reçoit que ce qu'on savait avant le coup d'envoi.

« Sans mémoire » = réglages applicables tout de suite au robot. « Avec mémoire » = en plus, on tient compte de la saison précédente (à brancher plus tard).

## 1. Résultat du match (1X2) — matchs jamais vus

| | Actuel | Réglé sans mémoire | Réglé avec mémoire | Cotes du marché | Toujours « domicile » |
|---|---|---|---|---|---|
| Bon résultat trouvé | 48,4 % | 48,8 % | 49,8 % | 52,9 % | 43,3 % |

Perte logarithmique du 1X2 (plus bas = mieux ; mesure la qualité des pourcentages) :

- hasard moyen : **1,074**
- modèle actuel : **1,032**
- réglé sans mémoire : **1,020**
- réglé avec mémoire : **1,007**
- cotes du marché : **0,979**

## 2. Fiabilité des pourcentages (1X2, réglé sans mémoire)

Quand le modèle annonce une probabilité pour sa meilleure issue, combien de fois ça arrive vraiment ?

| Annoncé | Matchs | Annoncé en moyenne | Réellement arrivé |
|---|---|---|---|
| 0–40 % | 779 | 37,9 % | 36,2 % |
| 40–45 % | 898 | 42,5 % | 42,9 % |
| 45–50 % | 663 | 47,4 % | 46,5 % |
| 50–55 % | 500 | 52,4 % | 50,6 % |
| 55–60 % | 378 | 57,5 % | 59,0 % |
| 60–70 % | 399 | 64,2 % | 65,4 % |
| 70–100 % | 185 | 75,7 % | 77,3 % |

## 3. Autres marchés — réglé sans mémoire, matchs jamais vus

Progrès = amélioration de la perte logarithmique par rapport à la fréquence moyenne. Fiabilité : Bonne ≥ 7 %, Moyenne 3–7 %, Faible < 3 %.

| Marché | Matchs | Progrès | Fiabilité | Écart avec le marché |
|---|---|---|---|---|
| Plus de 0,5 but | 3802 | 0,2 % | Faible |  |
| Plus de 1,5 but | 3802 | 0,5 % | Faible |  |
| Plus de 2,5 buts | 3802 | 0,8 % | Faible | modèle 0,684 · marché 0,669 |
| Plus de 3,5 buts | 3802 | 1,7 % | Faible |  |
| Plus de 4,5 buts | 3802 | 2,2 % | Faible |  |
| Les deux équipes marquent | 3802 | 0,3 % | Faible |  |
| Domicile marque au moins 1 but | 3802 | 4,0 % | Moyenne |  |
| Domicile marque 2 buts ou plus | 3802 | 4,0 % | Moyenne |  |
| Extérieur marque au moins 1 but | 3802 | 3,1 % | Moyenne |  |
| Extérieur marque 2 buts ou plus | 3802 | 3,1 % | Moyenne |  |
| Double chance : domicile ou nul | 3802 | 6,9 % | Moyenne |  |
| Double chance : pas de nul | 3802 | 0,2 % | Faible |  |
| Double chance : nul ou extérieur | 3802 | 6,3 % | Moyenne |  |
| Domicile gagne par 2 buts ou plus | 3802 | 6,2 % | Moyenne |  |
| Extérieur gagne par 2 buts ou plus | 3802 | 5,8 % | Moyenne |  |

## 4. Réglages

| | Actuel | Sans mémoire | Avec mémoire |
|---|---|---|---|
| Poids du passé du classement (lissage) | 5.0 | 16.0 | 16.0 |
| Poids de la forme récente | 0.008 | 0.024 | 0.024 |
| Poids des confrontations directes | 0.015 | 0.06 | 0.06 |
| Correction des petits scores (nuls) | -0.08 | -0.08 | -0.08 |
| Mémoire de la saison précédente | 0.0 | 0.0 | 0.5 |
| Prudence des pourcentages (1 = aucune) | 1.0 | 0.8 | 0.8 |

Valeurs testées pour chaque réglage : Poids du passé du classement [5.0, 8.0, 12.0, 16.0, 24.0, 40.0] ; Poids de la forme récente [0.0, 0.008, 0.016, 0.024, 0.032] ; Poids des confrontations directes [0.0, 0.015, 0.03, 0.045, 0.06, 0.08] ; Correction des petits scores [-0.14, -0.1, -0.06, -0.03, 0.0] ; Mémoire de la saison précédente [0.0, 0.25, 0.5, 0.75, 1.0] ; Prudence des pourcentages [0.6, 0.7, 0.8, 0.9, 1.0, 1.1].

## 5. Effet de chaque changement, pris isolément, sur les matchs jamais vus

Variation de l'objectif (plus bas = mieux ; un écart inférieur à 0,0005 est dans le bruit).

| Réglage | Avant → après | Effet |
|---|---|---|
| Poids du passé du classement (lissage) | 5.0 → 16.0 | -0,0092 (mieux) |
| Poids de la forme récente | 0.008 → 0.024 | +0,0016 (pire) |
| Poids des confrontations directes | 0.015 → 0.06 | +0,0001 (neutre) |
| Prudence des pourcentages (1 = aucune) | 1.0 → 0.8 | -0,0058 (mieux) |
| Mémoire de la saison précédente | 0.0 → 0.5 | -0,0161 (mieux) |

Objectif global sur les matchs jamais vus : actuel 0,71941 · sans mémoire 0,70641 · avec mémoire 0,70095.

## 6. Mi-temps

Part réelle des buts marqués en 1re mi-temps : **44,1 %** (notre modèle suppose 45 %, 3802 matchs). Meilleure valeur testée : **46 %**.
