"""Banc d'essai du modele VM_R.

Rejoue notre modele sur des milliers de matchs PASSES (football-data.co.uk, gratuit),
en ne lui donnant a chaque fois que ce qu'on savait AVANT le match. On mesure :
- la justesse du resultat (1X2) et la fiabilite des pourcentages,
- une dizaine de marches (buts, les deux marquent, double chance...),
- l'ecart avec les cotes du marche (reference),
puis on cherche de meilleurs reglages (appris sur les anciennes saisons, verifies sur les
plus recentes, jamais vues pendant l'apprentissage).
Ecrit etalonnage.md (lisible) et etalonnage.json.
"""
import csv
import io
import json
import math
import os
import re
import time
import urllib.request
from collections import defaultdict
from datetime import datetime

os.environ.setdefault("FOOTBALL_DATA_KEY", "x")  # maj.py exige cette variable, ici inutile
_src = re.sub(r"\nmain\(\)\s*$", "\n", open("maj.py", encoding="utf-8").read())
G = {"__name__": "moteur_maj"}
exec(compile(_src, "maj.py", "exec"), G)  # on reutilise EXACTEMENT les fonctions du robot
matrice, lambdas_fd, poisson = G["matrice"], G["lambdas_fd"], G["poisson"]
LAMBDA_DEF, PTS = G["LAMBDA_DEF"], G["PTS"]

LIGUES = {"E0": "Premier League", "E1": "Championship", "SP1": "La Liga", "I1": "Serie A",
          "D1": "Bundesliga", "F1": "Ligue 1", "N1": "Eredivisie", "P1": "Primeira Liga"}
SAISONS = ["2122", "2223", "2324", "2425", "2526", "2627"]
URL = "https://www.football-data.co.uk/mmz4281/{s}/{l}.csv"
DOSSIER_LOCAL = os.environ.get("ETALONNAGE_DOSSIER")  # pour les tests hors ligne
ACTUEL = {"k": 5.0, "forme": 0.008, "h2h": 0.015, "rho": -0.08, "memoire": 0.0, "disp": 1.0}
GRILLES = {"k": [5.0, 8.0, 12.0, 16.0, 24.0, 40.0], "forme": [0.0, 0.008, 0.016, 0.024, 0.032],
           "h2h": [0.0, 0.015, 0.03, 0.045, 0.06, 0.08], "rho": [-0.14, -0.10, -0.06, -0.03, 0.0],
           "memoire": [0.0, 0.25, 0.5, 0.75, 1.0], "disp": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1]}
EPS = 1e-6
GAIN_MINI = 2e-4  # un réglage n'est retenu que s'il améliore nettement l'objectif


# ---------------------------------------------------------------- donnees
def telecharger(saison, ligue):
    if DOSSIER_LOCAL:
        chemin = os.path.join(DOSSIER_LOCAL, f"{saison}_{ligue}.csv")
        return open(chemin, "rb").read() if os.path.exists(chemin) else None
    url = URL.format(s=saison, l=ligue)
    for essai in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read()
        except Exception as e:
            print("  telechargement impossible", url, "->", str(e)[:80])
            time.sleep(3)
    return None


def date_de(txt):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(txt)


def cotes(ligne, jeux):
    """Probabilites implicites normalisees (marge retiree) du premier jeu de colonnes complet."""
    for cols in jeux:
        try:
            vals = [float(ligne[c]) for c in cols]
        except (KeyError, TypeError, ValueError):
            continue
        if all(v > 1.0 for v in vals):
            inv = [1 / v for v in vals]
            s = sum(inv)
            return [x / s for x in inv]
    return None


