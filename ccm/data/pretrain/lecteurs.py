"""Lecteurs des sources (SPEC.md §12) : documents `{id, source, langue, texte}`, en flux.

Rien n'est décompressé sur le disque. Les formats des sources Hugging Face (colonnes) et de
MultiEURLEX sont à vérifier sur les fichiers figés (`telecharger --essai` de `brut`).
"""

import bz2
import gzip
import json
import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq

from ccm.config import CorpusConfig, DonneesConfig, SourcePretrain
from ccm.data import judilibre, legi
from ccm.data.droit import Texte
from ccm.data.pretrain.etat import tirage

Document = dict  # id, source, langue, texte

_ESPACES_NOMS = re.compile(r"^(?:Fichier|File|Image|Catégorie|Category|Portail|Modèle|Template):",
                           re.IGNORECASE)  # fmt: skip


def _sans_tables(wikitexte: str) -> str:
    """Retire les tables `{| … |}`, imbrications comprises."""
    out, profondeur, k = [], 0, 0
    for m in re.finditer(r"\{\||\|\}", wikitexte):
        if m.group() == "{|":
            if profondeur == 0:
                out.append(wikitexte[k : m.start()])
            profondeur += 1
        elif profondeur:
            profondeur -= 1
            if profondeur == 0:
                k = m.end()
    if profondeur == 0:
        out.append(wikitexte[k:])
    return "".join(out)


def texte_wiki(wikitexte: str) -> str:
    """Texte d'un article : sans tables, gabarits, références, fichiers ni catégories."""
    import mwparserfromhell

    code = mwparserfromhell.parse(_sans_tables(wikitexte))
    for t in code.filter_templates(recursive=False):
        try:
            code.remove(t)
        except ValueError:
            pass
    for t in code.filter_tags(recursive=False):
        if str(t.tag).lower() in ("ref", "gallery", "table", "math", "score", "timeline"):
            try:
                code.remove(t)
            except ValueError:
                pass
    for lien in code.filter_wikilinks(recursive=False):
        if _ESPACES_NOMS.match(str(lien.title).strip()):
            try:
                code.remove(lien)
            except ValueError:
                pass
    return code.strip_code(normalize=True, collapse=True)


def wiki(chemin: Path, source: str, s: SourcePretrain, graine: int) -> Iterator[Document]:
    """Articles (espace 0, sans redirection) d'un dump `pages-articles.xml.bz2`."""
    with bz2.open(chemin, "rb") as f:
        racine = None
        for evt, e in ET.iterparse(f, events=("start", "end")):
            if racine is None:
                racine = e
            if evt != "end" or (not e.tag.endswith("}page") and e.tag != "page"):
                continue
            ns = {c.tag.rsplit("}", 1)[-1]: c for c in e}
            if ns.get("ns") is not None and ns["ns"].text == "0" and "redirect" not in ns:
                id_ = f"{source}-{ns['id'].text}"
                if s.part >= 1 or tirage(graine, "part", id_) < s.part:
                    rev = ns.get("revision")
                    textes = [
                        c.text for c in (rev if rev is not None else ()) if c.tag.endswith("text")
                    ]
                    if textes and textes[0]:
                        brut = textes[0]
                        yield {"id": id_, "source": source, "langue": s.langue,
                               "texte": texte_wiki(brut)}  # fmt: skip
            racine.clear()  # la page lue ne reste pas en mémoire


def _valeur(v) -> str:
    if isinstance(v, list):
        return "\n\n".join(str(x) for x in v if x)
    if isinstance(v, dict):
        return ""
    return v or ""


def hf_parquet(chemins: list[Path], source: str, s: SourcePretrain) -> Iterator[Document]:
    """Une colonne de fichiers Parquet ; id stable : fichier et rang dans le fichier."""
    for chemin in chemins:
        rang = 0
        for lot in pq.ParquetFile(chemin).iter_batches(batch_size=256, columns=[s.colonne]):
            for v in lot.column(0).to_pylist():
                yield {"id": f"{source}-{chemin.stem}-{rang}", "source": source,
                       "langue": s.langue, "texte": _valeur(v)}  # fmt: skip
                rang += 1


def _texte_droit(t: Texte) -> str:
    """En-tête puis paragraphes ; les rangées de tableau sont retirées (§12, nettoyage)."""
    return "\n\n".join([t.tete, *(p for p, rangee in t.paragraphes if not rangee)])


def dila(archive: Path, source: str, s: SourcePretrain) -> Iterator[Document]:
    """Décisions d'un stock DILA (CASS, INCA, JADE, CAPP : déjà pseudonymisées)."""
    with tarfile.open(archive, "r|gz") as t:
        for m in t:
            if not (m.isfile() and m.name.endswith(".xml")):
                continue
            f = t.extractfile(m)
            if f is None:
                continue
            try:
                racine = ET.fromstring(f.read())
            except ET.ParseError:
                continue
            contenu = next(racine.iter("CONTENU"), None)
            if contenu is None:
                continue
            pars = [p for p, rangee in legi.paragraphes(contenu) if not rangee]
            id_ = racine.findtext("META/META_COMMUN/ID") or m.name
            yield {"id": f"{source}-{id_}", "source": source, "langue": s.langue,
                   "texte": "\n\n".join(pars)}  # fmt: skip


