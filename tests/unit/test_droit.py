"""Droit français (SPEC.md §12) : LEGI en flux, Judilibre avec quotas et reprise, propositions."""

import gzip
import io
import json
import tarfile
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter

import pytest

from ccm.config import load_config
from ccm.data import judilibre, legi
from ccm.data.droit import ecrire_textes, net, ouvrir_droit
from ccm.ingest.segment import phrases
from ccm.schema import GenreProposition

DUMP = "2025-07-13"
RACINE = "legi/global/code_et_TNC_en_vigueur"


def _article(id_, etat="VIGUEUR", debut="2016-10-01", fin="2999-01-01",
             contenu="<p>Tout fait quelconque de l'homme oblige à réparer.<br/>Ce sont 2 phrases "
                     "de loi. Et une autre phrase ici.</p>") -> bytes:  # fmt: skip
    return (
        f"<ARTICLE><META><META_COMMUN><ID>{id_}</ID></META_COMMUN><META_SPEC><META_ARTICLE>"
        f"<NUM>1240</NUM><ETAT>{etat}</ETAT><DATE_DEBUT>{debut}</DATE_DEBUT>"
        f"<DATE_FIN>{fin}</DATE_FIN></META_ARTICLE></META_SPEC></META><CONTEXTE><TEXTE>"
        f"<TITRE_TXT c_titre_court='Code civil'>Code civil</TITRE_TXT></TEXTE></CONTEXTE>"
        f"<BLOC_TEXTUEL><CONTENU>{contenu}</CONTENU></BLOC_TEXTUEL></ARTICLE>"
    ).encode()


def _archive(chemin, membres) -> None:
    with tarfile.open(chemin, "w:gz") as t:
        for nom, octets in membres:
            info = tarfile.TarInfo(nom)
            info.size = len(octets)
            t.addfile(info, io.BytesIO(octets))


@pytest.fixture
def archive(tmp_path):
    a = f"{RACINE}/code_en_vigueur/LEGI/TEXT/LEGITEXT1/article/LEGI/ARTI"
    chemin = tmp_path / "dump.tar.gz"
    _archive(chemin, [
        (f"{a}/A1.xml", _article("A1")),
        (f"{a}/A2.xml", _article("A2", etat="MODIFIE")),
        (f"{a}/A3.xml", _article("A3", fin="2020-01-01")),
        (f"{a}/A4.xml", _article("A4", etat="VIGUEUR_DIFF", debut="2030-01-01")),
        (f"{a}/A5.xml", _article("A5", contenu="<table><tr><td>x</td><td>1</td></tr></table>")),
        (f"{RACINE}/TNC_en_vigueur/JORF/article/A6.xml", _article("A6")),
        (f"{RACINE}/code_en_vigueur/LEGI/TEXT/LEGITEXT1/texte/struct/S.xml", b"<pas-article/>"),
        ("legi/global/code_et_TNC_non_vigueur/code_non_vigueur/article/A7.xml", _article("A7")),
    ])  # fmt: skip
    return chemin


def test_legi_ne_garde_que_les_versions_en_vigueur_des_codes(archive):
    lus = Counter()
    gardes = {t.piece_id: t for t in legi.textes(archive, DUMP, lus)}
    assert sorted(gardes) == ["A1", "A5"]
    assert lus["pas_en_vigueur"] == 2 and lus["hors_periode"] == 1
    assert gardes["A1"].tete == "Code civil, article 1240"
    assert gardes["A5"].paragraphes == (("x | 1", True),)


def test_legi_rangee_vide_ignoree():
    html = "<CONTENU><table><tr><td/><td> </td></tr><tr><td>a</td><td/></tr></table></CONTENU>"
    assert legi.paragraphes(ET.fromstring(html)) == (("a | ", True),)


def test_legi_lu_en_flux_sans_rien_ecrire(archive):
    avant = sorted(archive.parent.rglob("*"))
    list(legi.textes(archive, DUMP))
    assert sorted(archive.parent.rglob("*")) == avant