def lire_csv(octets, ligue, saison):
    try:
        texte = octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = octets.decode("latin-1")
    out = []
    for r in csv.DictReader(io.StringIO(texte)):
        try:
            m = {"d": date_de(r["Date"]), "l": ligue, "s": saison, "h": r["HomeTeam"].strip(),
                 "a": r["AwayTeam"].strip(), "fh": int(r["FTHG"]), "fa": int(r["FTAG"])}
        except (KeyError, TypeError, ValueError):
            continue
        try:
            m["hh"], m["ha"] = int(r["HTHG"]), int(r["HTAG"])
        except (KeyError, TypeError, ValueError):
            m["hh"] = m["ha"] = None
        m["c1x2"] = cotes(r, [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"),
                              ("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A")])
        m["cou"] = cotes(r, [("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5"),
                             ("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")])
        out.append(m)
    return out


# ---------------------------------------------------------------- parcours dans le temps
def nouvel_etat():
    return {"HOME": {}, "AWAY": {}, "TOTAL": {}}


def changer_saison(etat, mem):
    if mem <= 0:
        return nouvel_etat()
    return {t: {k: {"playedGames": r["playedGames"] * mem, "goalsFor": r["goalsFor"] * mem,
                    "goalsAgainst": r["goalsAgainst"] * mem} for k, r in tab.items()}
            for t, tab in etat.items()}


def ajouter(tab, equipe, pour, contre):
    r = tab.setdefault(equipe, {"playedGames": 0, "goalsFor": 0, "goalsAgainst": 0})
    r["playedGames"] += 1
    r["goalsFor"] += pour
    r["goalsAgainst"] += contre


def mettre_a_jour(etat, forme, h2h, m):
    h, a, fh, fa = m["h"], m["a"], m["fh"], m["fa"]
    ajouter(etat["HOME"], h, fh, fa)
    ajouter(etat["AWAY"], a, fa, fh)
    ajouter(etat["TOTAL"], h, fh, fa)
    ajouter(etat["TOTAL"], a, fa, fh)
    forme[h] = (forme[h] + ["V" if fh > fa else ("N" if fh == fa else "D")])[-5:]
    forme[a] = (forme[a] + ["V" if fa > fh else ("N" if fa == fh else "D")])[-5:]
    cle = frozenset((h, a))
    h2h[cle] = (h2h[cle] + [(h, a, "dom" if fh > fa else ("nul" if fh == fa else "ext"))])[-5:]


def predire(m, etat, forme, h2h, P):
    lh, la = lambdas_fd(etat, m["h"], m["a"]) or LAMBDA_DEF
    fh, fa = forme[m["h"]], forme[m["a"]]
    if fh and fa:
        d = sum(PTS[x] for x in fh) - sum(PTS[x] for x in fa)
        lh *= 1 + P["forme"] * d
        la *= 1 - P["forme"] * d
    v_h = v_a = 0
    for (hh, aa, res) in h2h[frozenset((m["h"], m["a"]))]:
        gagnant = hh if res == "dom" else (aa if res == "ext" else None)
        v_h += gagnant == m["h"]
        v_a += gagnant == m["a"]
    lh *= 1 + P["h2h"] * (v_h - v_a)
    la *= 1 - P["h2h"] * (v_h - v_a)
    base_h, base_a = LAMBDA_DEF
    lh = base_h * (lh / base_h) ** P["disp"]  # disp < 1 : on rapproche les prévisions de la moyenne
    la = base_a * (la / base_a) ** P["disp"]
    lh, la = min(3.5, max(0.3, lh)), min(3.5, max(0.3, la))
    return lh, la, matrice(lh, la)


def parcourir(matchs, P, evaluer):
    G["RHO"] = P["rho"]
    k = P["k"]
    G["lisse"] = lambda total, n, moyenne, kk=5: (total + k * moyenne) / (n + k)
    par_ligue = defaultdict(list)
    for m in matchs:
        par_ligue[m["l"]].append(m)
    for liste in par_ligue.values():
        liste.sort(key=lambda m: (m["d"], m["s"]))
        etat, forme, h2h, saison = nouvel_etat(), defaultdict(list), defaultdict(list), None
        i = 0
        while i < len(liste):
            j = i
            while j < len(liste) and liste[j]["d"] == liste[i]["d"]:
                j += 1
            groupe = liste[i:j]
            if groupe[0]["s"] != saison:
                etat, saison = changer_saison(etat, P["memoire"]), groupe[0]["s"]
            for m in groupe:
                evaluer(m, predire(m, etat, forme, h2h, P))
            for m in groupe:
                mettre_a_jour(etat, forme, h2h, m)
            i = j


