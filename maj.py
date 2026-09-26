"""Robot quotidien : 10 matchs des grandes compétitions (données actuelles
via football-data.org) + 7 matchs de complément dans d'autres compétitions
(données actuelles via TheSportsDB si l'équipe y est connue, sinon 2022-2024
via API-Football, clairement indiqué). Vérifie aussi les résultats de la veille.
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
SDB = "https://www.thesportsdb.com/api/v1/json/3"  # clé publique de test
MAX_GRANDES = 10
MAX_PETITES = 7
PTS = {"V": 3, "N": 1, "D": 0}
CODES = {2: "CL", 39: "PL", 140: "PD", 135: "SA", 78: "BL1", 61: "FL1"}
SAISONS_GRATUITES = [2024, 2023, 2022]
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


def sdb(chemin, params):
    time.sleep(2.1)
    try:
        r = requests.get(f"{SDB}/{chemin}", params=params, timeout=20)
        return r.json() or {}
    except Exception as e:
        print("Ignoré (TheSportsDB) :", chemin, params, e)
        return {}


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
    s = m["score"]["fulltime"]
    if s["home"] is None or s["away"] is None:
        return None
    if s["home"] > s["away"]:
        return "dom"
    if s["home"] < s["away"]:
        return "ext"
    return "nul"


def derniers(liste, n=5):
    finis = [f for f in liste if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN")]
    finis.sort(key=lambda f: f["fixture"]["date"])
    return finis[-n:]


def forme_af(team_id):
    """Repli pour les petits matchs si TheSportsDB ne connaît pas l'équipe."""
    for s in SAISONS_GRATUITES:
        r = af_ok(f"/fixtures?team={team_id}&season={s}")
        if r:
            return [resultat(f, team_id) for f in derniers(r)]
    return []


def forme_sdb(nom_equipe):
    """None = équipe non trouvée. [] ou liste = équipe trouvée (données actuelles)."""
    data = sdb("searchteams.php", {"t": nom_equipe})
    equipes = data.get("teams") or []
    if not equipes:
        return None
    tid = equipes[0]["idTeam"]
    data2 = sdb("eventslast.php", {"id": tid})
    evenements = data2.get("results") or data2.get("events") or []
    out = []
    for e in evenements:
        hs, as_ = e.get("intHomeScore"), e.get("intAwayScore")
        if hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        est_domicile = normal(e.get("strHomeTeam", "")) == normal(nom_equipe)
        score_lui = hs if est_domicile else as_
        score_adv = as_ if est_domicile else hs
        out.append("V" if score_lui > score_adv else ("D" if score_lui < score_adv else "N"))
    return out


# --- 1) Vérifier les prédictions passées non encore confirmées ---
try:
    with open(HIST, encoding="utf-8") as f:
        historique = json.load(f)
except FileNotFoundError:
    historique = []

a_verifier = [h for h in historique if h.get("resultat_reel") is None]
for fid in {h["fixture_id"] for h in a_verifier}:
    res = af_ok(f"/fixtures?id={fid}")
    if res:
        issue = issue_reelle(res[0])
        if issue:
            for h in historique:
                if h["fixture_id"] == fid:
                    h["resultat_reel"] = issue

# --- 2) Préparer les noms d'équipes des grandes compétitions (football-data) ---
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
        out.append("N" if w == "DRAW" else ("V" if (w == "HOME_TEAM") == dom else "D"))
    return out


# --- 3) Sélectionner les matchs du jour ---
jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
matchs = af(f"/fixtures?date={jour}")
blessures = af(f"/injuries?date={jour}")

a_venir = [m for m in matchs if m["fixture"]["status"]["short"] in ("NS", "TBD")]
a_venir.sort(key=lambda m: m["fixture"]["date"])

grandes = [m for m in a_venir if m["league"]["id"] in CODES][:MAX_GRANDES]
petites = [m for m in a_venir if m["league"]["id"] not in CODES][:MAX_PETITES]


def forme_petit(team_id, nom):
    r = forme_sdb(nom)
    if r is not None:
        return r, "actuelle"
    return forme_af(team_id), "historique"


def analyser(m, categorie):
    h, a, fid = m["teams"]["home"], m["teams"]["away"], m["fixture"]["id"]
    if categorie == "principal":
        forme_h, forme_a = forme_fd(h["name"]), forme_fd(a["name"])
        src_h = src_a = "actuelle"
    else:
        forme_h, src_h = forme_petit(h["id"], h["name"])
        forme_a, src_a = forme_petit(a["id"], a["name"])

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

    return {
        "categorie": categorie,
        "competition": m["league"]["name"],
        "heure": m["fixture"]["date"],
        "domicile": h["name"],
        "exterieur": a["name"],
        "proba": proba,
        "base_api": [round(x) for x in base],
        "ajustement": round(ajust, 1),
        "forme_dom": forme_h,
        "forme_ext": forme_a,
        "source_dom": src_h,
        "source_ext": src_a,
        "face_a_face": {"dom": v_h, "nuls": nuls, "ext": v_a},
        "absents": absents,
    }, fid


sortie = []
for m in grandes:
    r, fid = analyser(m, "principal")
    sortie.append(r)
    historique.append({"fixture_id": fid, "date": r["heure"], "domicile": r["domicile"], "exterieur": r["exterieur"], "proba": r["proba"], "resultat_reel": None})
for m in petites:
    r, fid = analyser(m, "secondaire")
    sortie.append(r)
    historique.append({"fixture_id": fid, "date": r["heure"], "domicile": r["domicile"], "exterieur": r["exterieur"], "proba": r["proba"], "resultat_reel": None})

limite = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
historique = [h for h in historique if h["date"] >= limite]

confirmes = [h for h in historique if h["resultat_reel"] is not None]
bons = 0
for h in confirmes:
    ordre = ["dom", "nul", "ext"]
    if ordre[h["proba"].index(max(h["proba"]))] == h["resultat_reel"]:
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

print(len(grandes), "grands matchs,", len(petites), "petits matchs,", len(confirmes), "vérifiés, taux :", taux)
