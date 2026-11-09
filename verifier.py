"""Robot de verification SANS API-Football : tourne toutes les 2 heures.
Pour chaque match analyse et maintenant termine, recupere le score final et les
buteurs (football-data.org pour les grands matchs, TheSportsDB pour les petits),
puis met a jour le taux de reussite. Cle : FOOTBALL_DATA_KEY (secret GitHub).
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

CLE_FD = os.environ["FOOTBALL_DATA_KEY"]
FD = "https://api.football-data.org/v4"
SDB = "https://www.thesportsdb.com/api/v1/json/123"
HIST = "historique.json"
DATA = "data.json"
MAX_APPELS_FD = 25  # limite par passage, le reste sera fait au passage suivant
NON_FINIS = {"not started", "ns", "tbd", "postponed", "cancelled", "canceled",
             "abandoned", "suspended", "1h", "2h", "ht", "et", "bt", "p", "live"}
appels_fd = 0


def fd(chemin, params=None):
    global appels_fd
    appels_fd += 1
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


def meme_equipe(a, b):
    na, nb = normal(a), normal(b)
    return len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na)


def lire(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return defaut


def issue(sh, sa):
    return "dom" if sh > sa else ("ext" if sh < sa else "nul")


def date_match(h):
    try:
        return datetime.fromisoformat(h["date"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


# ---------- football-data.org ----------
def resultat_fd(mid, nom_dom, nom_ext):
    d = fd(f"/matches/{mid}")
    if not d or d.get("status") != "FINISHED":
        return None
    s = d.get("score") or {}
    blob = s.get("regularTime") or s.get("fullTime") or {}
    sh, sa = blob.get("home"), blob.get("away")
    if sh is None or sa is None:
        return None
    buteurs = []
    id_dom = (d.get("homeTeam") or {}).get("id")
    for g in d.get("goals") or []:
        equipe = nom_dom if (g.get("team") or {}).get("id") == id_dom else nom_ext
        buteurs.append({
            "equipe": equipe,
            "joueur": (g.get("scorer") or {}).get("name") or "?",
            "minute": g.get("minute"),
            "prolongation": g.get("injuryTime"),
        })
    buteurs.sort(key=lambda x: x["minute"] or 0)
    return sh, sa, buteurs


# ---------- TheSportsDB ----------
def buts_sdb(texte, equipe):
    out = []
    for part in (texte or "").split(";"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)(?:\+(\d+))?\s*'?\s*:?\s*(.*)$", part)
        if m and m.group(3):
            minute, extra, nom = int(m.group(1)), m.group(2), m.group(3)
        else:
            m = re.match(r"^(.*?)\s+(\d+)(?:\+(\d+))?'?$", part)
            if not m:
                continue
            nom, minute, extra = m.group(1), int(m.group(2)), m.group(3)
        out.append({"equipe": equipe, "joueur": nom.strip() or "?",
                    "minute": minute, "prolongation": int(extra) if extra else None})
    return out


def resultat_sdb_evenement(e, nom_dom, nom_ext):
    sh, sa = e.get("intHomeScore"), e.get("intAwayScore")
    if sh in (None, "") or sa in (None, ""):
        return None
    if (e.get("strStatus") or "").strip().lower() in NON_FINIS:
        return None
    try:
        sh, sa = int(sh), int(sa)
    except ValueError:
        return None
    buteurs = (buts_sdb(e.get("strHomeGoalDetails"), nom_dom)
               + buts_sdb(e.get("strAwayGoalDetails"), nom_ext))
    buteurs.sort(key=lambda x: x["minute"] or 0)
    return sh, sa, buteurs


def resultat_sdb(eid, nom_dom, nom_ext):
    evs = sdb("lookupevent.php", {"id": eid}).get("events") or []
    return resultat_sdb_evenement(evs[0], nom_dom, nom_ext) if evs else None


# ---------- anciens matchs (identifiants API-Football, plus utilisables) ----------
def resultat_ancien(h, cache_fd, cache_sdb):
    jour = h["date"][:10]
    if jour not in cache_fd:
        lendemain = (datetime.fromisoformat(jour) + timedelta(days=1)).strftime("%Y-%m-%d")
        cache_fd[jour] = fd("/matches", {"dateFrom": jour, "dateTo": lendemain}).get("matches", [])
    for m in cache_fd[jour]:
        if m.get("status") != "FINISHED":
            continue
        th, ta = m["homeTeam"], m["awayTeam"]
        if (meme_equipe(th.get("name"), h["domicile"]) or meme_equipe(th.get("shortName"), h["domicile"])) and \
           (meme_equipe(ta.get("name"), h["exterieur"]) or meme_equipe(ta.get("shortName"), h["exterieur"])):
            if appels_fd < MAX_APPELS_FD:
                return resultat_fd(m["id"], h["domicile"], h["exterieur"])
            return "plus_tard"
    if jour not in cache_sdb:
        cache_sdb[jour] = sdb("eventsday.php", {"d": jour, "s": "Soccer"}).get("events") or []
    for e in cache_sdb[jour]:
        if meme_equipe(e.get("strHomeTeam"), h["domicile"]) and meme_equipe(e.get("strAwayTeam"), h["exterieur"]):
            return resultat_sdb_evenement(e, h["domicile"], h["exterieur"])
    return None


def main():
    maintenant = datetime.now(timezone.utc)
    historique = lire(HIST, [])
    cache_fd, cache_sdb = {}, {}

    en_attente = []
    for h in historique:
        if h.get("resultat_reel") is not None or h.get("abandon"):
            continue
        debut = date_match(h)
        if debut is None:
            continue
        delai = timedelta(minutes=115 if h.get("source") == "fd" else 125)
        if maintenant >= debut + delai:
            en_attente.append((debut, h))
    en_attente.sort(key=lambda x: x[0])
    print(len(en_attente), "match(s) en attente de resultat")

    for debut, h in en_attente:
        src = h.get("source")
        if src == "fd":
            if appels_fd >= MAX_APPELS_FD:
                continue
            res = resultat_fd(h["fixture_id"], h["domicile"], h["exterieur"])
        elif src == "sdb":
            res = resultat_sdb(h["fixture_id"], h["domicile"], h["exterieur"])
        else:
            res = resultat_ancien(h, cache_fd, cache_sdb)
            if res == "plus_tard":
                continue
        if res:
            sh, sa, buteurs = res
            h["resultat_reel"] = issue(sh, sa)
            h["score"] = [sh, sa]
            h["buteurs"] = buteurs
        elif maintenant - debut > timedelta(hours=36):
            h["tentatives"] = h.get("tentatives", 0) + 1
            if h["tentatives"] >= 10:
                h["abandon"] = True

    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=1)

    confirmes = [h for h in historique if h.get("resultat_reel") in ("dom", "nul", "ext")]
    bons = 0
    for h in confirmes:
        if ["dom", "nul", "ext"][h["proba"].index(max(h["proba"]))] == h["resultat_reel"]:
            bons += 1
    taux = round(100 * bons / len(confirmes)) if confirmes else None

    data = lire(DATA, {"matchs": []})
    data["historique"] = sorted(confirmes, key=lambda h: h["date"], reverse=True)[:30]
    data["taux_reussite"] = taux
    data["nb_verifies"] = len(confirmes)
    data["maj_resultats"] = maintenant.isoformat()
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("Taux de reussite :", taux, "sur", len(confirmes), "matchs verifies")


main()
