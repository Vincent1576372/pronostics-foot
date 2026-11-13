"""Moteur de marches VM_R, partage par le robot du matin (maj.py) et le verificateur (verifier.py).

- marches_verifiables : pour un match, tous les marches avec, pour chaque issue,
  son pourcentage ET une fonction qui dit, apres le match, si l'issue s'est produite.
- tous_les_marches    : meme chose sans les fonctions (format du site, data.json).
- bilan               : verification apres le match, sous forme compacte.
Attention : matrice() doit rester identique a celle de maj.py (meme RHO).
"""
from math import comb, exp, factorial

MAXB = 10
RHO = -0.08
PART_MT1 = 0.45  # part des buts marques en 1re mi-temps (le banc d'essai a mesure 44 %)
PROFIL_15MIN = [0.14, 0.15, 0.16, 0.17, 0.18, 0.20]  # buts par tranche de 15 minutes


def poisson(k, lam):
    return exp(-lam) * lam ** k / factorial(k)


def matrice(lh, la):
    m = [[poisson(i, lh) * poisson(j, la) for j in range(MAXB + 1)] for i in range(MAXB + 1)]
    m[0][0] *= max(0.0, 1 - lh * la * RHO)
    m[0][1] *= max(0.0, 1 + lh * RHO)
    m[1][0] *= max(0.0, 1 + la * RHO)
    m[1][1] *= max(0.0, 1 - RHO)
    tot = sum(sum(r) for r in m)
    return [[x / tot for x in r] for r in m]


def somme(m, f):
    return sum(m[i][j] for i in range(MAXB + 1) for j in range(MAXB + 1) if f(i, j))


def p1x2(m):
    return (somme(m, lambda i, j: i > j), somme(m, lambda i, j: i == j), somme(m, lambda i, j: i < j))


def pct(p):
    return round(100 * max(0.0, min(1.0, p)), 1)


def fiabilite(nom):
    """Niveau mesure par le banc d'essai (3 802 matchs jamais vus). None = marche pas encore mesure."""
    if nom.startswith("Total de buts (") or nom == "Les deux équipes marquent":
        return "Faible"
    if nom == "Double chance" or nom.startswith("Total Domicile") or nom.startswith("Total Extérieur"):
        return "Moyenne"
    return None


def sans_remontee(i, j, cache={}):
    """Parcours possibles ou l'equipe de gauche n'est jamais menee (pour 'revient au score')."""
    if not cache:
        n = MAXB + 1
        t = [[0] * n for _ in range(n)]
        for a in range(n):
            for b in range(n):
                if a < b:
                    continue
                if a == 0 and b == 0:
                    t[a][b] = 1
                else:
                    t[a][b] = (t[a - 1][b] if a >= 1 else 0) + (t[a][b - 1] if b >= 1 else 0)
        cache["t"] = t
    return cache["t"][i][j]


def jointe_mt_fin(principal, mu1h, mu1a, mu2h, mu2a):
    """Probabilite (resultat mi-temps, resultat final), 0=dom 1=nul 2=ext, calee sur le modele principal."""
    N = 9
    p1 = [[poisson(a, mu1h) * poisson(b, mu1a) for b in range(N)] for a in range(N)]
    p2 = [[poisson(c, mu2h) * poisson(d, mu2a) for d in range(N)] for c in range(N)]
    J = [[0.0] * 3 for _ in range(3)]
    ht = [0.0] * 3
    for a in range(N):
        for b in range(N):
            r1 = 0 if a > b else (1 if a == b else 2)
            ht[r1] += p1[a][b]
            for c in range(N):
                for d in range(N):
                    fa, fb = a + c, b + d
                    r2 = 0 if fa > fb else (1 if fa == fb else 2)
                    J[r1][r2] += p1[a][b] * p2[c][d]
    tot_ht = sum(ht)
    ht = [x / tot_ht for x in ht]
    for _ in range(30):
        for r1 in range(3):
            s_ = sum(J[r1])
            if s_ > 0:
                J[r1] = [x * ht[r1] / s_ for x in J[r1]]
        for r2 in range(3):
            s_ = sum(J[r1][r2] for r1 in range(3))
            if s_ > 0:
                for r1 in range(3):
                    J[r1][r2] *= principal[r2] / s_
    return J, ht