def test_legi_propositions_dans_la_base_et_reprise(archive, tmp_path):
    stock = tmp_path / "droit.sqlite"
    con = ouvrir_droit(stock)
    bilan = ecrire_textes(con, legi.textes(archive, DUMP))
    assert bilan["ajoutes"] == 2
    lignes = con.execute(
        "SELECT texte, genre FROM proposition WHERE piece_id = 'A1' ORDER BY ordre"
    ).fetchall()
    assert lignes[0] == ("Code civil, article 1240", str(GenreProposition.EN_TETE))
    assert lignes[1][0] == "Tout fait quelconque de l'homme oblige à réparer."
    assert len(lignes) == 4  # en-tête, puis 3 phrases
    assert con.execute("SELECT type, rang FROM piece WHERE piece_id = 'A1'").fetchone() == (
        "LOI",
        1,
    )
    suites = con.execute("SELECT COUNT(*) FROM arete WHERE type = 'SUIVANTE'").fetchone()[0]
    assert suites == 3 + 1  # A1 : 3 ; A5 : 1
    n = con.execute("SELECT COUNT(*) FROM proposition").fetchone()[0]
    # Relancer n'ajoute rien.
    assert ecrire_textes(con, legi.textes(archive, DUMP))["deja_la"] == 2
    assert con.execute("SELECT COUNT(*) FROM proposition").fetchone()[0] == n
    con.close()


# Judilibre : API simulée, aucun appel réseau.
def _cfg(total=8, juridictions=None, fin="2024-02"):
    cfg = load_config("donnees")
    j = cfg.judilibre.model_copy(update={
        "total": total, "juridictions": juridictions or {"cc": "2024-01"}, "fin": fin,
        "lot": 3, "pause_s": 0.5, "attente_s": 10.0, "essais": 3,
    })  # fmt: skip
    return cfg.model_copy(update={"judilibre": j})


TEXTE = "Attendu que la cour statue.\r\n\r\nPar ces motifs rejette le pourvoi."


class Api:
    """`/scan` simulée : pour un jour, les décisions demandées, 10 au plus."""

    def __init__(self):
        self.appels = []
        self.pannes = []

    def __call__(self, url, cle):
        assert cle == "cle"
        self.appels.append(url)
        if self.pannes:
            raise self.pannes.pop(0)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert q["date_type"] == ["creation"] and q["date_start"] == q["date_end"]
        jour = q["date_start"][0]
        res = [{"id": f"{q['jurisdiction'][0]}{jour}-{i}", "decision_date": jour,
                "jurisdiction": "cc", "chamber": "civ1", "text": TEXTE}
               for i in range(min(int(q["batch_size"][0]), 10))]  # fmt: skip
        return {"results": res, "next_batch": None}


def _erreur(code, retry=None):
    return urllib.error.HTTPError("u", code, "x", {"Retry-After": retry} if retry else {}, None)


def test_judilibre_plafond_et_pause_entre_les_appels(tmp_path):
    api, attentes = Api(), []
    bilan = judilibre.telecharger(tmp_path, _cfg(total=8), "cle", api, attentes.append)
    assert bilan == {"fenetres": 2, "decisions": 8, "part_par_fenetre": 4}
    assert len(api.appels) == 8 and attentes == [0.5] * 8  # un par décision, puis plus rien
    with gzip.open(tmp_path / "brut/judilibre/cc/2024-01.jsonl.gz", "rt", encoding="utf-8") as f:
        assert len(f.readlines()) == 4


def test_judilibre_reparti_sur_le_mois_et_jour_vide_reporte(tmp_path):
    def api(url, cle):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        vides = {"2024-02-01", "2024-02-02"}
        jour = q["date_start"][0]
        return {"results": [] if jour in vides else
                [{"id": f"{jour}-{i}", "decision_date": jour, "text": "x"}
                 for i in range(int(q["batch_size"][0]))]}  # fmt: skip

    cfg = _cfg(total=29, juridictions={"cc": "2024-02"}, fin="2024-02")
    bilan = judilibre.telecharger(tmp_path, cfg, "cle", api, lambda s: None)
    assert bilan["decisions"] == 29  # les deux jours vides sont reportés
    with gzip.open(tmp_path / "brut/judilibre/cc/2024-02.jsonl.gz", "rt", encoding="utf-8") as f:
        jours = {json.loads(x)["decision_date"] for x in f}
    assert len(jours) == 27  # tous les jours non vides de février 2024


def test_judilibre_reprise_apres_arret_sans_redemander(tmp_path):
    api, cfg = Api(), _cfg(total=4)  # 2 par mois : deux appels par mois
    judilibre.telecharger(tmp_path, cfg, "cle", api, lambda s: None)
    n = len(api.appels)
    (tmp_path / "brut/judilibre/cc/2024-02.jsonl.gz").unlink()
    bilan = judilibre.telecharger(tmp_path, cfg, "cle", api, lambda s: None)
    assert len(api.appels) == n + 2 and "2024-02" in api.appels[-1]
    assert bilan["decisions"] == 4


def test_judilibre_429_respecte_retry_after(tmp_path):
    api, attentes = Api(), []
    api.pannes = [_erreur(429, "37")]
    judilibre.telecharger(tmp_path, _cfg(total=2, fin="2024-01"), "cle", api, attentes.append)
    assert 37.0 in attentes


