"""Robot de vérification : tourne toutes les 2 heures, ne fait qu'une chose,
vérifier si des matchs déjà analysés sont maintenant terminés, et mettre à
jour le taux de réussite. N'utilise que peu de requêtes (une par match en
attente), pour rester dans le quota gratuit.
"""
import json
import os
import time
from datetime import datetime, timezone

import requests

CLE_AF = os.environ["API_FOOTBALL_KEY"]
AF = "https://v3.football.api-sports.io"
HIST = "historique.json"
DATA = "data.json"


def af_ok(chemin):
    time.sleep(7)
    try:
        r = requests.get(AF + chemin, headers={"x-apisports-key": CLE_AF}, timeout=30)
        j = r.json()
        if j.get("errors"):
            print("Ignoré :", chemin, j["errors"])
            return []
        return j.get("response", [])
    except Exception as e:
        print("Ignoré :", chemin, e)
        return []


def issue_reelle(m):
    s = m["score"]["fulltime"]
    if s["home"] is None or s["away"] is None:
        return None
    if s["home"] > s["away"]:
        return "dom"
    if s["home"] < s["away"]:
        return "ext"
    return "nul"


try:
    with open(HIST, encoding="utf-8") as f:
        historique = json.load(f)
except FileNotFoundError:
    historique = []

a_verifier = [h for h in historique if h.get("resultat_reel") is None]
print(len(a_verifier), "match(s) en attente de résultat")

for fid in {h["fixture_id"] for h in a_verifier}:
    res = af_ok(f"/fixtures?id={fid}")
    if res:
        issue = issue_reelle(res[0])
        if issue:
            for h in historique:
                if h["fixture_id"] == fid:
                    h["resultat_reel"] = issue

with open(HIST, "w", encoding="utf-8") as f:
    json.dump(historique, f, ensure_ascii=False, indent=1)

confirmes = [h for h in historique if h["resultat_reel"] is not None]
bons = 0
for h in confirmes:
    ordre = ["dom", "nul", "ext"]
    if ordre[h["proba"].index(max(h["proba"]))] == h["resultat_reel"]:
        bons += 1
taux = round(100 * bons / len(confirmes)) if confirmes else None

try:
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"matchs": []}

data["historique"] = sorted(confirmes, key=lambda h: h["date"], reverse=True)[:20]
data["taux_reussite"] = taux
data["nb_verifies"] = len(confirmes)
data["maj_resultats"] = datetime.now(timezone.utc).isoformat()

with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)

print("Taux de réussite :", taux, "sur", len(confirmes), "matchs vérifiés")
