"""Chaîne du corpus de pré-entraînement (SPEC.md §12) sur un mini-corpus figé inventé.

Détecteur factice (liste de noms, plus « Orlimont » et « Tavrel » après « M. » seulement),
compteur d'un jeton par mot : ni GLiNER, ni spaCy, ni tokenizer à charger.
"""

import json
import re
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from ccm.config import SourcePretrain, load_config
from ccm.data import canaries
from ccm.data.pretrain.chaine import (
    Chemins,
    bilan,
    chaine,
    ecrire_brut,
    inserer_canaris,
    melanger,
)
from ccm.data.pretrain.etat import Etape, lire_lignes
from ccm.data.pretrain.fenetres import compter_mots
from ccm.data.pretrain.remplacer import tables_nn, tables_pp
from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion
from ccm.ner.detectors import Zone
from ccm.schema import RELATION_IDS, Detecteur, Relation, TexteMarque, TypeNom

GOLDEN = Path(__file__).parent.parent / "golden" / "pretrain" / "documents.jsonl"
ICFG = load_config("ingest")
NOMS = re.compile(r"Albertine Vasseron|Vasseron|Corvalis Industries|Corbelune|Edmund Quarrish|"
                  r"Quarrish|Halvery Mills|(?<=M\. )(?:Orlimont|Tavrel)")  # fmt: skip
FINS = {"fr": [f"fin{c}" for c in "abcdefgh"], "en": [f"end{c}" for c in "abcdefgh"]}


def detecter(textes: list[str]) -> list[list[Zone]]:
    d = frozenset({Detecteur.GLINER})
    return [[Zone(*m.span(), TypeNom.PER, d) for m in NOMS.finditer(t)] for t in textes]


DETECTION = dict.fromkeys(("fr", "fr_sans_gliner", "en", "en_sans_gliner"), detecter)


def documents() -> list[dict]:
    return [json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines()]


def config(**maj):
    base = load_config("pretrain").corpus
    sources = {"essai_fr": SourcePretrain(langue="fr", lecteur="legi", quota=10**9),
               "essai_en": SourcePretrain(langue="en", lecteur="legi", quota=10**9)}  # fmt: skip
    can = base.canaris_cfg.model_copy(update={"par_frequence": 2, "frequences": (1, 2),
                                              "part_fr": 0.5})  # fmt: skip
    net = base.nettoyage.model_copy(update={"longueur_min": 40})
    return base.model_copy(update={
        "documents_par_paquet": 4, "processus": 0, "decoupeur": "mots", "jetons_fenetre": 60,
        "reserve_canari": 16, "nettoyage": net, "sources": sources, "canaris_cfg": can,
    } | maj)  # fmt: skip


def construire(racine: Path, cfg, arret=None, mode: str = "tout") -> Chemins:
    ch = Chemins(racine / "pretrain", racine / "canaris" / "canaris.json")
    ecrire_brut(documents(), ch.brut, cfg.documents_par_paquet)
    if not ch.canaris.exists():
        liste = canaries.generer(cfg.canaris_cfg, FINS, charger_exclusion(EXCLUS_WIKIDATA),
                                 cfg.graine)  # fmt: skip
        inserer_canaris(ch, cfg, liste)
    chaine(ch, cfg, ICFG, DETECTION, mode, 100, arret)
    return ch


def finales(ch: Chemins) -> list[dict]:
    e = Etape(ch.final)
    return [x for n in e.paquets() for x in lire_lignes(e.chemin_paquet(n))]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return construire(tmp_path_factory.mktemp("corpus"), config())


def test_aucun_nom_detecte_dans_le_final(corpus):
    """Toute surface détectée dans un document est absente de ses fenêtres finales (sauf les
    canaris forcés, en clair par construction)."""
    forces = [c for c in canaries.lire(corpus.canaris) if c["genre"] == "force"]
    det = Etape(corpus.detecte)
    surfaces: dict[str, set] = {}
    for n in det.paquets():
        for d in lire_lignes(det.chemin_paquet(n)):
            for (a, b), zs in zip(json.loads(d["phrases"]), json.loads(d["zones"]), strict=True):
                surfaces.setdefault(d["id"], set()).update(d["texte"][a:b][x:y] for x, y, _ in zs)
    lignes = finales(corpus)
    assert lignes and any(surfaces.values())
    for x in lignes:
        texte = x["texte"]
        for c in forces:
            texte = texte.replace(c["phrase"], "")
        for s in surfaces[x["document"]]:
            assert not re.search(rf"(?<!\w){re.escape(s)}(?!\w)", texte), (x["id"], s)
        TexteMarque(texte=texte, marques=json.loads(x["marques"]))  # marqueurs cohérents


