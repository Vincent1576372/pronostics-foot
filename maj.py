"""Robot quotidien : analyse les matchs des grandes compétitions,
et vérifie les résultats des prédictions de la veille.
Deux sources : API-Football (matchs, blessures, ses prédictions)
et football-data.org (forme actuelle des équipes, saison en cours).
Clés dans les secrets GitHub : API_FOOTBALL_KEY, FOOTBALL_DATA_KEY.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

CLE_AF = os.environ["API_FOOTBALL_KEY"]
CLE_FD = os.environ["FOOTBALL_DATA_KEY"]
AF = "https://v3.football.api-sports.io"
FD = "https://api.football-data.org/v4"
MAX = 10
PTS = {"V": 3, "N": 1, "D": 0}
CODES = {2: "CL", 39: "PL", 140: "PD", 135: "SA", 78: "BL1", 61: "FL1"}
HIST = "historique.json"


def af(chemin):
    time.sleep(7)
    r = requests.get(AF + chemin, headers={"x-apisports-key": CLE_AF}, timeout=30)
    j = r.json()
    if j.get("errors"):
        raise RuntimeError(str(j["errors"]))
    return j.get("response", [])


def af_ok(chemin):
    try:
        return af(chemin)
    except RuntimeError as e:
        print("Ignoré (API-Football) :", chemin, e)
        return []


def fd(chemin):
    time.sleep(6.5)
    r = requests.get(FD + chemin, headers={"X-Auth-Token": CLE_FD}, timeout=30)
    if r.status_code != 200:
        print("Ignoré (football-data) :", chemin, r.status_code)
        return {}
    return r.json()


def normal(nom):
    return "".join(c for c in nom.lower() if c.isalnum())


def resultat(f, tid):
    cote = "home" if f["teams"]["home"]["id"] == tid else "away"
    w = f["teams"][cote]["winner"]
    return "V" if w is True else "D" if w is False else "N"


def pct(s):
    try:
        return float(str(s).strip("%"))
    except ValueError:
        return None


def issue_reelle(m):
    """'dom', 'nul' ou 'ext' selon le score final, ou None si pas encore joué."""
    s = m["score"]["fulltime"]
    if s["home"] is None or s["away"] is None:
        return None
    if s["home"] > s["away"]:
        return "dom"
    if s["home"] < s["away"]:
        return "ext"
    return "nul"


# --- 1) Vérifier les prédictions passées non encore confirmées ---
try:
    with open(HIST, encoding="utf-8") as f:
        historique = json.load(f)
except FileNotFoundError:
    historique = []

a_verifier = [h for h in historique if h.get("resultat_reel") is None]
if a_verifier:
    ids = {h["fixture_id"] for h in a_verifier}
    for fid in ids:
        res = af_ok(f"/fixtures?id={fid}")
        if res:
            issue = issue_reelle(res[0])
            if issue:
                for h in historique:
                    if h["fixture_id"] == fid:
                        h["resultat_reel"] = issue

# --- 2) Analyser les matchs du jour ---
noms_equipes = {}
for code in set(CODES.values()):
    data = fd(f"/competitions/{code}/teams")
    for e in data.get("teams", []):
        noms_equipes[normal(e["name"])] = e["id"]
        noms_equipes[normal(e["shortName"])] = e["id"]


def forme_fd(nom_equipe):
    tid = noms_equipes.get(normal(nom_equipe))
    if not tid:
        return []
    data = fd(f"/teams/{tid}/matches?status=FINISHED&limit=5")
    out = []
    for m in data.get("matches", []):
        w = m["score"]["winner"]
        dom = m["homeTeam"]["id"] == tid
        if w == "DRAW":
            out.append("N")
        elif (w == "HOME_TEAM") == dom:
            out.append("V")
        else:
            out.append("D")
    return out


jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
matchs = af(f"/fixtures?date={jour}")
blessures = af(f"/injuries?date={jour}")

a_venir = [
    m for m in matchs
    if m["fixture"]["status"]["short"] in ("NS", "TBD") and m["league"]["id"] in CODES
]
a_venir.sort(key=lambda m: m["fixture"]["date"])
choisis = a_venir[:MAX]

sortie = []
for m in choisis:
    h, a, fid = m["teams"]["home"], m["teams"]["away"], m["fixture"]["id"]
    forme_h = forme_fd(h["name"])
    forme_a = forme_fd(a["name"])
    face = af_ok(f"/fixtures/headtohead?h2h={h['id']}-{a['id']}&last=5")
    pred = af_ok(f"/predictions?fixture={fid}")

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

    match_sortie = {
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
    }
    sortie.append(match_sortie)
    historique.append({
        "fixture_id": fid,
        "date": m["fixture"]["date"],
        "domicile": h["name"],
        "exterieur": a["name"],
        "proba": proba,
        "resultat_reel": None,
    })

# Garde 60 jours d'historique pour ne pas grossir indéfiniment
limite = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
historique = [h for h in historique if h["date"] >= limite]

# --- 3) Calcul du taux de réussite (meilleur pari du modèle = résultat réel) ---
confirmes = [h for h in historique if h["resultat_reel"] is not None]
bons = 0
for h in confirmes:
    ordre = ["dom", "nul", "ext"]
    meilleur = ordre[h["proba"].index(max(h["proba"]))]
    if meilleur == h["resultat_reel"]:
        bons += 1
taux = round(100 * bons / len(confirmes)) if confirmes else None

sortie.sort(key=lambda x: x["heure"])
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({
        "maj": datetime.now(timezone.utc).isoformat(),
        "matchs": sortie,
        "historique": sorted(confirmes, key=lambda h: h["date"], reverse=True)[:20],
        "taux_reussite": taux,
        "nb_verifies": len(confirmes),
    }, f, ensure_ascii=False, indent=1)

with open(HIST, "w", encoding="utf-8") as f:
    json.dump(historique, f, ensure_ascii=False, indent=1)

print(len(sortie), "matchs du jour,", len(confirmes), "résultats vérifiés, taux :", taux)
