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
from math import exp, factorial

import requests

from moteur import tous_les_marches  # marches et verification apres match (fichier moteur.py)

CLE_FD = os.environ["FOOTBALL_DATA_KEY"]
FD = "https://api.football-data.org/v4"
SDB = "https://www.thesportsdb.com/api/v1/json/123"  # cle publique de test
CODES = ["CL", "PL", "PD", "SA", "BL1", "FL1"]
GRANDES_LIGUES = {
    "uefachampionsleague", "englishpremierleague", "spanishlaliga",
    "italianseriea", "germanbundesliga", "frenchligue1",
}
MAX_GRANDES = 10
MAX_PETITES = 7
MAX_CANDIDATS = 25
PTS = {"V": 3, "N": 1, "D": 0}
MAXB = 10              # on calcule les scores de 0 a 10 buts par equipe
RHO = -0.08            # correction Dixon-Coles (un peu plus de 0-0 et de 1-1)
MOY_EQUIPE = 1.35      # buts par equipe et par match par defaut
K_LISSAGE = 16.0       # banc d'essai : poids du passe du classement (avant : 5)
K_PETITS = 5.0         # petits matchs : on n'a que 5 matchs de forme
DISP = 0.8             # banc d'essai : prudence, on rapproche les previsions de la moyenne
MEMOIRE = 0.5          # banc d'essai : la saison precedente compte comme une demi-saison
LAMBDA_DEF = (1.485, 1.215)  # buts attendus par defaut (domicile, exterieur)
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


def lire_tableaux(data):
    tabs = {"TOTAL": {}, "HOME": {}, "AWAY": {}}
    for bloc in data.get("standings", []):
        t = bloc.get("type")
        if t not in tabs:
            continue
        for ligne in bloc.get("table", []):
            if ligne.get("playedGames"):
                tabs[t][ligne["team"]["id"]] = dict(ligne)
    return tabs


def charger_classements(codes):
    """Classements TOTAL / HOME / AWAY de chaque competition (+ saison precedente, si disponible)."""
    out = {}
    for code in sorted(codes):
        data = fd(f"/competitions/{code}/standings")
        tabs = lire_tableaux(data)
        annee = ((data.get("season") or {}).get("startDate") or "")[:4]
        if MEMOIRE > 0 and code != "CL" and annee.isdigit():
            ancien = lire_tableaux(fd(f"/competitions/{code}/standings", {"season": int(annee) - 1}))
            n = 0
            for typ, tab in ancien.items():
                for tid, r in tab.items():
                    ligne = tabs[typ].setdefault(tid, {"team": {"id": tid}, "playedGames": 0,
                                                       "goalsFor": 0, "goalsAgainst": 0})
                    for cle in ("playedGames", "goalsFor", "goalsAgainst"):
                        ligne[cle] = (ligne.get(cle) or 0) + MEMOIRE * (r.get(cle) or 0)
                    n += 1
            print("Saison precedente", code, ":", ("ajoutee (%d lignes)" % n) if n else "indisponible")
        out[code] = tabs
    return out


# ---------- petits matchs (TheSportsDB) ----------
def forme_sdb(tid):
    """Renvoie (lettres V/N/D, liste de (buts pour, buts contre)) des 5 derniers matchs."""
    data = sdb("eventslast.php", {"id": tid})
    evs = data.get("results") or data.get("events") or []
    evs = sorted(evs, key=lambda e: e.get("dateEvent") or "")[-5:]
    lettres, buts = [], []
    for e in evs:
        try:
            hs, as_ = int(e["intHomeScore"]), int(e["intAwayScore"])
        except (KeyError, TypeError, ValueError):
            continue
        est_dom = str(e.get("idHomeTeam")) == str(tid)
        pour, contre = (hs, as_) if est_dom else (as_, hs)
        lettres.append("V" if pour > contre else ("D" if pour < contre else "N"))
        buts.append((pour, contre))
    return lettres, buts


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


# ---------- moteur : buts attendus -> matrice des scores -> tous les marches ----------
def poisson(k, lam):
    return exp(-lam) * lam ** k / factorial(k)


def matrice(lh, la):
    """Probabilite de chaque score (buts domicile i, buts exterieur j), 0 a MAXB."""
    m = [[poisson(i, lh) * poisson(j, la) for j in range(MAXB + 1)] for i in range(MAXB + 1)]
    m[0][0] *= max(0.0, 1 - lh * la * RHO)
    m[0][1] *= max(0.0, 1 + lh * RHO)
    m[1][0] *= max(0.0, 1 + la * RHO)
    m[1][1] *= max(0.0, 1 - RHO)
    tot = sum(sum(r) for r in m)
    return [[x / tot for x in r] for r in m]