# ---------------------------------------------------------------- evenements mesures
NOMS = {"O0.5": "Plus de 0,5 but", "O1.5": "Plus de 1,5 but", "O2.5": "Plus de 2,5 buts",
        "O3.5": "Plus de 3,5 buts", "O4.5": "Plus de 4,5 buts", "BTTS": "Les deux équipes marquent",
        "D>0.5": "Domicile marque au moins 1 but", "D>1.5": "Domicile marque 2 buts ou plus",
        "E>0.5": "Extérieur marque au moins 1 but", "E>1.5": "Extérieur marque 2 buts ou plus",
        "1X": "Double chance : domicile ou nul", "12": "Double chance : pas de nul",
        "X2": "Double chance : nul ou extérieur", "D-1.5": "Domicile gagne par 2 buts ou plus",
        "E-1.5": "Extérieur gagne par 2 buts ou plus"}
OBJECTIF = ["1X2", "O1.5", "O2.5", "O3.5", "BTTS"]


def evenements(mat):
    n = len(mat)
    dom = nul = ext = d2h = d2a = btts = 0.0
    tot, hg, ag = [0.0] * (2 * n), [0.0] * n, [0.0] * n
    for i in range(n):
        for j in range(n):
            p = mat[i][j]
            if i > j:
                dom += p
            elif i == j:
                nul += p
            else:
                ext += p
            d2h += p if i - j >= 2 else 0
            d2a += p if j - i >= 2 else 0
            btts += p if i > 0 and j > 0 else 0
            tot[i + j] += p
            hg[i] += p
            ag[j] += p
    ev = {"1X2": [dom, nul, ext], "BTTS": btts, "D-1.5": d2h, "E-1.5": d2a, "1X": dom + nul,
          "12": dom + ext, "X2": nul + ext, "D>0.5": 1 - hg[0], "D>1.5": 1 - hg[0] - hg[1],
          "E>0.5": 1 - ag[0], "E>1.5": 1 - ag[0] - ag[1]}
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        ev["O%.1f" % L] = sum(tot[int(L) + 1:])
    return ev


def verite(m):
    fh, fa, t = m["fh"], m["fa"], m["fh"] + m["fa"]
    v = {"1X2": 0 if fh > fa else (1 if fh == fa else 2), "BTTS": fh > 0 and fa > 0,
         "D-1.5": fh - fa >= 2, "E-1.5": fa - fh >= 2, "1X": fh >= fa, "12": fh != fa, "X2": fh <= fa,
         "D>0.5": fh >= 1, "D>1.5": fh >= 2, "E>0.5": fa >= 1, "E>1.5": fa >= 2}
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        v["O%.1f" % L] = t > L
    return v


def perte(p, y):
    """Perte logarithmique (plus bas = mieux). p : liste (3 issues) ou nombre (oui/non)."""
    if isinstance(p, list):
        return -math.log(max(EPS, p[y]))
    p = min(1 - EPS, max(EPS, p))
    return -math.log(p if y else 1 - p)


def brier(p, y):
    if isinstance(p, list):
        return sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3))
    return (p - (1.0 if y else 0.0)) ** 2


def enregistrements(matchs, P, legers=False):
    out = []

    def ev(m, pred):
        lh, la, mat = pred
        out.append({"m": m, "lh": lh, "la": la, "ev": evenements(mat), "v": verite(m)})
    parcourir(matchs, P, ev)
    return out


