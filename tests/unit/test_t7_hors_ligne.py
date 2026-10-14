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

INFERENCE = ["ingest", "search", "anonymize", "model", "verify"]
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
