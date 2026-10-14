import json
from pathlib import Path

import pydantic
import pytest

from ccm.schema import (
    LEXIQUE,
    RELATION_IDS,
    Exemple,
    TexteMarque,
    ouvrir_stock,
)

EXEMPLE = Path(__file__).parent.parent / "golden" / "exemple_spec.json"


def charger():
    return json.loads(EXEMPLE.read_text(encoding="utf-8"))


def test_exemple_de_la_spec_valide():
    ex = Exemple.model_validate(charger())
    assert ex.cible[-1] == "FIN"


def test_aller_retour_json():
    ex = Exemple.model_validate(charger())
    assert Exemple.model_validate_json(ex.model_dump_json()) == ex


def test_24_relations_et_25_jetons():
    ids = sorted(i for t in RELATION_IDS.values() for i in t)
    assert ids == list(range(1, 25))
    assert len(LEXIQUE) == len(set(LEXIQUE)) == 25


@pytest.mark.parametrize(
    "modif",
    [
        lambda d: d["question"].update(texte="sans marqueur"),
        lambda d: d["relations_noms"].append([1, 2, "SUIVANTE"]),
        lambda d: d["relations_props"].append([0, 1, "MEME_CHAINE"]),
        lambda d: d["cible"].insert(0, "SELON"),
        lambda d: d["cible"].insert(0, "P:9"),
        lambda d: d["justificatives"].append(4),
        lambda d: d.update(inconnu=1),
        lambda d: d["propositions"][0].update(rang=5),
        lambda d: d["relations_props"].append([0, 1, "SUIVANTE"]),
        lambda d: d["propositions"][0]["marques"][3].pop("precision"),
        lambda d: d["propositions"][0]["marques"][3].update(signe=1),
        lambda d: d["propositions"][0]["marques"][3].update(genre="NUM"),
        lambda d: d["propositions"][0]["marques"][3].update(genre="NUM", signe=1),
    ],
)
def test_exemple_invalide_refuse(modif):
    d = charger()
    modif(d)
    with pytest.raises(pydantic.ValidationError):
        Exemple.model_validate(d)


def test_marqueurs_dans_l_ordre():
    nom = {"genre": "NOM", "type": "PER", "nom": 0}
    TexteMarque(texte="⟦0⟧ et ⟦1⟧", marques=[nom, nom])
    with pytest.raises(pydantic.ValidationError):
        TexteMarque(texte="⟦1⟧ et ⟦0⟧", marques=[nom, nom])


def test_stock_cree_les_tables(tmp_path):
    con = ouvrir_stock(tmp_path / "dossier.sqlite")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"piece", "proposition", "mention", "nombre", "arete", "contrainte", "trace"}
    con.close()
    ouvrir_stock(tmp_path / "dossier.sqlite").close()  # réouverture sans erreur


def test_marque_num_valide():
    d = charger()
    date = d["propositions"][0]["marques"][3]
    del date["precision"]
    date.update(genre="NUM", unite="€", grandeur=3, signe=1)
    Exemple.model_validate(d)