def objectif(recs, saisons):
    tot, n = 0.0, 0
    for r in recs:
        if r["m"]["s"] in saisons:
            tot += sum(perte(r["ev"][e], r["v"][e]) for e in OBJECTIF) / len(OBJECTIF)
            n += 1
    return tot / n if n else float("inf")


def f(x, d=1):
    return ("%." + str(d) + "f") % x if x is not None else "n/d"


def pc(x, d=1):
    return (f(100 * x, d) + " %").replace(".", ",") if x is not None else "n/d"


def fr(x, d=3):
    return f(x, d).replace(".", ",")


def evaluer_jeu(recs, saisons, baseline):
    """Metriques par evenement sur un ensemble de saisons."""
    res = {}
    for e in ["1X2"] + [k for k in NOMS]:
        acc = {"n": 0, "mod": 0.0, "bas": 0.0, "mod_b": 0.0, "bas_b": 0.0, "mk": 0.0, "mk_b": 0.0, "n_mk": 0, "mod_mk": 0.0}
        for r in recs:
            if r["m"]["s"] not in saisons:
                continue
            p, y = r["ev"][e], r["v"][e]
            acc["n"] += 1
            acc["mod"] += perte(p, y)
            acc["mod_b"] += brier(p, y)
            acc["bas"] += perte(baseline[e], y)
            acc["bas_b"] += brier(baseline[e], y)
            ref = r["m"]["c1x2"] if e == "1X2" else (None if e != "O2.5" else r["m"]["cou"])
            if ref is not None:
                pm = ref if e == "1X2" else ref[0]
                acc["n_mk"] += 1
                acc["mk"] += perte(pm, y)
                acc["mk_b"] += brier(pm, y)
                acc["mod_mk"] += perte(p, y)
        res[e] = acc
    return res


def frequences_base(recs, saisons):
    c = defaultdict(float)
    n = 0
    for r in recs:
        if r["m"]["s"] in saisons:
            n += 1
            for e, y in r["v"].items():
                if e == "1X2":
                    c[("1X2", y)] += 1
                else:
                    c[e] += 1 if y else 0
    base = {"1X2": [c[("1X2", k)] / n for k in range(3)]}
    for e in NOMS:
        base[e] = c[e] / n
    return base


def calibration(recs, saisons, evt):
    tranches = [(0.0, .40), (.40, .45), (.45, .50), (.50, .55), (.55, .60), (.60, .70), (.70, 1.01)]
    out = []
    for lo, hi in tranches:
        n = ok = 0
        moy = 0.0
        for r in recs:
            if r["m"]["s"] not in saisons:
                continue
            if evt == "1X2":
                p = max(r["ev"]["1X2"])
                hit = r["ev"]["1X2"].index(p) == r["v"]["1X2"]
            else:
                p, hit = r["ev"][evt], bool(r["v"][evt])
                if p < 0.5:  # on regarde toujours l'issue la plus probable
                    p, hit = 1 - p, not hit
            if lo <= p < hi:
                n += 1
                ok += hit
                moy += p
        if n:
            out.append((lo, hi, n, moy / n, ok / n))
    return out


def justesse(recs, saisons):
    n = bon = bon_mk = n_mk = bon_dom = 0
    for r in recs:
        if r["m"]["s"] not in saisons:
            continue
        n += 1
        p = r["ev"]["1X2"]
        y = r["v"]["1X2"]
        bon += p.index(max(p)) == y
        bon_dom += y == 0
        c = r["m"]["c1x2"]
        if c:
            n_mk += 1
            bon_mk += c.index(max(c)) == y
    return {"n": n, "modele": bon / n if n else None, "marche": bon_mk / n_mk if n_mk else None,
            "domicile": bon_dom / n if n else None, "n_marche": n_mk}