def test_regle_des_30_pour_cent(corpus):
    """Orlimont : détecté 2 fois sur 4 (50 %), masqué partout ; Tavrel : 2 sur 7 (29 %),
    reste là où il n'est pas détecté."""
    par_doc = {}
    for x in finales(corpus):
        par_doc[x["document"]] = par_doc.get(x["document"], "") + x["texte"]
    assert "Orlimont" not in par_doc["fr-03"] and "Orlimont" in documents()[3]["texte"]
    assert "Tavrel" in par_doc["fr-06"]
    assert "Tavrel" not in par_doc["fr-04"] + par_doc["fr-05"]  # propagation dans le document
    assert Etape(corpus.travail / "globales").etat["globales"] >= 1


def test_rejets_et_doublons(corpus):
    """fr-11 copie fr-09 ; une copie qui reçoit un canari naturel n'est plus un doublon."""
    b = bilan(corpus)
    naturels = {i for c in canaries.lire(corpus.canaris) if c["genre"] == "naturel"
                for i in c["documents"]}  # fmt: skip
    doublons = 0 if naturels & {"fr-09", "fr-11"} else 1
    assert b["rejets"] == {"trop court": 1} | ({"doublon": 1} if doublons else {})
    assert set(b["parts_langues"]) == {"fr", "en"}
    assert b["canaris_forces_trouves"] == b["canaris_forces_attendus"] == 6
    assert b["documents_naturels_trouves"] == b["documents_naturels_attendus"] == 6


def test_fenetres_et_propositions(corpus):
    cfg = config()
    lignes = finales(corpus)
    avec_p = {x["document"] for x in lignes if x["a_p"]}
    docs = {x["document"] for x in lignes}
    assert 0 < len(avec_p) < len(docs)  # environ la moitié (tirage par id)
    for x in lignes:
        assert x["jetons"] <= cfg.jetons_fenetre
        sans_marques = re.sub(r"⟦\d+⟧", "X", x["texte"]).replace("[P]", "").replace("[/P]", "")
        assert len(sans_marques.split()) <= cfg.jetons_fenetre
        n = x["texte"].count("[P]")
        assert n == x["texte"].count("[/P]") == x["n_props"]
        assert (n > 0) == x["a_p"]
        if n:
            pp = tables_pp(n)
            assert pp[1, 1] & (1 << (RELATION_IDS[Relation.MEME_PROPOSITION][0] - 1))
            assert all(pp[i, j] & (1 << (RELATION_IDS[Relation.MEME_PIECE][0] - 1))
                       for i in range(1, n + 1) for j in range(1, n + 1))  # fmt: skip
            if n > 1:
                assert pp[1, 2] & (1 << (RELATION_IDS[Relation.SUIVANTE][0] - 1))
                assert pp[2, 1] & (1 << (RELATION_IDS[Relation.SUIVANTE][-1] - 1))
            if n > 2:
                assert not pp[1, 3] & (1 << (RELATION_IDS[Relation.SUIVANTE][0] - 1))


def test_relations_entre_noms(corpus):
    """« Albertine Vasseron » et « Vasseron » : même famille ou inclusion, dans la table NN."""
    vues = 0
    for x in finales(corpus):
        nn = tables_nn(x["noms"], json.loads(x["nn"]))
        assert all(nn[k, k] == 1 for k in range(1, x["noms"] + 1))
        vues += int((nn[1:, 1:] > 1).any())
    assert vues >= 1


def test_part_p_proche_de_la_moitie():
    from ccm.data.pretrain.etat import tirage

    n = sum(tirage(0, "p", f"doc-{i}") < 0.5 for i in range(10_000))
    assert 4_800 < n < 5_200


def test_reprise_octet_pour_octet(tmp_path, corpus):
    """Coupure après le paquet 1 de chaque passe : la relance donne les mêmes fichiers."""
    cfg = config()

    class Coupure(Exception):
        pass

    def couper(etape, n):
        if n == 1 and etape not in vus:
            vus.add(etape)
            raise Coupure

    vus: set = set()
    for _ in range(4):
        try:
            ch = construire(tmp_path, cfg, couper)
            break
        except Coupure:
            (tmp_path / "pretrain" / "final" / "paquet-00099.parquet.part").parent.mkdir(
                parents=True, exist_ok=True)  # fmt: skip
            (tmp_path / "pretrain" / "final" / "paquet-00099.parquet.part").write_bytes(b"x")
    assert vus == {"detecte", "occurrences", "final"}
    a = sorted(p.relative_to(corpus.racine) for p in (corpus.racine / "final").glob("*.parquet"))
    b = sorted(p.relative_to(ch.racine) for p in (ch.racine / "final").glob("*.parquet"))
    assert a == b and a
    for p in a:
        assert (corpus.racine / p).read_bytes() == (ch.racine / p).read_bytes()
    assert not list((ch.racine / "final").glob("*.part"))


