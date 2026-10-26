"""Suites de référence (SPEC.md §10, « Ordre des suites de référence ») d'une question du
corpus synthétique, sur le stock de référence (`eval.equivariance.stock_de_reference`).

1. NOTE_SAME ou NOTE_DIFF d'abord, si le message déclare une identité.
2. Citations dans l'ordre des étapes de la vérité terrain (première ligne de chaque étape).
3. Chaque SAME juste avant la citation de la ligne qui porte le fait relié ; sa preuve P
   est la ligne « X, dit S » (sinon SANS_PREUVE). L'étape PREUVE est cette preuve.
4. Étapes CONFLIT consécutives (versions contradictoires de la vérité terrain) : un bloc
   CONFLIT si la première ligne a une arête CONFLIT vers chacune des autres dans le
   contexte (conflit établi) ; sinon un bloc CONFLIT SANS_PREUVE (conflit supposé).
5. CALCUL après les citations, précédé de DONC. 6. Connecteur ET entre les segments.
Synthèse (mode synthèse) : après les segments, une phrase par phrase de référence.
ASK_SAME : les faits ambigus (plus de deux : un ASK_SAME par paire avec le premier, liés par
ET). Abstention : ABSTENTION FIN.
"""

import sqlite3

from ccm.anonymize.exemple import Message, _zones, anonymiser
from ccm.anonymize.table import TableConversation
from ccm.config import IngestConfig
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import Question
from ccm.eval.equivariance import message_de_reference
from ccm.grammar.lexicon import OPERATEURS, mots
from ccm.schema import Exemple, Relation


def _lignes(con: sqlite3.Connection, d: Dossier) -> dict[str, int]:
    """« P03:4 » → prop_id (stock de référence : une proposition par ligne, dans l'ordre)."""
    out = {}
    for p in d.pieces:
        q = "SELECT prop_id FROM proposition WHERE piece_id = ? ORDER BY prop_id"
        ids = [i for (i,) in con.execute(q, (p.id,))]
        out |= {f"{p.id}:{i}": pid for i, pid in enumerate(ids)}
    return out


def _lignes_utiles(q: Question) -> list[str]:
    refs = [e.lignes[0] for e in q.etapes]
    refs += [i.preuve for i in q.identites if i.preuve]
    refs += [f.rsplit(":", 1)[0] for f in (*q.ambigus, *(i.fait for i in q.identites))]
    refs += [x for t in q.historique for x in t.lignes]
    refs += [s for ph in q.synthese for s in ph.sources]
    return refs


def exemple_de_reference(
    d: Dossier, q: Question, con: sqlite3.Connection, cfg: IngestConfig, graine: int = 0,
    limite: int = 150,
) -> tuple[Exemple, dict[int, str]]:  # fmt: skip
    """Exemple de la question : lignes utiles, complétées dans l'ordre jusqu'à `limite` ;
    et les valeurs de ses nombres (valeur_id → valeur), pour le masque."""
    lignes = _lignes(con, d)
    ids = {lignes[r] for r in _lignes_utiles(q)}
    for pid in sorted(lignes.values()):
        if len(ids) >= limite:
            break
        ids.add(pid)
    citees = frozenset(lignes[x] for t in q.historique for x in t.lignes)
    table = TableConversation(graine, cfg.anonymiseur.reservoir)
    ex = anonymiser(
        con, sorted(ids), message_de_reference(q.message, cfg), table, cfg,
        historique=[message_de_reference(t, cfg) for t in q.historique if t.texte],
        citees=citees, id=q.id, origine="synthetique",
    )  # fmt: skip
    return ex, table.valeurs()


def _rang_zone(m: Message, debut: int, cfg: IngestConfig) -> int:
    zs = _zones(m.texte, m.noms, [(n.debut, n.fin, n.genre, n.valeur, n.unite, n.precision)
                                  for n in m.nombres], cfg)  # fmt: skip
    return next(j for j, z in enumerate(zs) if z.debut == debut)