def europarl(archive: Path, source: str, s: SourcePretrain) -> Iterator[Document]:
    """Europarl v7 : un document = `s.lignes` lignes consécutives de la langue."""
    with tarfile.open(archive, "r:gz") as t:
        membre = next(m for m in t.getmembers() if m.name.endswith(f".{s.langue}"))
        f = t.extractfile(membre)
        lignes, n = [], 0
        for ligne in (b.decode("utf-8", "replace").strip() for b in f):
            if ligne and not ligne.startswith("<"):
                lignes.append(ligne)
            if len(lignes) == s.lignes:
                yield {"id": f"{source}-{n}", "source": source, "langue": s.langue,
                       "texte": "\n".join(lignes)}  # fmt: skip
                lignes, n = [], n + 1
        if lignes:
            yield {"id": f"{source}-{n}", "source": source, "langue": s.langue,
                   "texte": "\n".join(lignes)}  # fmt: skip


def _jsonl_tar(chemin: Path) -> Iterator[tuple[str, dict]]:
    """(nom du membre, ligne JSON) des fichiers `.jsonl` d'une archive tar.gz."""
    with tarfile.open(chemin, "r|gz") as t:
        for m in t:
            f = t.extractfile(m) if m.isfile() and m.name.endswith(".jsonl") else None
            if f is not None:
                for x in f:
                    yield m.name, json.loads(x)


def eurlex(chemins: list[Path], source: str, s: SourcePretrain) -> Iterator[Document]:
    """MultiEURLEX : lignes JSON (`celex_id`, `text` : chaîne ou {langue: texte}), seules, en
    Parquet ou dans l'archive tar.gz de Zenodo (un membre par langue : les autres sont sautés)."""
    for chemin in chemins:
        if chemin.name.endswith(".tar.gz"):
            for k, (nom, r) in enumerate(_jsonl_tar(chemin)):
                texte = r.get(s.colonne)
                if isinstance(texte, dict):
                    texte = texte.get(s.langue)
                elif any(p in {"en", "fr", "de", "it", "es", "nl"} and p != s.langue
                         for p in re.split(r"[/._-]", nom)):  # fmt: skip
                    continue
                if texte:
                    yield {"id": f"{source}-{r.get('celex_id') or k}", "source": source,
                           "langue": s.langue, "texte": texte}  # fmt: skip
            continue
        if chemin.suffix == ".parquet":
            lignes = (r for lot in pq.ParquetFile(chemin).iter_batches(batch_size=256)
                      for r in lot.to_pylist())  # fmt: skip
        else:
            ouvrir = gzip.open if chemin.suffix == ".gz" else open
            lignes = (json.loads(x) for x in ouvrir(chemin, "rt", encoding="utf-8"))
        for k, r in enumerate(lignes):
            texte = r.get(s.colonne)
            if isinstance(texte, dict):
                texte = texte.get(s.langue)
            if texte:
                id_ = r.get("celex_id") or f"{chemin.stem}-{k}"
                yield {"id": f"{source}-{id_}", "source": source, "langue": s.langue,
                       "texte": texte}  # fmt: skip


def cedh(archive: Path, source: str, s: SourcePretrain) -> Iterator[Document]:
    """ECtHR (archive.org, `dataset.zip`) : lignes JSON, `facts` = liste de paragraphes."""
    with zipfile.ZipFile(archive) as z:
        for nom in sorted(n for n in z.namelist() if n.endswith(".jsonl")):
            with z.open(nom) as f:
                for k, x in enumerate(f):
                    r = json.loads(x)
                    faits = r.get("facts") or []
                    if faits:
                        yield {"id": f"{source}-{Path(nom).stem}-{r.get('case_id', k)}",
                               "source": source, "langue": s.langue,
                               "texte": "\n\n".join(faits)}  # fmt: skip


def documents(source: str, s: SourcePretrain, cfg: CorpusConfig, dcfg: DonneesConfig
              ) -> Iterator[Document]:  # fmt: skip
    """Documents d'une source, lus dans `racine/brut/<dossier>/`."""
    dossier = dcfg.racine / "brut" / (s.dossier or source)
    fichiers = sorted(p for p in dossier.glob("*") if p.is_file() and p.suffix != ".part")
    if s.lecteur == "legi":
        archive = dcfg.racine / "brut" / "legi" / dcfg.legi.archive
        for t in legi.textes(archive, dcfg.legi.date_dump):
            yield {"id": f"legi-{t.piece_id}", "source": source, "langue": s.langue,
                   "texte": _texte_droit(t)}  # fmt: skip
    elif s.lecteur == "judilibre":
        for t in judilibre.textes(dcfg.racine):
            yield {"id": t.piece_id, "source": source, "langue": s.langue,
                   "texte": _texte_droit(t)}  # fmt: skip
    elif s.lecteur == "wiki":
        for f in fichiers:
            yield from wiki(f, source, s, cfg.graine)
    elif s.lecteur == "hf_parquet":
        yield from hf_parquet([f for f in fichiers if f.suffix == ".parquet"], source, s)
    elif s.lecteur == "dila":
        for f in fichiers:
            yield from dila(f, source, s)
    elif s.lecteur == "europarl":
        for f in fichiers:
            yield from europarl(f, source, s)
    elif s.lecteur == "eurlex":
        yield from eurlex(fichiers, source, s)
    elif s.lecteur == "cedh":
        for f in fichiers:
            yield from cedh(f, source, s)
