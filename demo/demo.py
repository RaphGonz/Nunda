"""Démo de `ccm answer --oracle` (phase 3), à filmer.

Le dossier figé des tests (`tests/golden/oracle/syn-1000000`, 9 pièces PDF) est ingéré une
fois, puis chaque scène pose une question et montre :
  1. la question telle que le modèle la reçoit : aucun nom, aucun nombre, des marques ;
  2. les pas du modèle (ici l'oracle) : des pointeurs vers des passages et des marques ;
  3. la réponse affichée par le vérificateur : texte original des pièces, gabarits fixes.

    uv run python demo/demo.py            (toutes les scènes)
    uv run python demo/demo.py --pause    (Entrée entre deux scènes, pour la vidéo)
    uv run python demo/demo.py 2 5        (scènes 2 et 5)
"""

import os
import re
import sys
import time
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / "tests" / "golden" / "oracle" / "syn-1000000"
STOCK = RACINE / "runs" / "demo" / "stock.sqlite"

# (titre, ce que la scène montre, question, mode synthèse)
SCENES = [
    (
        "Raisonnement en deux étapes",
        "La question ne nomme pas la personne cherchée : il faut d'abord trouver qui a fait les "
        "constatations avec ROLLAND Tel, puis la date de son arrestation.",
        "syn-1000000-q21",
        False,
    ),
    (
        "Calcul exact",
        "Deux montants dans deux pièces différentes ; le modèle désigne les opérandes, le code "
        "calcule en décimal exact. Le modèle n'écrit aucun chiffre.",
        "syn-1000000-q36",
        False,
    ),
    (
        "Sources contradictoires",
        "Trois pièces donnent deux heures différentes pour le même contrôle : la réponse montre "
        "le conflit au lieu de choisir.",
        "syn-1000000-q00",
        False,
    ),
    (
        "Même personne ? Hypothèse signalée",
        "La question dit « Chloé Fet », la pièce dit « Mme Fet ». Le lien n'est pas prouvé : "
        "la réponse le dit.",
        "syn-1000000-q27",
        False,
    ),
    (
        "Dialogue",
        "« il » et « alors » renvoient à la question précédente.",
        "syn-1000000-q39",
        False,
    ),
    (
        "Déclaration de l'utilisateur, puis relance",
        "L'utilisateur affirme que deux noms désignent deux personnes. La contrainte est notée "
        "dans le stock, la recherche est relancée avec elle.",
        "syn-1000000-q38",
        False,
    ),
    (
        "Nom ambigu : le modèle demande",
        "Deux personnes du dossier s'appellent Lanard. Le modèle ne devine pas.",
        "syn-1000000-q37",
        False,
    ),
    (
        "Abstention",
        "Aucune pièce ne parle de ce contrôle avec HENRY Rachida : pas de réponse inventée.",
        "syn-1000000-q33",
        False,
    ),
    (
        "Synthèse rédigée, sans un nom ni un chiffre écrit par le modèle",
        "En mode synthèse, le modèle écrit des mots ; chaque nom et chaque nombre est un "
        "pointeur vers le passage source, remplacé par le code au rendu.",
        "syn-1000000-q29",
        True,
    ),
]

GRIS, GRAS, BLEU, VERT, JAUNE, FIN = (f"\033[{c}m" for c in ("90", "1", "36", "32", "33", "0"))


def _marques(t) -> str:
    """Texte marqué lisible : ⟦i⟧ devient ‹PER 3›, ‹DATE›, ‹NUM €›…"""

    def lab(m: re.Match) -> str:
        k = t.marques[int(m.group(1))]
        if k.genre == "NOM":
            return f"{JAUNE}‹{k.type} {k.nom}›{FIN}"
        u = k.unite if k.unite not in ("", "date") else ""
        return f"{JAUNE}‹{k.genre}{' ' + u if u else ''}›{FIN}"

    return re.sub(r"⟦(\d+)⟧", lab, t.texte)


def _ecrire(texte: str = "", lent: bool = False) -> None:
    print(texte, flush=True)
    if lent:
        time.sleep(0.15)


def main(args: list[str]) -> None:
    os.system("")  # couleurs ANSI dans la console Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pause = "--pause" in args
    choix = [int(a) for a in args if a.isdigit()] or range(1, len(SCENES) + 1)

    print(f"{GRIS}Chargement des détecteurs et du dossier…{FIN}", flush=True)
    from ccm.answer import repondre
    from ccm.config import load_config
    from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
    from ccm.model.oracle import Oracle
    from ccm.schema import ouvrir_stock
    from ccm.search.bm25 import charger_index, construire_index, dossier_index

    cfgs = tuple(load_config(x) for x in ("ingest", "search", "grammar", "verify"))
    neuf = not STOCK.exists()
    STOCK.parent.mkdir(parents=True, exist_ok=True)
    con = ouvrir_stock(STOCK)
    if neuf:
        ingerer_fichiers(con, fichiers_pdf([DOSSIER]), cfgs[0])
        construire_index(con, dossier_index(STOCK), cfgs[0], cfgs[1])
        con.commit()
    index = charger_index(dossier_index(STOCK))
    oracle = Oracle(DOSSIER)
    pieces = con.execute("SELECT COUNT(*) FROM piece").fetchone()[0]
    props = con.execute("SELECT COUNT(*) FROM proposition").fetchone()[0]
    print(f"{GRIS}Dossier : {pieces} pièces PDF, {props} passages dans le stock.{FIN}")
    print(
        f"{GRIS}« Contexte : » = phrase dont dépend la citation (elle commence par « Il », "
        f"« Ainsi »…), affichée avant elle.{FIN}\n"
    )

    for n in choix:
        titre, but, qid, synthese = SCENES[n - 1]
        q = oracle.question(id=qid)
        r = repondre(con, index, oracle, q, *cfgs, conv_id=uuid.uuid4().hex, synthese=synthese)
        t0, ex = r.tours[0], r.tours[0].entree.ex
        print(f"{GRAS}{BLEU}━━ {n}. {titre} ━━{FIN}")
        print(f"{GRIS}{but}{FIN}\n")
        for t in q.historique:
            if t.texte:
                qui = "Utilisateur" if t.role == "UTILISATEUR" else "Réponse précédente"
                print(f"{GRIS}{qui} : {t.texte}{FIN}")
        print(f"{GRAS}Question :{FIN} {q.message.texte}\n")
        print(f"{GRAS}Ce que reçoit le modèle{FIN} {GRIS}(aucun nom, aucun nombre){FIN}")
        print(f"  question : {_marques(ex.question)}")
        pointes = re.findall(r"\b[PMN]:(\d+)", " ".join(t0.suite))
        cites = list(dict.fromkeys(map(int, pointes)))
        local = {p.local: p for p in ex.propositions}
        for k in cites[:3]:
            print(f"  passage {k} : {_marques(local[k])}")
        print(f"  {GRIS}… {len(ex.propositions)} passages choisis par la recherche{FIN}")
        for i, t in enumerate(r.tours):
            quoi = "Pas du modèle" if i == 0 else "Pas du modèle après relance"
            print(f"\n{GRAS}{quoi} :{FIN} {GRIS}{' '.join(t.suite)}{FIN}")
        print(f"\n{GRAS}{VERT}Réponse vérifiée :{FIN}")
        for ligne in r.reponse.texte.splitlines():
            _ecrire(f"  {ligne}", lent=pause)
        print()
        if pause and n != choix[-1]:
            input(f"{GRIS}[Entrée]{FIN}")
            print()
    con.close()


if __name__ == "__main__":
    main(sys.argv[1:])
