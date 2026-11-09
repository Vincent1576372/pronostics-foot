"""Robot quotidien SANS API-Football.
- 10 grands matchs : football-data.org (matchs, classement, forme, face-a-face).
- 7 petits matchs : TheSportsDB (cle publique, sans compte).
Ecrit data.json et historique.json. Les scores finaux sont verifies par verifier.py.
Cle dans les secrets GitHub : FOOTBALL_DATA_KEY.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

CLE_FD = os.environ["FOOTBALL_DATA_KEY"]
FD = "https://api.football-data.org/v4"
SDB = "https://www.thesportsdb.com/api/v1/json/3"  # cle publique de test
CODES = ["CL", "PL", "PD", "SA", "BL1", "FL1"]
GRANDES_LIGUES = {
    "uefachampionsleague", "englishpremierleague", "spanishlaliga",
    "italianseriea", "germanbundesliga", "frenchligue1",
}
MAX_GRANDES = 10
MAX_PETITES = 7
MAX_CANDIDATS = 25
PTS = {"V": 3, "N": 1, "D": 0}
BASE = [44.0, 27.0, 29.0]  # depart : domicile / nul / exterieur
HIST = "historique.json"
DATA = "data.json"


def fd(chemin, params=None):
    for essai in range(2):
        time.sleep(6.5)
        try:
            r = requests.get(FD + chemin, params=params,
                             headers={"X-Auth-Token": CLE_FD}, timeout=30)
        except Exception as e:
            print("Ignore (football-data) :", chemin, e)
            return {}
        if r.status_code == 429 and essai == 0:
            print("football-data : trop de demandes, pause de 40 s")
            time.sleep(40)
            continue
        if r.status_code != 200:
            print("Ignore (football-data) :", chemin, r.status_code)
            return {}
        try:
            return r.json()
        except ValueError:
            return {}
    return {}


ENTETES = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
    "Accept": "application/json",
}


def sdb(chemin, params):
    for essai in range(3):
        time.sleep(2.1 if essai == 0 else 8)
        try:
            r = requests.get(f"{SDB}/{chemin}", params=params, headers=ENTETES, timeout=25)
        except Exception as e:
            print("Ignore (TheSportsDB) :", chemin, params, e)
            continue
        try:
            return r.json() or {}
        except ValueError:
            print("TheSportsDB reponse non JSON : code", r.status_code,
                  "debut :", r.text[:120].replace("\n", " "))
    return {}


def normal(nom):
    return "".join(c for c in (nom or "").lower() if c.isalnum())


def lire(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return defaut


# ---------- grands matchs (football-data.org) ----------
def forme_fd(tid):
    data = fd(f"/teams/{tid}/matches", {"status": "FINISHED"})
    ms = sorted(data.get("matches", []), key=lambda m: m["utcDate"])[-5:]
    out = []
    for m in ms:
        w = m["score"]["winner"]
        if w not in ("DRAW", "HOME_TEAM", "AWAY_TEAM"):
            continue
        dom = m["homeTeam"]["id"] == tid
        out.append("N" if w == "DRAW" else ("V" if (w == "HOME_TEAM") == dom else "D"))
    return out


def face_fd(mid, hid, aid):
    data = fd(f"/matches/{mid}/head2head")
    ms = sorted(data.get("matches", []), key=lambda m: m["utcDate"], reverse=True)[:5]
    v_h = v_a = nuls = 0
    for m in ms:
        w = m["score"]["winner"]
        if w == "DRAW":
            nuls += 1
        elif w == "HOME_TEAM":
            gagnant = m["homeTeam"]["id"]
        elif w == "AWAY_TEAM":
            gagnant = m["awayTeam"]["id"]
        else:
            continue
        if w != "DRAW":
            if gagnant == hid:
                v_h += 1
            elif gagnant == aid:
                v_a += 1
    return v_h, nuls, v_a


def charger_ppg(codes):
    """Points par match de chaque equipe (classement actuel)."""
    ppg = {}
    for code in sorted(codes):
        data = fd(f"/competitions/{code}/standings")
        for bloc in data.get("standings", []):
            if bloc.get("type") != "TOTAL":
                continue
            for ligne in bloc.get("table", []):
                if ligne.get("playedGames"):
                    ppg[ligne["team"]["id"]] = ligne["points"] / ligne["playedGames"]
    return ppg


# ---------- petits matchs (TheSportsDB) ----------
def forme_sdb(tid):
    data = sdb("eventslast.php", {"id": tid})
    evs = data.get("results") or data.get("events") or []
    evs = sorted(evs, key=lambda e: e.get("dateEvent") or "")[-5:]
    out = []
    for e in evs:
        try:
            hs, as_ = int(e["intHomeScore"]), int(e["intAwayScore"])
        except (KeyError, TypeError, ValueError):
            continue
        est_dom = str(e.get("idHomeTeam")) == str(tid)
        pour, contre = (hs, as_) if est_dom else (as_, hs)
        out.append("V" if pour > contre else ("D" if pour < contre else "N"))
    return out


def horodatage(e):
    ts = e.get("strTimestamp")
    if not ts and e.get("dateEvent"):
        ts = f"{e['dateEvent']}T{e.get('strTime') or '00:00:00'}"
    if not ts:
        return None
    if len(ts) <= 19 and "+" not in ts and not ts.endswith("Z"):
        ts += "+00:00"
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts


def candidats_sdb(jour, maintenant):
    data = sdb("eventsday.php", {"d": jour, "s": "Soccer"})
    out = []
    for e in data.get("events") or []:
        if normal(e.get("strLeague")) in GRANDES_LIGUES:
            continue
        if e.get("intHomeScore") not in (None, "") or e.get("intAwayScore") not in (None, ""):
            continue
        if (e.get("strStatus") or "").strip().lower() not in ("", "not started", "ns", "tbd"):
            continue
        if not e.get("idHomeTeam") or not e.get("idAwayTeam"):
            continue
        ts = horodatage(e)
        if not ts or datetime.fromisoformat(ts.replace("Z", "+00:00")) <= maintenant:
            continue
        out.append((ts, e))
    out.sort(key=lambda x: x[0])
    return out


# ---------- calcul ----------
def calculer(forme_h, forme_a, v_h, v_a, ppg_h, ppg_a):
    ajust = 1.0 * (v_h - v_a)
    if forme_h and forme_a:  # on ne compare la forme que si on a les deux
        ajust += 0.6 * (sum(PTS[x] for x in forme_h) - sum(PTS[x] for x in forme_a))
    if ppg_h is not None and ppg_a is not None:
        ajust += 6.0 * (ppg_h - ppg_a)
    dom, nul, ext = max(3, BASE[0] + ajust), BASE[1], max(3, BASE[2] - ajust)
    tot = dom + nul + ext
    proba = [round(100 * dom / tot), 0, round(100 * ext / tot)]
    proba[1] = 100 - proba[0] - proba[2]
    return proba, round(ajust, 1)


def fiche(categorie, competition, heure, dom, ext, proba, ajust,
          forme_h, forme_a, src_h, src_a, v_h, nuls, v_a):
    return {
        "categorie": categorie,
        "competition": competition,
        "heure": heure,
        "domicile": dom,
        "exterieur": ext,
        "proba": proba,
        "base_api": [round(x) for x in BASE],
        "ajustement": ajust,
        "forme_dom": forme_h,
        "forme_ext": forme_a,
        "source_dom": src_h,
        "source_ext": src_a,
        "face_a_face": {"dom": v_h, "nuls": nuls, "ext": v_a},
        "absents": [],
    }


def main():
    maintenant = datetime.now(timezone.utc)
    jour = maintenant.strftime("%Y-%m-%d")
    lendemain = (maintenant + timedelta(days=1)).strftime("%Y-%m-%d")

    historique = lire(HIST, [])
    anciennes_donnees = lire(DATA, {})
    sortie, a_enregistrer = [], []

    # 1) Grands matchs
    d = fd("/matches", {"dateFrom": jour, "dateTo": lendemain, "competitions": ",".join(CODES)})
    grands = [m for m in d.get("matches", [])
              if m.get("status") in ("TIMED", "SCHEDULED") and m["utcDate"][:10] == jour]
    grands.sort(key=lambda m: m["utcDate"])
    grands = grands[:MAX_GRANDES]
    ppg = charger_ppg({m["competition"]["code"] for m in grands}) if grands else {}

    for m in grands:
        h, a = m["homeTeam"], m["awayTeam"]
        nom_h = h.get("shortName") or h["name"]
        nom_a = a.get("shortName") or a["name"]
        forme_h, forme_a = forme_fd(h["id"]), forme_fd(a["id"])
        v_h, nuls, v_a = face_fd(m["id"], h["id"], a["id"])
        proba, ajust = calculer(forme_h, forme_a, v_h, v_a, ppg.get(h["id"]), ppg.get(a["id"]))
        sortie.append(fiche("principal", m["competition"]["name"], m["utcDate"], nom_h, nom_a,
                            proba, ajust, forme_h, forme_a,
                            "actuelle" if forme_h else "", "actuelle" if forme_a else "",
                            v_h, nuls, v_a))
        a_enregistrer.append({"source": "fd", "fixture_id": m["id"], "date": m["utcDate"],
                              "competition": m["competition"]["name"],
                              "domicile": nom_h, "exterieur": nom_a, "proba": proba})

    # 2) Petits matchs
    petites = 0
    candidats = candidats_sdb(jour, maintenant)
    print("TheSportsDB :", len(candidats), "matchs candidats")
    for ts, e in candidats[:MAX_CANDIDATS]:
        if petites >= MAX_PETITES:
            break
        forme_h, forme_a = forme_sdb(e["idHomeTeam"]), forme_sdb(e["idAwayTeam"])
        if not forme_h and not forme_a:
            continue  # aucune donnee sur les deux equipes : on saute ce match
        proba, ajust = calculer(forme_h, forme_a, 0, 0, None, None)
        sortie.append(fiche("secondaire", e.get("strLeague") or "Autre compétition", ts,
                            e["strHomeTeam"], e["strAwayTeam"], proba, ajust,
                            forme_h, forme_a,
                            "actuelle" if forme_h else "", "actuelle" if forme_a else "",
                            0, 0, 0))
        a_enregistrer.append({"source": "sdb", "fixture_id": str(e["idEvent"]), "date": ts,
                              "competition": e.get("strLeague") or "",
                              "domicile": e["strHomeTeam"], "exterieur": e["strAwayTeam"],
                              "proba": proba})
        petites += 1

    # 3) Historique : ajout sans doublon
    connus = {(h.get("source", "af"), str(h["fixture_id"])): h for h in historique}
    for n in a_enregistrer:
        cle = (n["source"], str(n["fixture_id"]))
        if cle in connus:
            if connus[cle].get("resultat_reel") is None:
                connus[cle]["proba"] = n["proba"]
        else:
            n["resultat_reel"] = None
            historique.append(n)

    limite = (maintenant - timedelta(days=60)).strftime("%Y-%m-%d")
    historique = [h for h in historique if h["date"][:10] >= limite]

    confirmes = [h for h in historique if h.get("resultat_reel") in ("dom", "nul", "ext")]
    bons = 0
    for h in confirmes:
        if ["dom", "nul", "ext"][h["proba"].index(max(h["proba"]))] == h["resultat_reel"]:
            bons += 1
    taux = round(100 * bons / len(confirmes)) if confirmes else None

    sortie.sort(key=lambda x: x["heure"])
    data = {
        "maj": maintenant.isoformat(),
        "matchs": sortie,
        "historique": sorted(confirmes, key=lambda h: h["date"], reverse=True)[:30],
        "taux_reussite": taux,
        "nb_verifies": len(confirmes),
    }
    if anciennes_donnees.get("maj_resultats"):
        data["maj_resultats"] = anciennes_donnees["maj_resultats"]

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=1)

    print(len(grands), "grands matchs,", petites, "petits matchs,",
          len(confirmes), "verifies, taux :", taux)


main()
