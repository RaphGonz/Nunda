"""Tests figés de `ccm answer --oracle` (SPEC.md §2, phase 3 ; §3, `tests/golden/`).

Un dossier de validation figé (`oracle/syn-1000000` : PDF, vérité terrain, questions) passe
par la vraie chaîne : ingestion, index BM25, recherche, anonymiseur, modèle oracle,
vérificateur, relance après NOTE_*. Pour chaque question, en mode citation et en mode
synthèse, les pas du modèle, les abstentions de l'oracle et le texte affiché sont égaux à
ceux de `oracle/attendu.json`. Chaque fragment affiché est contrôlé comme T5 : aucun nom,
nombre ou date hors du contexte.

Après un changement voulu de la chaîne, réécrire les sorties attendues et relire leur diff :
    CCM_GOLDEN=ecrire uv run pytest tests/golden/test_answer_oracle.py
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ccm.answer import repondre
from ccm.cli import app
from ccm.config import load_config
from ccm.eval.rendu import controler, fermes
from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
from ccm.model.oracle import Oracle
from ccm.schema import ouvrir_stock
from ccm.search.bm25 import charger_index, construire_index, dossier_index

DOSSIER = Path(__file__).parent / "oracle" / "syn-1000000"
ATTENDU = Path(__file__).parent / "oracle" / "attendu.json"
CFGS = tuple(load_config(x) for x in ("ingest", "search", "grammar", "verify"))


@pytest.fixture(scope="module")
def stock(tmp_path_factory) -> Path:
    s = tmp_path_factory.mktemp("oracle") / "stock.sqlite"
    con = ouvrir_stock(s)
    ingerer_fichiers(con, fichiers_pdf([DOSSIER]), CFGS[0])
    construire_index(con, dossier_index(s), CFGS[0], CFGS[1])
    con.commit()
    con.close()
    return s


def _sorties(stock: Path) -> list[dict]:
    o = Oracle(DOSSIER)
    con = ouvrir_stock(stock)
    index = charger_index(dossier_index(stock))
    out = []
    for q in o.questions:
        for synthese in (False, True):
            r = repondre(con, index, o, q, *CFGS, conv_id=f"{q.id}-{synthese}",
                         synthese=synthese)  # fmt: skip
            textes, noms, refs = set(), set(), set()
            for t in r.tours:
                ts, ns, rs = fermes(con, t.entree.ex, t.entree)
                textes |= set(ts)
                noms |= ns
                refs |= rs
            controler(r.reponse, textes, noms, refs, o.vocabulaire)
            suites = [" ".join(t.suite) for t in r.tours]
            raisons = [t.raison for t in r.tours]
            out.append(dict(id=q.id, synthese=synthese, suites=suites, raisons=raisons,
                            texte=r.reponse.texte))  # fmt: skip
    con.close()
    return out


def test_answer_oracle_fige(stock):
    sorties = _sorties(stock)
    if os.environ.get("CCM_GOLDEN") == "ecrire":
        ATTENDU.write_text(json.dumps(sorties, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")  # fmt: skip
    attendu = json.loads(ATTENDU.read_text(encoding="utf-8"))
    assert len(sorties) == len(attendu)
    for s, a in zip(sorties, attendu, strict=True):
        assert s == a, s["id"]
    # L'oracle rejoue la référence, sauf quand la vraie détection manque un fait.
    rejouees = sum(not any(s["raisons"]) for s in sorties)
    assert rejouees / len(sorties) >= 0.9


def test_cli_answer(stock, tmp_path):
    attendu = {(a["id"], a["synthese"]): a for a in json.loads(ATTENDU.read_text("utf-8"))}
    copie = tmp_path / "stock.sqlite"  # la commande écrit trace et contraintes
    shutil.copy(stock, copie)
    shutil.copytree(dossier_index(stock), dossier_index(copie))
    for qid, synthese in [("syn-1000000-q36", False), ("syn-1000000-q38", False),
                          ("syn-1000000-q29", True)]:  # fmt: skip
        args = ["answer", "--stock", str(copie), "--oracle", str(DOSSIER), "--id", qid]
        r = CliRunner().invoke(app, args + (["--synthese"] if synthese else []))
        assert r.exit_code == 0, r.output
        assert r.stdout.strip() == attendu[(qid, synthese)]["texte"]
