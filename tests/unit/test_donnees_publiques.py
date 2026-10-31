"""Conversion des jeux publics (SPEC.md §12) : cibles, rejets, absence de noms, nombres anglais."""

import json
import re
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from ccm.config import load_config
from ccm.data import finqa, hotpot, squad_fr
from ccm.data.publics import Brut, Rejet, convertir, convertir_partie, nombres_en, remplir_cache
from ccm.ner.detectors import Zone
from ccm.schema import Detecteur, TypeNom

CFG = load_config("ingest")
GCFG = load_config("grammar")
NOMS = re.compile(r"Ada Lovelace|Lovelace|Turing")


def zones(t: str) -> list[Zone]:
    return [Zone(*m.span(), TypeNom.PER, frozenset({Detecteur.GLINER})) for m in NOMS.finditer(t)]


def _hotpot() -> dict:
    return {
        "id": "a1",
        "question": "Who worked with Turing?",
        "context": {
            "title": ["Turing", "Lovelace"],
            "sentences": [
                [" Turing was born in 1912.", " "],
                ["Ada Lovelace wrote notes.", " She died."],
            ],
        },
        "supporting_facts": {"title": ["Lovelace", "Turing"], "sent_id": [1, 0]},
    }  # fmt: skip


def test_hotpot_chaine_de_citations_sans_nom():
    ex, _ = convertir(hotpot.brut_de(_hotpot()), zones, CFG, GCFG, 0)
    assert ex.langue == "en" and ex.origine == "hotpot"
    assert ex.cible == ["P:2", "ET", "P:0", "FIN"] and ex.justificatives == [2, 0]
    assert "Turing" not in ex.model_dump_json() and "Lovelace" not in ex.model_dump_json()
    assert [p.texte for p in ex.propositions][2] == "She died."


def test_hotpot_justificative_absente_rejetee():
    ligne = _hotpot() | {"supporting_facts": {"title": ["Turing"], "sent_id": [7]}}
    with pytest.raises(Rejet):
        convertir(hotpot.brut_de(ligne), zones, CFG, GCFG, 0)


def test_squad_sans_reponse(tmp_path):
    f = tmp_path / "s.json"
    qas = [{"id": "q1", "question": "Where did Turing go?", "is_impossible": True, "answers": []},
           {"id": "q2", "question": "When?", "is_impossible": False,
            "answers": [{"text": "x"}]}]  # fmt: skip
    f.write_text(json.dumps({"data": [{"title": "Alan_Turing", "paragraphs": [
        {"context": "Turing was born. He studied.", "qas": qas}]}]}))  # fmt: skip
    bruts = list(squad_fr.sans_reponse(f))
    assert [b.id for b in bruts] == ["squad-q1"]
    ex, _ = convertir(bruts[0], zones, CFG, GCFG, 0)
    assert ex.cible == ["ABSTENTION", "FIN"] and len(ex.propositions) == 2


def test_avec_reponse_phrase_de_l_extrait_et_distracteurs(tmp_path):
    f = tmp_path / "p.json"
    paragraphes = [
        {"context": f"Phrase {i} du texte. Seconde phrase {i}.", "qas": []} for i in range(5)
    ]
    debut = paragraphes[0]["context"].index("Seconde")
    paragraphes[0]["qas"] = [{"id": "q", "question": "Quoi ?",
                              "answers": [{"text": "Seconde", "answer_start": debut}]}]  # fmt: skip
    f.write_text(json.dumps({"data": [{"title": "T", "paragraphs": paragraphes}]}))
    (b,) = squad_fr.avec_reponse(f, "piaf", "fr", 3, 0)
    assert len(b.paragraphes) == 4 and b.justificatives == [(0, 1)]


@pytest.mark.parametrize(
    ("programme", "attendu"),
    [("subtract(5829, 5735), divide(#0, 5735)", ["5829", "5735", "−", "5735", "÷"]),
     ("add(12%, 3.5)", ["12", "3.5", "+"])],
)  # fmt: skip
def test_finqa_postfixe(programme, attendu):
    assert finqa.postfixe(programme) == attendu


@pytest.mark.parametrize(
    "programme", ["divide(5, const_100)", "exp(2, 3)", "table_sum(a, none)", "x"]
)
def test_finqa_hors_champ(programme):
    with pytest.raises(finqa.HorsChamp):
        finqa.postfixe(programme)


def _finqa(programme: str) -> dict:
    return {"pre_text": ["Revenue rose .", ".", "costs were 500 in total ."], "post_text": [],
            "table": [["item", "2008", "2007"], ["sales", "$ 5,829", "$ 5,735"]],
            "qa": {"question": "What is the change?", "program": programme,
                   "gold_inds": {"table_1": "sales"}}}  # fmt: skip


def test_finqa_calcul_pointe_les_nombres(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([_finqa("subtract(5829, 5735)"), _finqa("divide(1, const_100)")]))
    bruts, ecartes = finqa.lire(f)
    assert ecartes == {"constante": 1} and len(bruts) == 1
    ex, valeurs = convertir(bruts[0], zones, CFG, GCFG, 0)
    k = ex.justificatives[0]
    assert ex.cible == [
        f"P:{k}",
        "DONC",
        "CALCUL",
        f"N:{k}.0",
        f"N:{k}.1",
        "−",
        "FIN_CALCUL",
        "FIN",
    ]
    assert {Decimal(5735), Decimal(5829)} <= {Decimal(v) for v in valeurs.values()}


def test_finqa_operande_absent_rejete(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([_finqa("subtract(7, 5735)")]))
    with pytest.raises(Rejet, match="opérande"):
        convertir(finqa.lire(f)[0][0], zones, CFG, GCFG, 0)


def test_nombres_anglais():
    lus = nombres_en(
        "On March 5, 2010 sales of $ 5,829.50 rose 3.5 % in 2008 ; 12th.", [], 1900, 2100
    )
    assert [(n.valeur, n.unite) for n in lus] == [
        ("2010-03-05", "date"), ("5829.50", ""), ("3.5", "%"), ("2008", "date")]  # fmt: skip


def test_ecriture_deterministe_et_par_lots(tmp_path):
    cache = tmp_path / "c.sqlite"
    bruts = [Brut(f"x{i}", "squad", "en", "Who?", [["Turing rose.", "Ada Lovelace fell."]],
                  abstention=True, temoins=["Absent"] if i else ["rose"])
             for i in range(5)]  # fmt: skip
    icfg = CFG.model_copy(update={"detection": CFG.detection.model_copy(
        update={"detecteurs": ("regle",)})})  # fmt: skip
    remplir_cache((t for b in bruts for t in ("Who?", *b.paragraphes[0])), cache, icfg, 10)
    cfg = load_config("donnees").model_copy(update={"lot_parquet": 2})
    a = convertir_partie(bruts, tmp_path / "a", cache, cfg, 1)
    b = convertir_partie(bruts, tmp_path / "b", cache, cfg, 1)
    assert a == b and a["gardes"] == 4 and a["lots"] == 2
    assert a["rejets"] == {"titre resté en clair": 1}
    for n in ("lot-00000.parquet", "lot-00001.parquet"):
        assert pq.read_table(tmp_path / "a" / n).equals(pq.read_table(tmp_path / "b" / n))
    assert (tmp_path / "a" / "lot-00000.parquet").read_bytes() == (
        tmp_path / "b" / "lot-00000.parquet"
    ).read_bytes()
