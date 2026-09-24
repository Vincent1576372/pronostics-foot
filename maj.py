
"""Robot quotidien : analyse 10 matchs du jour et écrit data.json.
La clé vient du secret GitHub API_FOOTBALL_KEY (jamais écrite ici).
Pauses de 7 s entre requêtes (limite gratuite : 10 par minute).
"""
import json
import os
import time
from datetime import datetime, timezone

import requests

CLE = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
GRANDES = [2, 3, 39, 140, 135, 78, 61]  # C1, C3, PL, Liga, Serie A, Bundesliga, L1
MAX = 10
PTS = {"V": 3, "N": 1, "D": 0}


def api(chemin):
    time.sleep(7)
    r = requests.get(BASE + chemin, headers={"x-apisports-key": CLE}, timeout=30)
    j = r.json()
    if j.get("errors"):
        raise RuntimeError(str(j["errors"]))
    return j.get("response", [])


def essayer(chemin):
    try:
        return api(chemin)
    except RuntimeError as e:
        print("Ignoré :", chemin, e)
        return []


def derniers(liste, n=5):
    finis = [f for f in liste if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN")]
    finis.sort(key=lambda f: f["fixture"]["date"])
    return finis[-n:]


def resultat(f, tid):
    cote = "home" if f["teams"]["home"]["id"] == tid else "away"
    w = f["teams"][cote]["winner"]
    return "V" if w is True else "D" if w is False else "N"


def pct(s):
    try:
        return float(str(s).strip("%"))
    except ValueError:
        return None


jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
matchs = api("/fixtures?date=" + jour)
blessures = api("/injuries?date=" + jour)


def rang(m):
    i = GRANDES.index(m["league"]["id"]) if m["league"]["id"] in GRANDES else 99
    return (i, m["fixture"]["date"])


a_venir = [m for m in matchs if m["fixture"]["status"]["short"] in ("NS", "TBD")]
choisis = sorted(a_venir, key=rang)[:MAX]

sortie = []
for m in choisis:
    h, a, fid = m["teams"]["home"], m["teams"]["away"], m["fixture"]["id"]
    saison = m["league"]["season"]
    forme_h = [resultat(f, h["id"]) for f in derniers(essayer(f"/fixtures?team={h['id']}&season={saison}"))]
    forme_a = [resultat(f, a["id"]) for f in derniers(essayer(f"/fixtures?team={a['id']}&season={saison}"))]
    face = derniers(essayer(f"/fixtures/headtohead?h2h={h['id']}-{a['id']}"))
    pred = essayer(f"/predictions?fixture={fid}")

    base = [38.0, 28.0, 34.0]
    if pred:
        p = pred[0]["predictions"]["percent"]
        v = [pct(p.get("home")), pct(p.get("draw")), pct(p.get("away"))]
        if None not in v:
            base = v

    res_face = [resultat(f, h["id"]) for f in face]
    v_h, nuls, v_a = res_face.count("V"), res_face.count("N"), res_face.count("D")

    absents, charge = [], {h["id"]: 0.0, a["id"]: 0.0}
    for b in blessures:
        if b["fixture"]["id"] == fid:
            incertain = b["player"].get("type") == "Questionable"
            charge[b["team"]["id"]] = charge.get(b["team"]["id"], 0) + (0.5 if incertain else 1)
            absents.append({
                "joueur": b["player"]["name"],
                "equipe": b["team"]["name"],
                "statut": "Incertain" if incertain else "Absent",
                "raison": b["player"].get("reason"),
            })

    ajust = (
        0.6 * (sum(PTS[x] for x in forme_h) - sum(PTS[x] for x in forme_a))
        + 1.0 * (v_h - v_a)
        - 1.5 * (charge[h["id"]] - charge[a["id"]])
    )
    dom, nul, ext = max(3, base[0] + ajust), base[1], max(3, base[2] - ajust)
    tot = dom + nul + ext
    proba = [round(100 * dom / tot), 0, round(100 * ext / tot)]
    proba[1] = 100 - proba[0] - proba[2]

    sortie.append({
        "competition": m["league"]["name"],
        "heure": m["fixture"]["date"],
        "domicile": h["name"],
        "exterieur": a["name"],
        "proba": proba,
        "base_api": [round(x) for x in base],
        "ajustement": round(ajust, 1),
        "forme_dom": forme_h,
        "forme_ext": forme_a,
        "face_a_face": {"dom": v_h, "nuls": nuls, "ext": v_a},
        "absents": absents,
    })

sortie.sort(key=lambda x: x["heure"])
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"maj": datetime.now(timezone.utc).isoformat(), "matchs": sortie}, f, ensure_ascii=False, indent=1)
print(len(sortie), "matchs enregistrés")