# ---------------------------------------------------------------- verites apres le match
# Le « contexte » c d'un match termine : fh, fa (score final), hh, ha (score a la mi-temps ou None),
# buts (liste de (cote "D"/"E", minute, minutes de temps additionnel) ou None si on ne connait pas les buteurs).
def sequence(c):
    """Cotes des buts dans l'ordre (liste), [] si 0-0, None si les buts ne sont pas tous connus."""
    total = c["fh"] + c["fa"]
    if total == 0:
        return []
    b = c.get("buts")
    if not b or len(b) != total:
        return None
    return [x[0] for x in sorted(b, key=lambda x: x[1] + (x[2] or 0) / 100.0)]


def premier(c):
    s = sequence(c)
    return None if s is None else (s[0] if s else "-")


def dernier(c):
    s = sequence(c)
    return None if s is None else (s[-1] if s else "-")


def revient(c, cote):
    """Vrai si l'equipe `cote` gagne apres avoir ete menee a un moment."""
    gagnant = "D" if c["fh"] > c["fa"] else ("E" if c["fa"] > c["fh"] else None)
    if gagnant != cote:
        return False
    s = sequence(c)
    if s is None:
        return None
    d = pire = 0
    for x in s:
        d += 1 if x == cote else -1
        pire = min(pire, d)
    return pire < 0


def moitie(c):
    """Score a la mi-temps (hh, ha), reconstitue depuis les buts si besoin ; None si inconnu."""
    if c.get("hh") is not None and c.get("ha") is not None:
        return c["hh"], c["ha"]
    total = c["fh"] + c["fa"]
    if total == 0:
        return 0, 0
    b = c.get("buts")
    if not b or len(b) != total:
        return None
    return (sum(1 for s, mn, _ in b if s == "D" and mn <= 45), sum(1 for s, mn, _ in b if s == "E" and mn <= 45))


def minute_premier_but(c):
    s = c.get("buts")
    total = c["fh"] + c["fa"]
    if total == 0 or not s or len(s) != total:
        return None
    x = sorted(s, key=lambda x: x[1] + (x[2] or 0) / 100.0)[0]
    return x[1]


def _egal(a, b):
    return None if a is None else a == b


def _ht(c, f):
    h = moitie(c)
    return None if h is None else f(h[0], h[1])


def _op(v, f):
    return None if v is None else f(v)


def _res(a, b):
    return 0 if a > b else (1 if a == b else 2)