def somme(m, f):
    return sum(m[i][j] for i in range(MAXB + 1) for j in range(MAXB + 1) if f(i, j))


def lisse(total, n, moyenne, k=K_LISSAGE):
    """Ramene vers la moyenne quand on a peu de matchs."""
    return (total + k * moyenne) / (n + k)


def moyenne_tableau(tab):
    pg = sum(r["playedGames"] for r in tab.values())
    return sum(r["goalsFor"] for r in tab.values()) / pg if pg else None


def lambdas_fd(cl, hid, aid):
    """Buts attendus (domicile, exterieur) a partir des classements de la competition."""
    if not cl:
        return None
    H, A, T = cl.get("HOME") or {}, cl.get("AWAY") or {}, cl.get("TOTAL") or {}
    if hid in H and aid in A and moyenne_tableau(H) and moyenne_tableau(A):
        mh, ma = moyenne_tableau(H), moyenne_tableau(A)
        ah = lisse(H[hid]["goalsFor"], H[hid]["playedGames"], mh)
        dh = lisse(H[hid]["goalsAgainst"], H[hid]["playedGames"], ma)
        aa = lisse(A[aid]["goalsFor"], A[aid]["playedGames"], ma)
        da = lisse(A[aid]["goalsAgainst"], A[aid]["playedGames"], mh)
        return ah * da / mh, aa * dh / ma
    if hid in T and aid in T and moyenne_tableau(T):
        moy = moyenne_tableau(T)
        ah = lisse(T[hid]["goalsFor"], T[hid]["playedGames"], moy)
        dh = lisse(T[hid]["goalsAgainst"], T[hid]["playedGames"], moy)
        aa = lisse(T[aid]["goalsFor"], T[aid]["playedGames"], moy)
        da = lisse(T[aid]["goalsAgainst"], T[aid]["playedGames"], moy)
        return ah * da / moy * 1.10, aa * dh / moy * 0.90
    return None


def lambdas_sdb(buts_h, buts_a):
    """Buts attendus a partir des buts des 5 derniers matchs de chaque equipe."""
    def stats(liste):
        return len(liste), sum(x[0] for x in liste), sum(x[1] for x in liste)
    nh, gfh, gah = stats(buts_h)
    na, gfa, gaa = stats(buts_a)
    ah, dh = lisse(gfh, nh, MOY_EQUIPE, K_PETITS), lisse(gah, nh, MOY_EQUIPE, K_PETITS)
    aa, da = lisse(gfa, na, MOY_EQUIPE, K_PETITS), lisse(gaa, na, MOY_EQUIPE, K_PETITS)
    return ah * da / MOY_EQUIPE * 1.10, aa * dh / MOY_EQUIPE * 0.90


def disperser(lh, la):
    """Prudence : le banc d'essai montrait des pourcentages trop confiants, on les rapproche de la moyenne."""
    return (LAMBDA_DEF[0] * (lh / LAMBDA_DEF[0]) ** DISP, LAMBDA_DEF[1] * (la / LAMBDA_DEF[1]) ** DISP)


def ajuster(lh, la, forme_h, forme_a, v_h, v_a, avec_forme):
    """Petits ajustements : forme recente et confrontations directes."""
    if avec_forme and forme_h and forme_a:
        d = sum(PTS[x] for x in forme_h) - sum(PTS[x] for x in forme_a)
        lh *= 1 + 0.008 * d
        la *= 1 - 0.008 * d
    d2 = v_h - v_a
    lh *= 1 + 0.015 * d2
    la *= 1 - 0.015 * d2
    lh, la = disperser(lh, la)
    return min(3.5, max(0.3, lh)), min(3.5, max(0.3, la))


def p1x2(m):
    return (somme(m, lambda i, j: i > j), somme(m, lambda i, j: i == j),
            somme(m, lambda i, j: i < j))


def prevoir(lh0, la0, forme_h, forme_a, v_h, v_a, avec_forme):
    m0 = matrice(*disperser(lh0, la0))
    base = p1x2(m0)
    lh, la = ajuster(lh0, la0, forme_h, forme_a, v_h, v_a, avec_forme)
    m = matrice(lh, la)
    dom, nul, ext = p1x2(m)
    proba = [round(100 * dom), 0, round(100 * ext)]
    proba[1] = 100 - proba[0] - proba[2]
    base_pct = [round(100 * base[0]), 0, round(100 * base[2])]
    base_pct[1] = 100 - base_pct[0] - base_pct[2]
    return {"proba": proba, "base": base_pct, "ajust": proba[0] - base_pct[0],
            "lh": round(lh, 3), "la": round(la, 3), "marches": tous_les_marches(m, lh, la)}


