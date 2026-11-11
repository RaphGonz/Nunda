"""T9 (SPEC.md §14) : même graine, même entrée → mêmes fichiers ; même réponse en décodage
glouton.

Deux processus neufs, avec des graines de hachage différentes (`PYTHONHASHSEED`), font la
même chose : écrire un dossier du corpus (PDF, `verite.json`, `questions.json`), ses suites
de référence (`cibles.json`), puis, pour chaque question, un décodage glouton sous masque et
sa réponse vérifiée. Le modèle n'existe pas encore : le décodage glouton prend, à chaque pas,
le jeton permis de plus haut score, le score étant une fonction fixe du préfixe et du jeton
(le modèle la remplacera). Un décodage au hasard de même graine est aussi comparé.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = r"""
import json, sys, zlib
from pathlib import Path
from ccm.config import load_config
from ccm.data.worldgen.cibles import exemple_de_reference
from ccm.data.worldgen.corpus import _ecrire
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.data.worldgen.suites import suites_du_dossier
from ccm.eval.equivariance import message_de_reference, stock_de_reference
from ccm.grammar.automaton import Automate, Contexte, decoder_au_hasard
from ccm.grammar.lexicon import mots
from ccm.verify.verifier import Entree, verifier

CFG, GCFG, VCFG, WCFG = (load_config(x) for x in ("ingest", "grammar", "verify", "worldgen"))
sortie = Path(sys.argv[1])
r = _ecrire((7, "entrainement", WCFG, frozenset(), str(sortie)))
dossier = sortie / r["id"]
suites_du_dossier(dossier)
d = Dossier.model_validate_json((dossier / "verite.json").read_text(encoding="utf-8"))
qs = poser_questions(d, WCFG)
con = stock_de_reference(d, CFG)
v = frozenset(m.lower() for q in qs for ph in q.synthese for e in ph.elements for m in mots(e.mots))

def glouton(ctx, synthese):
    a = Automate(ctx, GCFG, synthese)
    while not a.fini:
        prefixe = "|".join(a.suite)
        a.avancer(max(a.autorises(), key=lambda p: (zlib.crc32(f"{prefixe}|{p}".encode()), p)))
    return a.suite

out = []
for q in qs:
    ex, valeurs = exemple_de_reference(d, q, con, CFG)
    hist = tuple(message_de_reference(t, CFG) for t in q.historique if t.texte)
    e = Entree(ex, valeurs, message_de_reference(q.message, CFG), hist)
    ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
    for synthese in (False, True):
        for suite in (glouton(ctx, synthese), decoder_au_hasard(ctx, GCFG, q.id, synthese)):
            rep = verifier(con, e, suite, CFG, GCFG, VCFG, synthese=synthese, vocabulaire=v)
            out.append([suite, rep.texte, rep.erreur])
print(json.dumps(out, ensure_ascii=False))
"""


def _lancer(sortie: Path, graine_hachage: str) -> tuple[dict[str, str], list]:
    env = {**os.environ, "PYTHONHASHSEED": graine_hachage, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-c", _SCRIPT, str(sortie)], env=env,
                       capture_output=True, text=True, encoding="utf-8", check=True)  # fmt: skip
    fichiers = {
        str(f.relative_to(sortie)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(sortie.rglob("*"))
        if f.is_file()
    }
    return fichiers, json.loads(r.stdout)


def test_t9_determinisme(tmp_path):
    f1, rep1 = _lancer(tmp_path / "a", "0")
    f2, rep2 = _lancer(tmp_path / "b", "12345")
    assert any(k.endswith(".pdf") for k in f1) and any(k.endswith("cibles.json") for k in f1)
    assert f1 == f2
    assert len(rep1) >= 100 and all(err is None for _, _, err in rep1)
    assert rep1 == rep2
