"""Étapes du corpus de pré-entraînement (SPEC.md §12) : nettoyage, fenêtres, propagation,
lecteurs, débit."""

import bz2
import io
import tarfile
from collections import Counter

from ccm.config import SourcePretrain, load_config
from ccm.data.pretrain import debit, lecteurs
from ccm.data.pretrain import propager as prop
from ccm.data.pretrain.fenetres import compter_mots, decouper_document
from ccm.data.pretrain.nettoyer import nettoyer, sans_gutenberg
from ccm.ner.detectors import Zone
from ccm.schema import Detecteur, TypeNom

CFG = load_config("pretrain").corpus
FR = SourcePretrain(langue="fr", lecteur="legi", quota=1)


def test_nettoyer():
    texte, raison = nettoyer("Un  texte⟦3⟧ [P]propre\r\n\n\n\nfin. " * 20, FR, CFG.nettoyage)
    assert raison is None
    assert "⟦" not in texte and "[P]" not in texte and "\n\n\n" not in texte and " " not in texte
    assert nettoyer("court", FR, CFG.nettoyage)[1] == "trop court"
    assert nettoyer("1234 5678 " * 40, FR, CFG.nettoyage)[1] == "peu de lettres"
    livre = FR.model_copy(update={"ocr": True})
    assert nettoyer("a b c d e f g h ij " * 40, livre, CFG.nettoyage)[1] == "OCR"
    g = ("En-tête\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\nCorps.\n"
         "*** END OF THE PROJECT GUTENBERG EBOOK X ***")  # fmt: skip
    assert sans_gutenberg(g).strip() == "Corps."
    wiki = FR.model_copy(update={"lecteur": "wiki"})
    assert "|" not in nettoyer("{| tab\n| cellule\n|}\n" + "Texte suivi. " * 30, wiki,
                               CFG.nettoyage)[0]  # fmt: skip


def test_fenetres_bornees_et_coupees_en_fin_de_phrase():
    texte = "\n".join(" ".join(f"mot{i}" for i in range(n)) + "." for n in (5, 12, 7, 30, 3))
    phr, fen = decouper_document(texte, "fr", compter_mots, 15)
    assert all(j <= 15 for _, _, j in fen)
    assert fen[0][0] == 0 and fen[-1][1] == len(phr)
    assert all(a[1] == b[0] for a, b in zip(fen, fen[1:], strict=False))  # aucune phrase perdue
    for i0, i1, _ in fen:
        assert len(texte[phr[i0][0] : phr[i1 - 1][1]].split()) <= 15
    assert "".join(texte[a:b] for a, b in phr).replace(" ", "") == texte.replace(" ", "").replace(
        "\n", "")  # fmt: skip


def _z(t: str, s: str) -> list[Zone]:
    i = t.index(s)
    return [Zone(i, i + len(s), TypeNom.PER, frozenset({Detecteur.GLINER}))]


def test_regle_des_30_pour_cent(tmp_path):
    """Cas construit : « Orla » détectée 3 fois sur 9 (33 %), « Bram » 2 sur 8 (25 %)."""
    docs = [["M. Orla vient.", "Bram part."], ["M. Orla vient.", "Bram aussi."],
            ["M. Orla et Bram."], ["Orla, Orla, Orla.", "Orla encore et Orla."],
            ["Bram, Bram, Bram, Bram."]]  # fmt: skip
    detect = [[_z(docs[0][0], "Orla"), _z(docs[0][1], "Bram")],
              [_z(docs[1][0], "Orla"), _z(docs[1][1], "Bram")], [_z(docs[2][0], "Orla")],
              [[], []], [[]]]  # fmt: skip
    con = prop.ouvrir_chaines(tmp_path / "c.sqlite")
    for ts, zs in zip(docs, detect, strict=True):
        c = prop.comptes_detectes(ts, zs, 2)
        prop.ajouter_detectees(con, ((s, r, n, 1) for s, (n, r) in c.items()))
    a = prop.automate(prop.candidates(con, 2))
    prop.ajouter_occurrences(
        con, prop.compter_occurrences(a, (t for ts in docs for t in ts)).items()
    )
    assert [s for s, _ in prop.globales(con, 2, 0.30)] == ["Orla"]
    g = prop.automate(prop.globales(con, 2, 0.30))
    zs = prop.appliquer(g, "Orla, Orlando et Orla.", [])
    assert [(z.debut, z.fin) for z in zs] == [(0, 4), (17, 21)]  # limites de mot