# ---------------------------------------------------------------- les marches
def marches_verifiables(m, lh, la):
    out = []

    def ajouter(groupe, nom, issues, approx=False):
        out.append({"groupe": groupe, "nom": nom, "approx": approx, "fiab": fiabilite(nom), "issues": issues})

    P = lambda f: somme(m, f)
    sc = lambda f: (P(f), lambda c: f(c["fh"], c["fa"]))  # issue fondee sur le score final
    dom, nul, ext = p1x2(m)
    R, B, C, S, D, T = "Résultat", "Buts", "Combinés", "Score exact", "Déroulement", "Mi-temps"

    # ----- Résultat -----
    ajouter(R, "Résultat du match (1X2)", [("Domicile", *sc(lambda i, j: i > j)), ("Nul", *sc(lambda i, j: i == j)),
                                           ("Extérieur", *sc(lambda i, j: i < j))])
    ajouter(R, "Double chance", [("Domicile ou nul", *sc(lambda i, j: i >= j)),
                                 ("Domicile ou extérieur", *sc(lambda i, j: i != j)),
                                 ("Nul ou extérieur", *sc(lambda i, j: i <= j))])
    ajouter(R, "Remboursé si match nul", [
        ("Domicile", dom / (dom + ext), lambda c: None if c["fh"] == c["fa"] else c["fh"] > c["fa"]),
        ("Extérieur", ext / (dom + ext), lambda c: None if c["fh"] == c["fa"] else c["fa"] > c["fh"])])
    iss = [("Domicile par %d but%s" % (k, "s" if k > 1 else ""), *sc(lambda i, j, k=k: i - j == k)) for k in (1, 2, 3)]
    iss.append(("Domicile par 4 buts ou plus", *sc(lambda i, j: i - j >= 4)))
    iss.append(("Nul", *sc(lambda i, j: i == j)))
    iss += [("Extérieur par %d but%s" % (k, "s" if k > 1 else ""), *sc(lambda i, j, k=k: j - i == k)) for k in (1, 2, 3)]
    iss.append(("Extérieur par 4 buts ou plus", *sc(lambda i, j: j - i >= 4)))
    ajouter(R, "Va gagner par", iss)
    ajouter(R, "Victoire sans encaisser de but", [("Domicile", *sc(lambda i, j: i > j and j == 0)),
                                                  ("Extérieur", *sc(lambda i, j: j > i and i == 0))])
    ajouter(R, "N'encaisse pas de but", [("Domicile n'encaisse pas", *sc(lambda i, j: j == 0)),
                                        ("Extérieur n'encaisse pas", *sc(lambda i, j: i == 0))])
    sg = lambda x: ("+%d" % x) if x > 0 else ("%d" % x)
    for h in (-2, -1, 1, 2):
        ajouter(R, "Handicap européen Domicile (%s)" % sg(h),
                [("Domicile (%s)" % sg(h), *sc(lambda i, j, h=h: i + h > j)),
                 ("Nul (%s)" % sg(h), *sc(lambda i, j, h=h: i + h == j)),
                 ("Extérieur (%s)" % sg(-h), *sc(lambda i, j, h=h: i + h < j))])
    for h in (-1.5, -0.5, 0.5, 1.5):
        ajouter(R, "Handicap asiatique Domicile (%+.1f)" % h,
                [("Domicile (%+.1f)" % h, *sc(lambda i, j, h=h: i + h > j)),
                 ("Extérieur (%+.1f)" % -h, *sc(lambda i, j, h=h: i + h < j))])

    # ----- Buts -----
    for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        ajouter(B, "Total de buts (%.1f)" % L, [("Plus de %.1f" % L, *sc(lambda i, j, L=L: i + j > L)),
                                                 ("Moins de %.1f" % L, *sc(lambda i, j, L=L: i + j < L))])
    for nom, idx in (("Domicile", 0), ("Extérieur", 1)):
        for L in (0.5, 1.5, 2.5):
            ajouter(B, "Total %s (%.1f)" % (nom, L),
                    [("Plus de %.1f" % L, *sc(lambda i, j, L=L, idx=idx: (i if idx == 0 else j) > L)),
                     ("Moins de %.1f" % L, *sc(lambda i, j, L=L, idx=idx: (i if idx == 0 else j) < L))])
    ajouter(B, "Les deux équipes marquent", [("Oui", *sc(lambda i, j: i > 0 and j > 0)),
                                             ("Non", *sc(lambda i, j: not (i > 0 and j > 0)))])
    ajouter(B, "Total de buts pair / impair", [("Pair", *sc(lambda i, j: (i + j) % 2 == 0)),
                                               ("Impair", *sc(lambda i, j: (i + j) % 2 == 1))])
    for nom, idx in (("Domicile", 0), ("Extérieur", 1)):
        ajouter(B, "%s : total pair / impair" % nom,
                [("Pair", *sc(lambda i, j, idx=idx: (i if idx == 0 else j) % 2 == 0)),
                 ("Impair", *sc(lambda i, j, idx=idx: (i if idx == 0 else j) % 2 == 1))])
    iss = [(str(k), *sc(lambda i, j, k=k: i + j == k)) for k in range(5)]
    iss.append(("5 ou plus", *sc(lambda i, j: i + j >= 5)))
    ajouter(B, "Nombre exact de buts dans le match", iss)
    for nom, idx in (("Domicile", 0), ("Extérieur", 1)):
        iss = [(str(k), *sc(lambda i, j, k=k, idx=idx: (i if idx == 0 else j) == k)) for k in range(3)]
        iss.append(("3 ou plus", *sc(lambda i, j, idx=idx: (i if idx == 0 else j) >= 3)))
        ajouter(B, "Nombre exact de buts %s" % nom, iss)
    ajouter(B, "Multi-buts", [("%d-%d buts" % (a, b), *sc(lambda i, j, a=a, b=b: a <= i + j <= b))
                              for a, b in ((1, 2), (1, 3), (2, 3), (2, 4), (3, 5), (4, 6))])
    ajouter(B, "Au moins une équipe marque", [("Oui", *sc(lambda i, j: i + j > 0)), ("Non (0-0)", *sc(lambda i, j: i + j == 0))])
    ajouter(B, "Une seule équipe marque", [("Oui", *sc(lambda i, j: (i > 0) != (j > 0))),
                                           ("Non", *sc(lambda i, j: (i > 0) == (j > 0)))])

    # ----- Combinés -----
    res = (("Domicile", lambda i, j: i > j), ("Nul", lambda i, j: i == j), ("Extérieur", lambda i, j: i < j))
    dc = (("Domicile ou nul", lambda i, j: i >= j), ("Domicile ou extérieur", lambda i, j: i != j),
          ("Nul ou extérieur", lambda i, j: i <= j))
    for L in (1.5, 2.5, 3.5):
        iss = []
        for nom, f in res:
            iss.append(("%s et plus de %.1f" % (nom, L), *sc(lambda i, j, f=f, L=L: f(i, j) and i + j > L)))
            iss.append(("%s et moins de %.1f" % (nom, L), *sc(lambda i, j, f=f, L=L: f(i, j) and i + j < L)))
        ajouter(C, "Résultat + Total (%.1f)" % L, iss)
    iss = []
    for nom, f in res:
        iss.append(("%s et les deux marquent" % nom, *sc(lambda i, j, f=f: f(i, j) and i > 0 and j > 0)))
        iss.append(("%s et une équipe ne marque pas" % nom, *sc(lambda i, j, f=f: f(i, j) and (i == 0 or j == 0))))
    ajouter(C, "Résultat + Les deux équipes marquent", iss)
    iss = []
    for nom, f in dc:
        iss.append(("%s et plus de 2.5" % nom, *sc(lambda i, j, f=f: f(i, j) and i + j > 2.5)))
        iss.append(("%s et moins de 2.5" % nom, *sc(lambda i, j, f=f: f(i, j) and i + j < 2.5)))
    ajouter(C, "Double chance + Total (2.5)", iss)
    iss = []
    for nom, f in dc:
        iss.append(("%s et les deux marquent" % nom, *sc(lambda i, j, f=f: f(i, j) and i > 0 and j > 0)))
        iss.append(("%s et une équipe ne marque pas" % nom, *sc(lambda i, j, f=f: f(i, j) and (i == 0 or j == 0))))
    ajouter(C, "Double chance + Les deux équipes marquent", iss)
    ajouter(C, "Les deux équipes marquent + Total (2.5)", [
        ("Oui et plus de 2.5", *sc(lambda i, j: i > 0 and j > 0 and i + j > 2.5)),
        ("Oui et moins de 2.5", *sc(lambda i, j: i > 0 and j > 0 and i + j < 2.5)),
        ("Non et plus de 2.5", *sc(lambda i, j: (i == 0 or j == 0) and i + j > 2.5)),
        ("Non et moins de 2.5", *sc(lambda i, j: (i == 0 or j == 0) and i + j < 2.5))])

    # ----- Score exact -----
    scores = sorted(((m[i][j], i, j) for i in range(MAXB + 1) for j in range(MAXB + 1)), reverse=True)[:15]
    liste = {(i, j) for _, i, j in scores}
    iss = [("%d-%d" % (i, j), p, (lambda c, i=i, j=j: c["fh"] == i and c["fa"] == j)) for p, i, j in scores]
    iss.append(("Autre score", 1 - sum(p for p, _, _ in scores), lambda c: (c["fh"], c["fa"]) not in liste))
    ajouter(S, "Score exact", iss)

    # ----- Déroulement -----
    prem_dom = sum(m[i][j] * i / (i + j) for i in range(MAXB + 1) for j in range(MAXB + 1) if i + j > 0)
    prem_ext = sum(m[i][j] * j / (i + j) for i in range(MAXB + 1) for j in range(MAXB + 1) if i + j > 0)
    aucun = lambda c: c["fh"] + c["fa"] == 0
    ajouter(D, "Équipe qui marque le premier but", [("Domicile", prem_dom, lambda c: _egal(premier(c), "D")),
                                                    ("Extérieur", prem_ext, lambda c: _egal(premier(c), "E")),
                                                    ("Aucun but", m[0][0], aucun)])
    ajouter(D, "Équipe qui marque le dernier but", [("Domicile", prem_dom, lambda c: _egal(dernier(c), "D")),
                                                    ("Extérieur", prem_ext, lambda c: _egal(dernier(c), "E")),
                                                    ("Aucun but", m[0][0], aucun)])

    def prem_et(equipe, cond):
        tot = 0.0
        for i in range(MAXB + 1):
            for j in range(MAXB + 1):
                if i + j and cond(i, j):
                    tot += m[i][j] * ((i if equipe == 0 else j) / (i + j))
        return tot

    def pe(cote, cond):
        return lambda c: None if premier(c) is None else (premier(c) == cote and cond(c["fh"], c["fa"]))
    ajouter(D, "Premier but et résultat final", [
        ("Domicile marque en premier et gagne", prem_et(0, lambda i, j: i > j), pe("D", lambda i, j: i > j)),
        ("Domicile marque en premier et fait nul", prem_et(0, lambda i, j: i == j), pe("D", lambda i, j: i == j)),
        ("Domicile marque en premier et perd", prem_et(0, lambda i, j: i < j), pe("D", lambda i, j: i < j)),
        ("Extérieur marque en premier et gagne", prem_et(1, lambda i, j: j > i), pe("E", lambda i, j: j > i)),
        ("Extérieur marque en premier et fait nul", prem_et(1, lambda i, j: i == j), pe("E", lambda i, j: i == j)),
        ("Extérieur marque en premier et perd", prem_et(1, lambda i, j: j < i), pe("E", lambda i, j: j < i)),
        ("Aucun but", m[0][0], aucun)])
    rem_dom = sum(m[i][j] * (1 - sans_remontee(i, j) / comb(i + j, i))
                  for i in range(MAXB + 1) for j in range(MAXB + 1) if i > j)
    rem_ext = sum(m[i][j] * (1 - sans_remontee(j, i) / comb(i + j, i))
                  for i in range(MAXB + 1) for j in range(MAXB + 1) if j > i)

    def aucune_remontee(c):
        a, b = revient(c, "D"), revient(c, "E")
        return None if a is None or b is None else not (a or b)
    ajouter(D, "Revient au score et gagne", [("Domicile revient et gagne", rem_dom, lambda c: revient(c, "D")),
                                              ("Extérieur revient et gagne", rem_ext, lambda c: revient(c, "E")),
                                              ("Aucune remontée", 1 - rem_dom - rem_ext, aucune_remontee)], approx=True)

    # ----- Mi-temps (estimations : on applique la répartition moyenne des buts) -----
    mu1h, mu1a, mu2h, mu2a = PART_MT1 * lh, PART_MT1 * la, (1 - PART_MT1) * lh, (1 - PART_MT1) * la
    mu1, mu2 = mu1h + mu1a, mu2h + mu2a
    J, ht = jointe_mt_fin(p1x2(m), mu1h, mu1a, mu2h, mu2a)
    ajouter(T, "Résultat à la mi-temps", [("Domicile", ht[0], lambda c: _ht(c, lambda a, b: a > b)),
                                          ("Nul", ht[1], lambda c: _ht(c, lambda a, b: a == b)),
                                          ("Extérieur", ht[2], lambda c: _ht(c, lambda a, b: a < b))], True)
    noms = ("Domicile", "Nul", "Extérieur")
    ajouter(T, "Mi-temps / Fin du match",
            [("%s / %s" % (noms[a], noms[b]), J[a][b],
              (lambda c, a=a, b=b: _ht(c, lambda x, y: _res(x, y) == a and _res(c["fh"], c["fa"]) == b)))
             for a in range(3) for b in range(3)], True)
    for titre, mu, deuxieme in (("1re mi-temps", mu1, False), ("2e mi-temps", mu2, True)):
        for L in (0.5, 1.5, 2.5):
            p_moins = sum(poisson(k, mu) for k in range(int(L) + 1))

            def buts_mt(c, deuxieme=deuxieme):
                h = moitie(c)
                if h is None:
                    return None
                g1 = h[0] + h[1]
                return (c["fh"] + c["fa"] - g1) if deuxieme else g1
            ajouter(T, "Total de buts en %s (%.1f)" % (titre, L),
                    [("Plus de %.1f" % L, 1 - p_moins, (lambda c, L=L, f=buts_mt: _op(f(c), lambda v: v > L))),
                     ("Moins de %.1f" % L, p_moins, (lambda c, L=L, f=buts_mt: _op(f(c), lambda v: v < L)))], True)
    p_m1 = sum(poisson(a, mu1) * poisson(b, mu2) for a in range(15) for b in range(15) if a > b)
    p_m2 = sum(poisson(a, mu1) * poisson(b, mu2) for a in range(15) for b in range(15) if a < b)

    def compare(c, op):
        h = moitie(c)
        if h is None:
            return None
        g1 = h[0] + h[1]
        g2 = c["fh"] + c["fa"] - g1
        return op(g1, g2)
    ajouter(T, "Mi-temps avec le plus de buts", [("1re mi-temps", p_m1, lambda c: compare(c, lambda a, b: a > b)),
                                                 ("Égalité", 1 - p_m1 - p_m2, lambda c: compare(c, lambda a, b: a == b)),
                                                 ("2e mi-temps", p_m2, lambda c: compare(c, lambda a, b: a < b))], True)
    g1p, g2p = 1 - exp(-mu1), 1 - exp(-mu2)

    def un_but(c, partie):
        h = moitie(c)
        if h is None:
            return None
        g1 = h[0] + h[1]
        return {1: g1 >= 1, 2: c["fh"] + c["fa"] - g1 >= 1, 3: g1 >= 1 and c["fh"] + c["fa"] - g1 >= 1}[partie]
    for nom, partie, p in (("But en 1re mi-temps", 1, g1p), ("But en 2e mi-temps", 2, g2p), ("But dans chaque mi-temps", 3, g1p * g2p)):
        ajouter(T, nom, [("Oui", p, lambda c, partie=partie: un_but(c, partie)),
                         ("Non", 1 - p, lambda c, partie=partie: None if un_but(c, partie) is None else not un_but(c, partie))], True)

    def deux_marquent(c, deuxieme):
        h = moitie(c)
        if h is None:
            return None
        return ((c["fh"] - h[0] > 0) and (c["fa"] - h[1] > 0)) if deuxieme else (h[0] > 0 and h[1] > 0)
    b1 = (1 - exp(-mu1h)) * (1 - exp(-mu1a))
    b2 = (1 - exp(-mu2h)) * (1 - exp(-mu2a))
    for nom, deuxieme, p in (("Les deux équipes marquent en 1re mi-temps", False, b1),
                             ("Les deux équipes marquent en 2e mi-temps", True, b2)):
        ajouter(T, nom, [("Oui", p, lambda c, d=deuxieme: deux_marquent(c, d)),
                         ("Non", 1 - p, lambda c, d=deuxieme: None if deux_marquent(c, d) is None else not deux_marquent(c, d))], True)
    lam_tot = lh + la
    cum, brut = 0.0, []
    for part in PROFIL_15MIN:
        brut.append(exp(-lam_tot * cum) - exp(-lam_tot * (cum + part)))
        cum += part
    facteur = (1 - m[0][0]) / sum(brut)
    noms_t = ("1-15 min", "16-30 min", "31-45 min", "46-60 min", "61-75 min", "76-90 min")
    limites = (15, 30, 45, 60, 75, 200)

    def tranche(c, k):
        if c["fh"] + c["fa"] == 0:
            return False
        mn = minute_premier_but(c)
        if mn is None:
            return None
        lo = limites[k - 1] if k else -1
        return lo < mn <= limites[k]
    ajouter(T, "Moment du premier but", [(n, b * facteur, (lambda c, k=k: tranche(c, k))) for k, (n, b) in enumerate(zip(noms_t, brut))]
            + [("Aucun but", m[0][0], aucun)], True)
    return out


def tous_les_marches(m, lh, la):
    """Format du site (data.json) : sans les fonctions de verification."""
    return [{"groupe": x["groupe"], "nom": x["nom"], "approx": x["approx"], "fiab": x["fiab"],
             "issues": [{"n": n, "p": pct(p)} for n, p, _ in x["issues"]]} for x in marches_verifiables(m, lh, la)]


# ---------------------------------------------------------------- verification apres le match
def bilan(marches, ctx):
    """Compact : [groupe, nom, [[issue, %, realisee 1/0/None], ...], verdict 1/0/None, estimation 1/0].
    Verdict = l'issue la plus probable du marche s'est-elle produite ?"""
    out = []
    for mk in marches:
        oks = [v(ctx) for (_, _, v) in mk["issues"]]
        if any(o is None for o in oks):
            oks, verdict = [None] * len(oks), None
        else:
            top = max(range(len(oks)), key=lambda k: mk["issues"][k][1])
            verdict = 1 if oks[top] else 0
        out.append([mk["groupe"], mk["nom"], [[lab, pct(p), None if o is None else int(bool(o))]
                                              for (lab, p, _), o in zip(mk["issues"], oks)], verdict, 1 if mk["approx"] else 0])
    return out