def test_mode_10pct(tmp_path):
    ch = construire(tmp_path, config(), mode="10pct")
    assert finales(ch)
    b = bilan(ch)
    assert all(not k.endswith("_total") or v > 0 for k, v in b["ratees_sans_gliner"].items())


def test_processus_fils(tmp_path, corpus):
    """Même résultat avec des processus fils."""
    ch = construire(tmp_path, config(processus=2))
    for p in sorted((corpus.racine / "final").glob("*.parquet")):
        assert pq.read_table(p).equals(pq.read_table(ch.racine / "final" / p.name))


def test_melanger_quotas():
    flux = {"a": iter([{"texte": "un deux"}] * 10), "b": iter([{"texte": "un"}] * 10)}
    docs = list(melanger(flux, {"a": 4, "b": 100}, compter_mots, 0))
    assert sum(d["texte"] == "un deux" for d in docs) == 2  # arrêt au quota
    assert sum(d["texte"] == "un" for d in docs) == 10  # source épuisée


def test_liste_des_canaris_hors_du_corpus(corpus):
    assert corpus.canaris.exists() and corpus.racine not in corpus.canaris.parents
    liste = canaries.lire(corpus.canaris)
    temoin = json.dumps(liste[0]["fins"]).encode()
    for p in corpus.racine.rglob("*"):
        assert p.name != corpus.canaris.name
        if p.is_file() and p.suffix in (".json", ".parquet"):
            assert temoin not in p.read_bytes(), p
    # Les naturels sont dans le brut, une fois par document choisi.
    brut = {d["id"]: d["texte"] for _, p in [(0, x) for x in sorted(
        (corpus.racine / "brut+canaris").glob("*.parquet"))] for d in lire_lignes(p)}  # fmt: skip
    for c in liste:
        if c["genre"] == "naturel":
            assert all(brut[i].count(c["phrase"]) == 1 for i in c["documents"])


def test_doublon_entre_paquets(tmp_path):
    """Un paquet par document : la copie fr-11 de fr-09 tombe dans un autre paquet.

    Graine 3 : ni fr-09 ni fr-11 ne reçoit de canari naturel (sinon pas de doublon).
    """
    ch = construire(tmp_path, config(documents_par_paquet=1, graine=3))
    assert bilan(ch)["rejets"] == {"trop court": 1, "doublon": 1}


def test_bpe_sur_le_final(tmp_path, corpus):
    """BPE de B (§8) : spéciaux en tête et d'un seul jeton, aucun marqueur ⟦k⟧ ni surface
    détectée dans son vocabulaire (hors canaris forcés), aller-retour exact."""
    from ccm.data.pretrain import bpe

    paquets = [Etape(corpus.final).chemin_paquet(n) for n in Etape(corpus.final).paquets()]
    b = bpe.entrainer(paquets, tmp_path, 400, 1.0, 0)
    tok = bpe.charger(tmp_path)
    assert b["fenetres"] == len(finales(corpus)) and b["vocabulaire"] <= 400
    assert [tok.token_to_id(s) for s in bpe.SPECIAUX] == list(range(len(bpe.SPECIAUX)))
    x = finales(corpus)[0]
    t = bpe.texte_bpe(x["texte"], json.loads(x["marques"]))
    assert "⟦" not in t and tok.decode(tok.encode(t).ids, skip_special_tokens=False) == t
    ids = tok.encode("[P] ⟨PER⟩ a vu ⟨LIEU⟩ le ⟨DATE⟩ [/P]").ids
    assert all(tok.token_to_id(s) in ids for s in ("[P]", "⟨PER⟩", "⟨LIEU⟩", "⟨DATE⟩", "[/P]"))
    vocab = {tok.decoder.decode([v]) for v in tok.get_vocab()}
    assert not any("⟦" in v for v in vocab)
    # tirage partiel : même graine, mêmes fenêtres
    assert list(bpe.textes(paquets, 0.5, 0)) == list(bpe.textes(paquets, 0.5, 0))