def test_automate_sauve(tmp_path):
    a = prop.automate([("Zélie", 1)])
    prop.sauver(a, tmp_path / "a.pkl")
    a = prop.charger(tmp_path / "a.pkl")
    assert Counter(prop.compter_occurrences(a, ["Zélie, Zélie"])) == {"Zélie": 2}


def test_lecteur_wiki(tmp_path):
    xml = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/"><page><title>A</title>
<ns>0</ns><id>7</id><revision><text>'''Lorvane''' est un [[village]] {{Infobox|x=1}}.
{| class="wikitable"
| cellule
|}
[[Catégorie:Village]]Fin du texte.<ref>source</ref></text></revision></page>
<page><title>B</title><ns>0</ns><id>8</id><redirect title="A"/><revision><text>#R</text>
</revision></page><page><title>C</title><ns>4</ns><id>9</id><revision><text>méta</text>
</revision></page></mediawiki>"""
    chemin = tmp_path / "w.xml.bz2"
    chemin.write_bytes(bz2.compress(xml.encode()))
    s = SourcePretrain(langue="fr", lecteur="wiki", quota=1)
    docs = list(lecteurs.wiki(chemin, "wiki_fr", s, 0))
    assert [d["id"] for d in docs] == ["wiki_fr-7"]
    t = docs[0]["texte"]
    assert "Lorvane est un village" in t and "Fin du texte." in t
    assert not any(x in t for x in ("Infobox", "cellule", "Catégorie", "source", "{{"))


def _tar(chemin, membres: dict[str, bytes]) -> None:
    with tarfile.open(chemin, "w:gz") as t:
        for nom, octets in membres.items():
            info = tarfile.TarInfo(nom)
            info.size = len(octets)
            t.addfile(info, io.BytesIO(octets))


def test_lecteurs_dila_et_europarl(tmp_path):
    xml = (b"<TEXTE_JURI_JUDI><META><META_COMMUN><ID>JURITEXT1</ID></META_COMMUN></META>"
           b"<TEXTE><BLOC_TEXTUEL><CONTENU>Premier attendu.<br/>Second attendu.</CONTENU>"
           b"</BLOC_TEXTUEL></TEXTE></TEXTE_JURI_JUDI>")  # fmt: skip
    _tar(tmp_path / "cass.tar.gz", {"cass/a.xml": xml, "cass/lisez.txt": b"x"})
    s = SourcePretrain(langue="fr", lecteur="dila", quota=1)
    (d,) = lecteurs.dila(tmp_path / "cass.tar.gz", "dila_cass", s)
    assert d["id"] == "dila_cass-JURITEXT1" and "Premier attendu." in d["texte"]
    _tar(tmp_path / "fr-en.tgz", {"europarl-v7.fr-en.fr": b"Un.\nDeux.\n<P>\nTrois.\n",
                                  "europarl-v7.fr-en.en": b"One.\nTwo.\nThree.\n"})  # fmt: skip
    s = SourcePretrain(langue="en", lecteur="europarl", quota=1, lignes=2)
    docs = list(lecteurs.europarl(tmp_path / "fr-en.tgz", "europarl_en", s))
    assert [x["texte"] for x in docs] == ["One.\nTwo.", "Three."]


def test_debit_et_decision():
    cfg = CFG.model_copy(update={"jetons_total": 10_000})
    phrases = {"fr": ["Un deux trois."] * 50, "en": ["One two."] * 50}
    det = {"fr": {"gliner": lambda ts: None, "regle": lambda ts: None}, "en": {}}
    res = debit.mesurer(det, phrases, cfg, compter_mots, chauffe=2)
    assert res["gliner"] == "tout" and res["heures_gliner"] < 1
    assert set(res["langues"]["fr"]["detecteurs"]) == {"gliner", "regle"}
    lent = {"fr": {"gliner": lambda ts: __import__("time").sleep(0.05)}}
    cfg = cfg.model_copy(update={"jetons_total": 10**12})
    assert debit.mesurer(lent, phrases, cfg, compter_mots, chauffe=1)["gliner"] == "10pct"