def mi_temps(recs, saisons):
    """Mesure la part reelle des buts en 1re mi-temps et choisit la meilleure part pour le modele."""
    lignes = [r for r in recs if r["m"]["s"] in saisons and r["m"]["hh"] is not None]
    if not lignes:
        return None
    buts_mt = sum(r["m"]["hh"] + r["m"]["ha"] for r in lignes)
    buts = sum(r["m"]["fh"] + r["m"]["fa"] for r in lignes)
    essais = {}
    for part in (0.40, 0.42, 0.44, 0.46, 0.48, 0.50):
        tot, n = 0.0, 0
        for r in lignes:
            mu1 = part * (r["lh"] + r["la"])
            hh, ha = r["m"]["hh"], r["m"]["ha"]
            p1 = [poisson(a, part * r["lh"]) * poisson(b, part * r["la"]) for a in range(9) for b in range(9)]
            dom = sum(p1[a * 9 + b] for a in range(9) for b in range(9) if a > b)
            nul = sum(p1[a * 9 + b] for a in range(9) for b in range(9) if a == b)
            ext = max(EPS, 1 - dom - nul)
            y = 0 if hh > ha else (1 if hh == ha else 2)
            tot += perte([dom, nul, ext], y)
            tot += perte(1 - math.exp(-mu1), hh + ha >= 1) + perte(1 - math.exp(-mu1) * (1 + mu1), hh + ha >= 2)
            n += 1
        essais[part] = tot / n / 3
    return {"part_reelle": buts_mt / buts, "n": len(lignes), "essais": essais,
            "meilleure": min(essais, key=essais.get)}


# ---------------------------------------------------------------- reglages
def optimiser(matchs, saisons_app, depart, fixes=()):
    P = dict(depart)
    histo = []
    meilleur = objectif(enregistrements(matchs, P), saisons_app)
    histo.append(("départ", dict(P), meilleur))
    print("  objectif de depart :", round(meilleur, 5))
    for tour in range(2):
        modifie = False
        for nom, valeurs in GRILLES.items():
            if nom in fixes:
                continue
            for v in valeurs:
                if v == P[nom]:
                    continue
                Q = dict(P)
                Q[nom] = v
                score = objectif(enregistrements(matchs, Q), saisons_app)
                if score < meilleur - GAIN_MINI:
                    meilleur, P, modifie = score, Q, True
                    histo.append((f"{nom} = {v}", dict(P), meilleur))
                    print("  amelioration :", nom, "=", v, "->", round(meilleur, 5))
        if not modifie:
            break
    return P, histo


def main():
    t0 = time.time()
    matchs, dispo = [], []
    for s in SAISONS:
        n_s = 0
        for lg in LIGUES:
            octets = telecharger(s, lg)
            time.sleep(0.4)
            if octets:
                lus = lire_csv(octets, lg, s)
                matchs += lus
                n_s += len(lus)
        print("saison", s, ":", n_s, "matchs")
        if n_s:
            dispo.append(s)
    if len(dispo) < 2 or len(matchs) < 500:
        raise SystemExit("Pas assez de donnees telechargees pour un banc d'essai fiable.")
    app, test = (dispo[:-2], dispo[-2:]) if len(dispo) >= 4 else (dispo[:-1], dispo[-1:])
    print("apprentissage :", app, "| test (jamais vu) :", test)

    print("1) modele actuel")
    recs_a = enregistrements(matchs, ACTUEL)
    base = frequences_base(recs_a, app)
    print("2) reglages SANS memoire (applicables tout de suite au robot)")
    P_sans, h_sans = optimiser(matchs, app, ACTUEL, fixes=("memoire",))
    print("3) reglages AVEC memoire de la saison precedente")
    P_avec, h_avec = optimiser(matchs, app, P_sans)
    print("4) mesures finales")
    recs_s = enregistrements(matchs, P_sans) if P_sans != ACTUEL else recs_a
    recs_m = enregistrements(matchs, P_avec) if P_avec != P_sans else recs_s
    jeux = {}
    for nom, recs in (("actuel", recs_a), ("sans", recs_s), ("avec", recs_m)):
        jeux[nom] = {"test": evaluer_jeu(recs, test, base), "just": justesse(recs, test),
                     "cal": calibration(recs, test, "1X2")}
    print("5) effet de chaque changement, pris isolement, sur les matchs jamais vus")
    obj_actuel = objectif(recs_a, test)
    isole = []
    for nom in GRILLES:
        if P_sans[nom] != ACTUEL[nom]:
            Q = dict(ACTUEL)
            Q[nom] = P_sans[nom]
            isole.append((nom, ACTUEL[nom], P_sans[nom], objectif(enregistrements(matchs, Q), test) - obj_actuel))
    if P_avec["memoire"] != ACTUEL["memoire"]:
        Q = dict(ACTUEL)
        Q["memoire"] = P_avec["memoire"]
        isole.append(("memoire", ACTUEL["memoire"], P_avec["memoire"], objectif(enregistrements(matchs, Q), test) - obj_actuel))
    mt = mi_temps(recs_s, test)
    out = {"saisons_apprentissage": app, "saisons_test": test, "reglages_actuels": ACTUEL, "reglages_sans": P_sans,
           "reglages_avec": P_avec, "nb_matchs": len(matchs), "nb_ligues": len({m["l"] for m in matchs})}
    ecrire_rapport(out, jeux, isole, (h_sans, h_avec), mt, time.time() - t0)


