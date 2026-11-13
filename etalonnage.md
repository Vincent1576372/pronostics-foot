# Banc d'essai du modèle VM_R

Généré le 13/11/2026 03:27 · 15614 matchs passés · 8 championnats · durée 122 s

Le modèle est réglé sur les saisons **2122, 2223, 2324, 2425** puis jugé sur **2526, 2627** (3802 matchs qu'il n'a jamais vus pendant le réglage). Pour chaque match, le modèle ne reçoit que ce qu'on savait avant le coup d'envoi.

## 1. Résultat du match (1X2) — matchs jamais vus

| | Modèle actuel | Modèle réglé | Cotes du marché | Toujours « domicile » |
|---|---|---|---|---|
| Bon résultat trouvé | 48,4 % | 50,1 % | 52,9 % | 43,3 % |

Perte logarithmique du 1X2 (plus bas = mieux ; mesure la qualité des pourcentages, pas seulement le bon résultat) :

- hasard moyen : **1,074**
- modèle actuel : **1,032**
- modèle réglé : **1,005**
- cotes du marché : **0,979** (sur 3802 matchs avec cotes ; le modèle actuel y fait 1,032)

## 2. Fiabilité des pourcentages (1X2, modèle réglé)

Quand le modèle annonce une certaine probabilité pour sa meilleure issue, combien de fois ça arrive vraiment ?

| Annoncé | Matchs | Annoncé en moyenne | Réellement arrivé |
|---|---|---|---|
| 0–40 % | 624 | 37,6 % | 38,5 % |
| 40–45 % | 765 | 42,4 % | 42,1 % |
| 45–50 % | 633 | 47,4 % | 41,4 % |
| 50–55 % | 458 | 52,4 % | 47,8 % |
| 55–60 % | 380 | 57,3 % | 53,2 % |
| 60–70 % | 525 | 64,7 % | 65,0 % |
| 70–100 % | 417 | 78,1 % | 76,5 % |

## 3. Autres marchés — modèle réglé, matchs jamais vus

Progrès = amélioration de la perte logarithmique par rapport à la fréquence moyenne (hasard moyen).

| Marché | Matchs | Progrès sur le hasard | Écart avec le marché |
|---|---|---|---|
| Plus de 0,5 but | 3802 | 0,9 % |  |
| Plus de 1,5 but | 3802 | 1,1 % |  |
| Plus de 2,5 buts | 3802 | 1,4 % | modèle 0,680 · marché 0,669 |
| Plus de 3,5 buts | 3802 | 1,9 % |  |
| Plus de 4,5 buts | 3802 | 2,4 % |  |
| Les deux équipes marquent | 3802 | 0,4 % |  |
| Domicile marque au moins 1 but | 3802 | 5,5 % |  |
| Domicile marque 2 buts ou plus | 3802 | 5,1 % |  |
| Extérieur marque au moins 1 but | 3802 | 4,0 % |  |
| Extérieur marque 2 buts ou plus | 3802 | 3,8 % |  |
| Double chance : domicile ou nul | 3802 | 8,9 % |  |
| Double chance : pas de nul | 3802 | 0,7 % |  |
| Double chance : nul ou extérieur | 3802 | 7,9 % |  |
| Domicile gagne par 2 buts ou plus | 3802 | 7,9 % |  |
| Extérieur gagne par 2 buts ou plus | 3802 | 7,3 % |  |

## 4. Réglages

| | Actuel | Proposé |
|---|---|---|
| Poids du passé du classement (lissage) | 5.0 | 12.0 |
| Poids de la forme récente | 0.008 | 0.016 |
| Poids des confrontations directes | 0.015 | 0.04 |
| Correction des petits scores (nuls) | -0.08 | -0.08 |
| Mémoire de la saison précédente | 0.0 | 0.5 |

« Mémoire de la saison précédente » : 0 = on repart de zéro à chaque saison ; 0,5 = le bilan de la saison passée compte comme une demi-saison de matchs au départ.

Étapes de l'optimisation (objectif sur les saisons d'apprentissage, plus bas = mieux) :

- départ → 0,71747
- k = 8.0 → 0,71274
- k = 12.0 → 0,71061
- forme = 0.012 → 0,71024
- forme = 0.016 → 0,71003
- h2h = 0.025 → 0,70973
- h2h = 0.04 → 0,70947
- memoire = 0.25 → 0,70482
- memoire = 0.5 → 0,70387

Sur les matchs **jamais vus** : objectif 0,71941 (actuel) → 0,70152 (réglé). Le réglage améliore bien le modèle.

## 5. Mi-temps

Part réelle des buts marqués en 1re mi-temps : **44,1 %** (notre modèle suppose 45 %, 3802 matchs). Meilleure valeur testée : **44 %**.