def cible_de_reference(
    d: Dossier, q: Question, con: sqlite3.Connection, ex: Exemple, cfg: IngestConfig,
    synthese: bool = False,
) -> list[str]:  # fmt: skip
    if q.abstention:
        return ["ABSTENTION", "FIN"]
    lignes = _lignes(con, d)
    local = {p.prop_id: p.local for p in ex.propositions}
    pieces = {p.id: p for p in d.pieces}

    def P(ref: str) -> str:
        return f"P:{local[lignes[ref]]}"

    def marque(fait: str) -> str:
        """« P03:4:1 » → « k.j »."""
        ref, i = fait.rsplit(":", 1)
        piece, n = ref.split(":")
        debut = pieces[piece].lignes[int(n)].faits[int(i)].debut
        pid = lignes[ref]
        noms = con.execute("SELECT debut, fin, type FROM mention WHERE prop_id = ?", (pid,))
        nbs = con.execute("SELECT debut, fin, genre, valeur, unite, precision_date FROM nombre "
                          "WHERE prop_id = ?", (pid,))  # fmt: skip
        texte = con.execute("SELECT texte FROM proposition WHERE prop_id = ?", (pid,)).fetchone()
        zs = _zones(texte[0], list(noms), list(nbs), cfg)
        return f"{local[pid]}.{next(j for j, z in enumerate(zs) if z.debut == debut)}"

    msg = message_de_reference(q.message, cfg)

    def question(rang: int) -> str:
        return f"M:q.{_rang_zone(msg, q.message.faits[rang].debut, cfg)}"

    def calcul(postfixe) -> list[str]:
        return ["CALCUL", *(x if x in OPERATEURS else f"N:{marque(x)}" for x in postfixe),
                "FIN_CALCUL"]  # fmt: skip

    segments: list[list[str]] = []
    if q.declaration:
        a, b = q.declaration.faits
        genre = "NOTE_SAME" if q.declaration.genre == "MEME" else "NOTE_DIFF"
        segments.append([genre, question(a), question(b)])
    if q.ambigus:  # ASK_SAME M M : une paire par personne possible après la première
        premier, *autres = (f"M:{marque(f)}" for f in q.ambigus)
        segments += [["ASK_SAME", premier, m] for m in autres]
    conflits = {(a, b) for a, b, r in ex.relations_props if r == Relation.CONFLIT}
    conflits |= {(b, a) for a, b in conflits}
    preuves = {i.preuve for i in q.identites if i.preuve}
    vues: set[str] = set()
    etapes = list(q.etapes)
    while etapes:
        e = etapes.pop(0)
        ref = e.lignes[0]
        if e.role == "PREUVE" and ref in preuves:
            continue
        if e.role == "CONFLIT":
            bloc = [ref]
            while etapes and etapes[0].role == "CONFLIT":
                bloc.append(etapes.pop(0).lignes[0])
            k0 = local[lignes[ref]]
            etabli = all((k0, local[lignes[r]]) in conflits for r in bloc[1:])
            segments.append(["CONFLIT", *([] if etabli else ["SANS_PREUVE"]), *map(P, bloc),
                             "FIN_CONFLIT"])  # fmt: skip
            vues |= set(bloc)
            continue
        for i in q.identites:
            if i.fait.rsplit(":", 1)[0] == ref:
                segments.append(["SAME", question(i.question), f"M:{marque(i.fait)}",
                                 P(i.preuve) if i.preuve else "SANS_PREUVE"])  # fmt: skip
        if ref not in vues:
            segments.append([P(ref)])
            vues.add(ref)
    suite = []
    for s in segments:
        suite += (["ET"] if suite else []) + s
    if q.calcul:
        suite += ["DONC", *calcul(q.calcul.postfixe)]
    if synthese and q.synthese:
        suite.append("SYNTHESE")
        for ph in q.synthese:
            suite += ["SOURCES", *map(P, ph.sources), "DEBUT"]
            for el in ph.elements:
                if el.genre == "MOTS":
                    suite += [f"W:{m}" for m in mots(el.mots)]
                elif el.genre == "CALCUL":
                    suite += calcul(el.calcul)
                else:
                    suite.append(f"{el.genre}:{marque(el.fait)}")
            suite.append("FIN_PHRASE")
        suite.append("FIN_SYNTHESE")
    return [*suite, "FIN"]