def fiche(categorie, competition, heure, dom, ext, prev, forme_h, forme_a, src_h, src_a, v_h, nuls, v_a):
    return {
        "categorie": categorie,
        "competition": competition,
        "heure": heure,
        "domicile": dom,
        "exterieur": ext,
        "proba": prev["proba"],
        "base_api": prev["base"],
        "ajustement": prev["ajust"],
        "buts_attendus": [round(prev["lh"], 2), round(prev["la"], 2)],
        "forme_dom": forme_h,
        "forme_ext": forme_a,
        "source_dom": src_h,
        "source_ext": src_a,
        "face_a_face": {"dom": v_h, "nuls": nuls, "ext": v_a},
        "absents": [],
        "marches": prev["marches"],
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
    classements = charger_classements({m["competition"]["code"] for m in grands}) if grands else {}

    for m in grands:
        h, a = m["homeTeam"], m["awayTeam"]
        nom_h = h.get("shortName") or h["name"]
        nom_a = a.get("shortName") or a["name"]
        forme_h, forme_a = forme_fd(h["id"]), forme_fd(a["id"])
        v_h, nuls, v_a = face_fd(m["id"], h["id"], a["id"])
        lh0, la0 = lambdas_fd(classements.get(m["competition"]["code"]), h["id"], a["id"]) or LAMBDA_DEF
        prev = prevoir(lh0, la0, forme_h, forme_a, v_h, v_a, True)
        sortie.append(fiche("principal", m["competition"]["name"], m["utcDate"], nom_h, nom_a, prev,
                            forme_h, forme_a,
                            "actuelle" if forme_h else "", "actuelle" if forme_a else "",
                            v_h, nuls, v_a))
        a_enregistrer.append({"source": "fd", "fixture_id": m["id"], "date": m["utcDate"],
                              "competition": m["competition"]["name"],
                              "domicile": nom_h, "exterieur": nom_a, "proba": prev["proba"],
                              "lh": prev["lh"], "la": prev["la"]})

    # 2) Petits matchs
    petites = 0
    candidats = candidats_sdb(jour, maintenant)
    print("TheSportsDB :", len(candidats), "matchs candidats")
    for ts, e in candidats[:MAX_CANDIDATS]:
        if petites >= MAX_PETITES:
            break
        forme_h, buts_h = forme_sdb(e["idHomeTeam"])
        forme_a, buts_a = forme_sdb(e["idAwayTeam"])
        if not forme_h and not forme_a:
            continue  # aucune donnee sur les deux equipes : on saute ce match
        lh0, la0 = lambdas_sdb(buts_h, buts_a)
        prev = prevoir(lh0, la0, forme_h, forme_a, 0, 0, False)
        sortie.append(fiche("secondaire", e.get("strLeague") or "Autre compétition", ts,
                            e["strHomeTeam"], e["strAwayTeam"], prev, forme_h, forme_a,
                            "actuelle" if forme_h else "", "actuelle" if forme_a else "",
                            0, 0, 0))
        a_enregistrer.append({"source": "sdb", "fixture_id": str(e["idEvent"]), "date": ts,
                              "competition": e.get("strLeague") or "",
                              "domicile": e["strHomeTeam"], "exterieur": e["strAwayTeam"],
                              "proba": prev["proba"], "lh": prev["lh"], "la": prev["la"]})
        petites += 1

    # 3) Historique : ajout sans doublon
    connus = {(h.get("source", "af"), str(h["fixture_id"])): h for h in historique}
    for n in a_enregistrer:
        cle = (n["source"], str(n["fixture_id"]))
        if cle in connus:
            if connus[cle].get("resultat_reel") is None:
                connus[cle]["proba"] = n["proba"]
                connus[cle]["lh"], connus[cle]["la"] = n["lh"], n["la"]
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
    if anciennes_donnees.get("stats_marches"):
        data["stats_marches"] = anciennes_donnees["stats_marches"]

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(HIST, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(h, ensure_ascii=False, separators=(",", ":")) for h in historique) + "\n]\n")

    print(len(grands), "grands matchs,", petites, "petits matchs,",
          len(confirmes), "verifies, taux :", taux)


main()