NOMS_REGLAGES = {"k": "Poids du passé du classement (lissage)", "forme": "Poids de la forme récente",
                 "h2h": "Poids des confrontations directes", "rho": "Correction des petits scores (nuls)",
                 "memoire": "Mémoire de la saison précédente", "disp": "Prudence des pourcentages (1 = aucune)"}


def niveau(prog):
    return "Bonne" if prog >= 0.07 else ("Moyenne" if prog >= 0.03 else "Faible")


def ecrire_rapport(out, jeux, isole, histos, mt, duree):
    A, S, M = jeux["actuel"], jeux["sans"], jeux["avec"]
    nt = A["test"]["1X2"]["n"]
    L = ["# Banc d'essai du modèle VM_R (version 2)", "",
         f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')} · {out['nb_matchs']} matchs passés · "
         f"{out['nb_ligues']} championnats · durée {int(duree)} s", "",
         f"Réglage sur les saisons **{', '.join(out['saisons_apprentissage'])}**, jugement sur "
         f"**{', '.join(out['saisons_test'])}** ({nt} matchs jamais vus pendant le réglage). "
         "Pour chaque match, le modèle ne reçoit que ce qu'on savait avant le coup d'envoi.", "",
         "« Sans mémoire » = réglages applicables tout de suite au robot. « Avec mémoire » = en plus, on tient compte de la saison précédente (à brancher plus tard).", ""]
    L += ["## 1. Résultat du match (1X2) — matchs jamais vus", "",
          "| | Actuel | Réglé sans mémoire | Réglé avec mémoire | Cotes du marché | Toujours « domicile » |", "|---|---|---|---|---|---|",
          f"| Bon résultat trouvé | {pc(A['just']['modele'])} | {pc(S['just']['modele'])} | {pc(M['just']['modele'])} | {pc(A['just']['marche'])} | {pc(A['just']['domicile'])} |", ""]
    e = {k: J["test"]["1X2"] for k, J in jeux.items()}
    L += ["Perte logarithmique du 1X2 (plus bas = mieux ; mesure la qualité des pourcentages) :", "",
          f"- hasard moyen : **{fr(e['actuel']['bas'] / e['actuel']['n'])}**",
          f"- modèle actuel : **{fr(e['actuel']['mod'] / e['actuel']['n'])}**",
          f"- réglé sans mémoire : **{fr(e['sans']['mod'] / e['sans']['n'])}**",
          f"- réglé avec mémoire : **{fr(e['avec']['mod'] / e['avec']['n'])}**"]
    if e["actuel"]["n_mk"]:
        L.append(f"- cotes du marché : **{fr(e['actuel']['mk'] / e['actuel']['n_mk'])}**")
    L += ["", "## 2. Fiabilité des pourcentages (1X2, réglé sans mémoire)", "",
          "Quand le modèle annonce une probabilité pour sa meilleure issue, combien de fois ça arrive vraiment ?", "",
          "| Annoncé | Matchs | Annoncé en moyenne | Réellement arrivé |", "|---|---|---|---|"]
    for lo, hi, n, moy, ok in S["cal"]:
        L.append(f"| {int(lo * 100)}–{min(100, int(hi * 100))} % | {n} | {pc(moy)} | {pc(ok)} |")
    L += ["", "## 3. Autres marchés — réglé sans mémoire, matchs jamais vus", "",
          "Progrès = amélioration de la perte logarithmique par rapport à la fréquence moyenne. Fiabilité : Bonne ≥ 7 %, Moyenne 3–7 %, Faible < 3 %.", "",
          "| Marché | Matchs | Progrès | Fiabilité | Écart avec le marché |", "|---|---|---|---|---|"]
    for ev, nom in NOMS.items():
        r = S["test"][ev]
        prog = 1 - r["mod"] / r["bas"] if r["bas"] else 0
        ecart = f"modèle {fr(r['mod_mk'] / r['n_mk'])} · marché {fr(r['mk'] / r['n_mk'])}" if (ev == "O2.5" and r["n_mk"]) else ""
        L.append(f"| {nom} | {r['n']} | {pc(prog)} | {niveau(prog)} | {ecart} |")
    L += ["", "## 4. Réglages", "", "| | Actuel | Sans mémoire | Avec mémoire |", "|---|---|---|---|"]
    for k, nom in NOMS_REGLAGES.items():
        L.append(f"| {nom} | {out['reglages_actuels'][k]} | {out['reglages_sans'][k]} | {out['reglages_avec'][k]} |")
    L += ["", "Valeurs testées pour chaque réglage : " + " ; ".join(f"{NOMS_REGLAGES[k].split(' (')[0]} {v}" for k, v in GRILLES.items()) + ".", ""]
    L += ["## 5. Effet de chaque changement, pris isolément, sur les matchs jamais vus", "",
          "Variation de l'objectif (plus bas = mieux ; un écart inférieur à 0,0005 est dans le bruit).", "",
          "| Réglage | Avant → après | Effet |", "|---|---|---|"]
    for nom, av, ap, delta in isole:
        verdict = "mieux" if delta < -5e-4 else ("pire" if delta > 5e-4 else "neutre")
        L.append(f"| {NOMS_REGLAGES[nom]} | {av} → {ap} | {('+' if delta > 0 else '')}{fr(delta, 4)} ({verdict}) |")
    ta, ts, tm = (objectif_moyen(J["test"]) for J in (A, S, M))
    L += ["", f"Objectif global sur les matchs jamais vus : actuel {fr(ta, 5)} · sans mémoire {fr(ts, 5)} · avec mémoire {fr(tm, 5)}.", ""]
    if mt:
        L += ["## 6. Mi-temps", "",
              f"Part réelle des buts marqués en 1re mi-temps : **{pc(mt['part_reelle'])}** (notre modèle suppose 45 %, {mt['n']} matchs). "
              f"Meilleure valeur testée : **{int(mt['meilleure'] * 100)} %**."]
    open("etalonnage.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
    out["resume"] = {"objectif_test": {"actuel": ta, "sans": ts, "avec": tm}, "isole": isole, "mi_temps": mt,
                     "justesse": {k: J["just"] for k, J in jeux.items()}}
    json.dump(out, open("etalonnage.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n".join(L[:30]))


def objectif_moyen(res):
    return sum(res[e]["mod"] / res[e]["n"] for e in OBJECTIF) / len(OBJECTIF)


main()
