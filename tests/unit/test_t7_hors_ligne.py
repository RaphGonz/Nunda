"""T7 (SPEC.md §14) : aucune connexion réseau dans les modules d'inférence (SPEC.md §3)."""

import ast
import importlib
import json
import pkgutil
import socket
import sys
from pathlib import Path

import pytest

import ccm
from ccm.schema import Exemple, ouvrir_stock

INFERENCE = ["ingest", "ner", "search", "anonymize", "model", "verify"]
INTERDITS = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "requests", "httpx", "aiohttp"}
EXEMPLE = Path(__file__).parent.parent / "golden" / "exemple_spec.json"


class ConnexionInterdite(AssertionError):
    pass


@pytest.fixture
def sans_reseau(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnexionInterdite(f"connexion réseau : {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def modules_inference():
    for paquet in INFERENCE:
        racine = f"ccm.{paquet}"
        yield racine
        chemin = importlib.import_module(racine).__path__
        for m in pkgutil.walk_packages(chemin, prefix=f"{racine}."):
            yield m.name


def test_le_garde_bloque(sans_reseau):
    with pytest.raises(ConnexionInterdite):
        socket.create_connection(("example.com", 80))


def test_t7_modules_inference_sans_connexion(sans_reseau, tmp_path):
    for nom in modules_inference():
        sys.modules.pop(nom, None)
        importlib.import_module(nom)
    ex = Exemple.model_validate(json.loads(EXEMPLE.read_text(encoding="utf-8")))
    assert ex.cible[-1] == "FIN"
    ouvrir_stock(tmp_path / "dossier.sqlite").close()


def test_t7_aucun_import_reseau():
    racine = Path(ccm.__file__).parent
    fautes = []
    for paquet in INFERENCE:
        for fichier in (racine / paquet).rglob("*.py"):
            for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
                if isinstance(noeud, ast.Import):
                    noms = [a.name for a in noeud.names]
                elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0:
                    noms = [noeud.module or ""]
                else:
                    continue
                fautes += [f"{fichier}: {n}" for n in noms if n.split(".")[0] in INTERDITS]
    assert not fautes


def test_t7_detection_des_noms_hors_ligne(sans_reseau):
    """Les modèles de l'étape 5 se chargent depuis le disque, réseau coupé."""
    from ccm.config import load_config
    from ccm.ner import detectors
    from ccm.ner.union import detecter

    cfg = load_config("ingest")
    if not (detectors.RACINE / cfg.detection.gliner.modele / "model.safetensors").exists():
        pytest.skip("modèles absents : `ccm modeles`")
    for f in (detectors._gliner, detectors._spacy, detectors._lexiques):
        f.cache_clear()
    zones = detecter(["Elodie Bamier a vu la SARL Delcoron."], cfg)[0]
    assert len(zones) == 2


def test_t7_recherche_hors_ligne(sans_reseau, tmp_path):
    """Index BM25, recherche et trace (§7), réseau coupé."""
    from ccm.anonymize.exemple import Message
    from ccm.config import load_config
    from ccm.graph.store import ajouter_mentions
    from ccm.schema import TypeNom
    from ccm.search.bm25 import charger_index, construire_index
    from ccm.search.retrieve import chercher, ecrire_trace

    cfg, cfg_s = load_config("ingest"), load_config("search")
    con = ouvrir_stock(tmp_path / "d.sqlite")
    con.execute("INSERT INTO piece (piece_id, type, rang) VALUES ('P1', 'RAPPORT', 0)")
    con.execute(
        "INSERT INTO proposition (piece_id, page, ordre, texte, genre, ocr_conf) "
        "VALUES ('P1', 1, 0, 'Jean Rival a signé le bail.', 'PHRASE', 1.0)"
    )
    ajouter_mentions(con, 1, [(0, 10, "Jean Rival", "jean rival", "PER", "regle")])
    construire_index(con, tmp_path / "i", cfg, cfg_s)
    q = Message("Qui a signé, Jean Rival ?", ((13, 23, TypeNom.PER),), ())
    res = chercher(con, charger_index(tmp_path / "i"), q, cfg_s, cfg)
    assert res.prop_ids == [1]
    ecrire_trace(con, res, q.texte)
