"""T11 (SPEC.md §10 bis, « Évaluation ») et décodages au hasard sous masque (SPEC.md §2,
seuil de phase 3) : 100 000 décodages aléatoires en mode synthèse.

Chaque décodage doit être valide : fin par FIN dans `pas_max_synthese`, sans impasse, relu
par l'automate (`accepter`), vérifié sans erreur. Chaque réponse rendue passe le contrôle de
T5. Chaque phrase de synthèse passe T11 : aucun chiffre, aucun mot hors de V, et chaque nom,
nombre et date affiché appartient aux sources de sa phrase (sources déclarées et leurs
dépendances DEPEND_DE, lues dans le stock et non dans le contexte de l'automate).

Dossiers synthétiques d'entraînement 0, 1, … avec les mentions de référence (comme T4) ;
vocabulaire V provisoire : mots des synthèses de référence du dossier.
"""

import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from test_t5_rendu_ferme import _controler, _fermes

from ccm.config import load_config
from ccm.data.worldgen.cibles import exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import message_de_reference, stock_de_reference
from ccm.grammar.automaton import Contexte, accepter, decoder_au_hasard
from ccm.grammar.lexicon import mots
from ccm.verify.verifier import Entree, decouper, verifier

CFG = load_config("ingest")
GCFG = load_config("grammar")
VCFG = load_config("verify")
WCFG = load_config("worldgen")
TOTAL = 100_000
PAR_QUESTION = 25


def _sources(con, ex, sources: list[int]) -> tuple[set[int], list[str], set[str]]:
    """Propositions, textes et surfaces des mentions des sources d'une phrase et de leur
    fermeture DEPEND_DE dans le stock."""
    ids = {ex.propositions[k].prop_id for k in sources}
    pile = list(ids)
    while pile:
        for (d,) in con.execute("SELECT dst FROM arete WHERE src = ? AND type = 'DEPEND_DE'",
                                (pile.pop(),)):  # fmt: skip
            if d not in ids:
                ids.add(d)
                pile.append(d)
    marques = ",".join("?" * len(ids))
    textes = [t for (t,) in con.execute(
        f"SELECT texte FROM proposition WHERE prop_id IN ({marques})", list(ids))]  # fmt: skip
    noms = {s for (s,) in con.execute(
        f"SELECT surface FROM mention WHERE prop_id IN ({marques})", list(ids))}  # fmt: skip
    return ids, textes, noms


def _pointeurs(elements) -> list[str]:
    out = []
    for el in elements:
        out += el[1] if isinstance(el, tuple) else [el]
    return [p for p in out if p[:2] in ("M:", "N:")]


def _t11(con, ex, suite, rep, v) -> int:
    """Contrôle T11 des phrases de synthèse ; rend leur nombre."""
    phrases = [ph for seg in decouper(suite) if seg[0] == "SYNTHESE" for ph in seg[1]]
    blocs = [b for b in rep.blocs if b.style == "synthese"][1:]  # [0] : l'étiquette
    assert len(blocs) == len(phrases), (suite, rep.texte)
    for (sources, elements), bloc in zip(phrases, blocs, strict=True):
        ids, textes, noms = _sources(con, ex, [int(k) for k in sources])
        for p in _pointeurs(elements):
            assert ex.propositions[int(p[2:].split(".")[0])].prop_id in ids, (p, sources)
        for f in bloc.frags:
            if f.genre == "mot":
                assert f.texte.lower() in v and not re.search(r"\d", f.texte), f
            elif f.genre == "nom":
                assert f.texte in noms, (f, sources)
            elif f.genre == "texte":
                assert any(f.texte in t for t in textes), (f, sources)
            elif f.genre in ("gabarit", "calcul", "ref"):
                pass  # contrôlés par T5 (calcul : résultat sur des nombres de la phrase)
            else:
                raise AssertionError(f)
        assert any(f.genre in ("nom", "texte", "calcul") for f in bloc.frags), bloc
    return len(phrases)


def _dossier(i: int) -> Counter:
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    questions = poser_questions(d, WCFG)
    con = stock_de_reference(d, CFG)
    v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                  for m in mots(e.mots))  # fmt: skip
    n: Counter = Counter()
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        hist = tuple(message_de_reference(t, CFG) for t in q.historique if t.texte)
        entree = Entree(ex, valeurs, message_de_reference(q.message, CFG), hist)
        textes, noms, refs = _fermes(con, ex, entree)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
        for g in range(PAR_QUESTION):
            suite = decoder_au_hasard(ctx, GCFG, f"{i}:{q.id}:{g}", synthese=True)
            assert suite[-1] == "FIN" and len(suite) <= GCFG.pas_max_synthese, suite
            assert accepter(ctx, suite, GCFG, True), suite
            rep = verifier(con, entree, suite, CFG, GCFG, VCFG, synthese=True, vocabulaire=v)
            _controler(rep, textes, noms, refs, v)
            n["phrases"] += _t11(con, ex, suite, rep, v)
            n["decodages"] += 1
            n["avec_synthese"] += "SYNTHESE" in suite
    con.close()
    return n


def test_t11_cent_mille_decodages():
    n: Counter = Counter()
    pool = ProcessPoolExecutor(min(4, os.cpu_count() or 1))  # mémoire
    try:
        for c in pool.map(_dossier, range(TOTAL // 500)):  # ~975 décodages par dossier
            n += c
            if n["decodages"] >= TOTAL:
                break
    finally:
        pool.shutdown(cancel_futures=True)
    print(f"T11 : {dict(n)}")  # visible avec pytest -s
    assert n["decodages"] >= TOTAL, n
    assert n["avec_synthese"] >= TOTAL // 4 and n["phrases"] >= TOTAL // 4, n