def test_judilibre_quota_persistant_arrete_et_garde_le_fait(tmp_path):
    api, cfg = Api(), _cfg(total=4)
    judilibre.telecharger(tmp_path, cfg.model_copy(update={"judilibre": cfg.judilibre.model_copy(
        update={"fin": "2024-01", "total": 2})}), "cle", api, lambda s: None)  # fmt: skip
    api.pannes = [_erreur(429)] * 3
    with pytest.raises(judilibre.ArretJudilibre):
        judilibre.telecharger(tmp_path, cfg, "cle", api, lambda s: None)
    assert (tmp_path / "brut/judilibre/cc/2024-01.jsonl.gz").exists()
    assert not (tmp_path / "brut/judilibre/cc/2024-02.jsonl.gz").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_judilibre_refus_de_la_cle_sans_la_citer(tmp_path):
    api = Api()
    api.pannes = [_erreur(401)]
    with pytest.raises(judilibre.ArretJudilibre) as e:
        judilibre.telecharger(tmp_path, _cfg(), "cle", api, lambda s: None)
    assert "cle=" not in str(e.value) and "401" in str(e.value)


def test_judilibre_propositions_dans_la_base_avec_metadonnees(tmp_path):
    judilibre.telecharger(tmp_path, _cfg(total=4), "cle", Api(), lambda s: None)
    con = ouvrir_droit(tmp_path / "droit.sqlite")
    bilan = ecrire_textes(con, judilibre.textes(tmp_path))
    assert bilan["ajoutes"] == 4
    p = con.execute("SELECT piece_id FROM piece ORDER BY piece_id").fetchone()[0]
    lignes = [t for (t,) in con.execute(
        "SELECT texte FROM proposition WHERE piece_id = ? ORDER BY ordre", (p,))]  # fmt: skip
    assert lignes[0] == "Décision : Cour de cassation, civ1, 2024-01-01"
    assert lignes[1:] == ["Attendu que la cour statue.", "Par ces motifs rejette le pourvoi."]
    assert ecrire_textes(con, judilibre.textes(tmp_path))["ajoutes"] == 0
    con.close()


def test_identifiants_lus_dans_l_environnement_ou_le_fichier(tmp_path, monkeypatch):
    monkeypatch.delenv("PISTE_CLIENT_ID", raising=False)
    monkeypatch.delenv("PISTE_CLIENT_SECRET", raising=False)
    assert judilibre.lire_identifiants(tmp_path) is None
    fichier = tmp_path / judilibre.FICHIER_IDENTIFIANTS
    fichier.write_text("# mode d'emploi\nclient_id =\nclient_secret =\n", encoding="utf-8")
    assert judilibre.lire_identifiants(tmp_path) is None
    fichier.write_text("# client_id = non\nclient_id = i\nclient_secret = s=1\n", encoding="utf-8")
    assert judilibre.lire_identifiants(tmp_path) == ("i", "s=1")
    monkeypatch.setenv("PISTE_CLIENT_ID", "e")
    assert judilibre.lire_identifiants(tmp_path) == ("e", "s=1")


class _Reponse(io.BytesIO):
    pass


def test_jeton_garde_jusqu_a_sa_fin_puis_redemande():
    corps = []

    def ouvrir(req, timeout):
        corps.append(urllib.parse.parse_qs(req.data.decode()))
        return _Reponse(json.dumps({"access_token": f"j{len(corps)}", "expires_in": 3600}).encode())

    jetons = judilibre.Jetons("https://j.test", "i", "s", ouvrir)
    assert jetons() == "j1" and jetons() == "j1" and len(corps) == 1
    assert corps[0]["grant_type"] == ["client_credentials"] and corps[0]["client_secret"] == ["s"]
    jetons.fin = 0.0
    assert jetons() == "j2"


def test_jeton_refuse_sans_citer_le_secret():
    def ouvrir(req, timeout):
        raise _erreur(401)

    with pytest.raises(judilibre.ArretJudilibre) as e:
        judilibre.Jetons("https://j.test", "i", "secret", ouvrir)()
    assert "secret" not in str(e.value)


def test_nom_pseudonymise_ne_coupe_pas_la_phrase():
    cfg = load_config("ingest").segmentation
    texte = "M. X... a formé un pourvoi. La cour de J.P. Durand a statué."
    assert [texte[a:b] for a, b in phrases(texte, cfg)] == [
        "M. X... a formé un pourvoi.",
        "La cour de J.P. Durand a statué.",
    ]


def test_net_decode_les_entites():
    assert net("l&apos;article  1240\n&quot;x&quot;") == 'l\'article 1240 "x"'
