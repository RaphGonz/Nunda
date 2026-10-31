"""Commandes `ccm` (SPEC.md §3). Les commandes arrivent avec leurs phases."""

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, help="CCM : modèle de citation amnésique.")


@app.callback()
def main() -> None:
    """CCM : modèle de citation amnésique."""


@app.command()
def corpus(
    partie: Annotated[list[str] | None, typer.Option(help="Parties (toutes par défaut).")] = None,
    limite: Annotated[int | None, typer.Option(help="Dossiers par partie au plus.")] = None,
    sortie: Annotated[Path | None, typer.Option(help="Sortie (config par défaut).")] = None,
) -> None:
    """Écrit le corpus synthétique niveau 0 : PDF et vérité terrain (SPEC.md §12)."""
    from ccm.config import load_config
    from ccm.data.worldgen.corpus import ecrire_corpus
    from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion

    cfg = load_config("worldgen")
    sortie = sortie or Path(cfg.redaction.sortie)
    bilan = ecrire_corpus(cfg, charger_exclusion(EXCLUS_WIKIDATA), sortie, partie, limite)
    separation = bilan.pop("separation")
    for nom, b in bilan.items():
        typer.echo(
            f"{nom} : {b['dossiers']} dossiers, {b['pieces']} pièces, {b['rejetees']} rejetées, "
            f"{sum(b['questions'].values())} questions, "
            f"{len(b['erreurs_questions'])} erreurs de questions"
        )
    for k, v in separation.items():
        typer.echo(f"séparation : {k} communs : {', '.join(map(str, v))}")
    if separation or any(b["rejetees"] or b["erreurs_questions"] for b in bilan.values()):
        raise typer.Exit(1)


@app.command()
def ingest(
    sources: Annotated[list[Path], typer.Argument(help="Fichiers PDF ou dossiers de PDF.")],
    stock: Annotated[Path, typer.Option(help="Base SQLite du dossier (créée si absente).")],
) -> None:
    """Ingère des pièces PDF dans un stock : pièces, propositions, noms (§6), nombres,
    doublons, conflits (§5) ; reconstruit l'index BM25 (§7)."""
    from ccm.config import load_config
    from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
    from ccm.schema import ouvrir_stock
    from ccm.search.bm25 import construire_index, dossier_index

    cfg = load_config("ingest")
    con = ouvrir_stock(stock)
    try:
        fichiers = fichiers_pdf(sources)
        pieces = ingerer_fichiers(con, fichiers, cfg)
        n = con.execute("SELECT COUNT(*) FROM proposition").fetchone()[0]
        m = con.execute("SELECT COUNT(*) FROM mention").fetchone()[0]
        c = con.execute("SELECT COUNT(*) FROM arete WHERE type = 'CONFLIT'").fetchone()[0] // 2
        construire_index(con, dossier_index(stock), cfg, load_config("search"))
    finally:
        con.close()
    typer.echo(
        f"{len(fichiers)} fichiers, {len(pieces)} pièces ajoutées ; {n} propositions, {m} noms, "
        f"{c} conflits"
    )


@app.command()
def forget(
    noms: Annotated[list[str], typer.Argument(help="Noms normalisés à oublier.")],
    stock: Annotated[Path, typer.Option(help="Base SQLite du dossier.")],
) -> None:
    """Oublie des personnes : caviarde leurs mentions, VACUUM, reconstruit l'index (§5)."""
    from ccm.config import load_config
    from ccm.graph.oubli import oublier
    from ccm.schema import ouvrir_stock
    from ccm.search.bm25 import construire_index, dossier_index

    if not stock.exists():
        raise typer.BadParameter(f"base absente : {stock}")
    cfg = load_config("ingest")
    con = ouvrir_stock(stock)
    try:
        n = oublier(con, noms, cfg)
        construire_index(con, dossier_index(stock), cfg, load_config("search"))
    finally:
        con.close()
    typer.echo(f"{n} propositions caviardées")


@app.command()
def anonymize(
    question: Annotated[str, typer.Argument(help="Message de l'utilisateur.")],
    stock: Annotated[Path, typer.Option(help="Base SQLite du dossier.")],
    prop: Annotated[
        list[int] | None,
        typer.Option(help="Propositions du contexte, dans l'ordre (par défaut : toutes)."),
    ] = None,
    conv: Annotated[
        str | None, typer.Option(help="Conversation (contraintes MEME/DIFFERENT).")
    ] = None,
    graine: Annotated[int, typer.Option(help="Graine de la table de la conversation.")] = 0,
    sortie: Annotated[Path | None, typer.Option(help="Fichier JSON (sinon la sortie).")] = None,
) -> None:
    """Anonymise une question et des propositions : exemple JSON sans aucun nom (§4, §6)."""
    import sys

    from ccm.anonymize.exemple import anonymiser, lire_message
    from ccm.anonymize.table import TableConversation
    from ccm.config import load_config
    from ccm.schema import ouvrir_stock

    if not stock.exists():
        raise typer.BadParameter(f"base absente : {stock}")
    cfg = load_config("ingest")
    con = ouvrir_stock(stock)
    try:
        ids = prop or [
            p
            for (p,) in con.execute(
                "SELECT prop_id FROM proposition "
                "WHERE groupe_doublon IS NULL OR groupe_doublon = prop_id ORDER BY prop_id"
            )
        ]
        table = TableConversation(graine, cfg.anonymiseur.reservoir)
        ex = anonymiser(con, ids, lire_message(question, con, cfg), table, cfg, conv_id=conv)
    finally:
        con.close()
    texte = ex.model_dump_json(indent=1)
    if sortie:
        sortie.write_text(texte, encoding="utf-8")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # console Windows : cp1252 sans « ⟦ »
        typer.echo(texte)


@app.command()
def search(
    question: Annotated[str, typer.Argument(help="Message de l'utilisateur.")],
    stock: Annotated[Path, typer.Option(help="Base SQLite du dossier (index BM25 à côté).")],
    precedente: Annotated[
        list[str] | None, typer.Option(help="Messages précédents, du plus ancien au plus récent.")
    ] = None,
    citee: Annotated[list[int] | None, typer.Option(help="Propositions citées avant.")] = None,
    conv: Annotated[str | None, typer.Option(help="Conversation (contraintes).")] = None,
    jetons: Annotated[
        int | None, typer.Option(help="Budget de jetons (config par défaut).")
    ] = None,
    sans_trace: Annotated[bool, typer.Option(help="Ne pas écrire la table trace.")] = False,
    sortie: Annotated[Path | None, typer.Option(help="Fichier JSON (sinon la sortie).")] = None,
) -> None:
    """Recherche : propositions du contexte, dans l'ordre, avec leurs raisons (§7)."""
    import json
    import sys
    from dataclasses import asdict

    from ccm.config import load_config
    from ccm.schema import ouvrir_stock
    from ccm.search import retrieve as r
    from ccm.search.bm25 import charger_index, dossier_index

    if not stock.exists():
        raise typer.BadParameter(f"base absente : {stock}")
    cfg, cfg_s = load_config("ingest"), load_config("search")
    con = ouvrir_stock(stock)
    try:
        res = r.chercher(
            con,
            charger_index(dossier_index(stock)),
            r.lire_message(question, con, cfg),
            cfg_s,
            cfg,
            precedentes=[r.lire_message(m, con, cfg) for m in precedente or []],
            conv_id=conv,
            citees=frozenset(citee or []),
            jetons_max=jetons,
        )
        rid = None if sans_trace else r.ecrire_trace(con, res, question, conv)
        con.commit()
        pieces = dict(con.execute("SELECT prop_id, piece_id FROM proposition"))
    finally:
        con.close()
    texte = json.dumps(
        dict(
            reponse_id=rid,
            noms=res.noms,
            jetons=res.jetons,
            propositions=[dict(asdict(res.raisons[p]), piece_id=pieces[p]) for p in res.prop_ids],
        ),
        ensure_ascii=False,
        indent=1,
    )
    if sortie:
        sortie.write_text(texte, encoding="utf-8")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        typer.echo(texte)


@app.command()
def answer(
    question: Annotated[str | None, typer.Argument(help="Message de l'utilisateur.")] = None,
    stock: Annotated[Path, typer.Option(help="Base SQLite du dossier (index BM25 à côté).")] = ...,
    oracle: Annotated[
        Path | None,
        typer.Option(help="Dossier du corpus synthétique (vérité terrain) : modèle oracle."),
    ] = None,
    id: Annotated[str | None, typer.Option(help="Question du dossier (et historique).")] = None,
    synthese: Annotated[bool, typer.Option(help="Mode synthèse (§10 bis).")] = False,
    conv: Annotated[str | None, typer.Option(help="Conversation (contraintes).")] = None,
    graine: Annotated[int, typer.Option(help="Graine de la table de la conversation.")] = 0,
    suite: Annotated[bool, typer.Option(help="Affiche aussi les pas du modèle.")] = False,
) -> None:
    """Répond de bout en bout : recherche, anonymiseur, modèle, vérificateur (§2, §11)."""
    import sys
    import uuid

    from ccm.answer import repondre
    from ccm.config import load_config
    from ccm.model.oracle import Oracle
    from ccm.schema import ouvrir_stock
    from ccm.search.bm25 import charger_index, dossier_index

    if oracle is None:
        raise typer.BadParameter("seul le modèle oracle existe (phase 3) : --oracle DOSSIER")
    if not stock.exists():
        raise typer.BadParameter(f"base absente : {stock}")
    if question is None and id is None:
        raise typer.BadParameter("donner la question ou --id")
    o = Oracle(oracle)
    try:
        q = o.question(question, id)
    except KeyError as e:
        raise typer.BadParameter(e.args[0]) from None
    cfgs = (load_config(x) for x in ("ingest", "search", "grammar", "verify"))
    con = ouvrir_stock(stock)
    try:
        index = charger_index(dossier_index(stock))
        conv = conv or uuid.uuid4().hex
        r = repondre(con, index, o, q, *cfgs, conv_id=conv, synthese=synthese, graine=graine)
    finally:
        con.close()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for t in r.tours:
        if suite:
            typer.echo(f"pas du modèle : {' '.join(t.suite)}", err=True)
        if t.raison:
            typer.echo(f"oracle : abstention ({t.raison})", err=True)
    typer.echo(r.reponse.texte)
    if r.reponse.erreur:
        raise typer.Exit(1)


@app.command()
def modeles() -> None:
    """Télécharge les modèles de la détection des noms dans `runs/modeles/` (§6)."""
    from ccm.data.modeles import MODELES, telecharger

    ecrits = telecharger()
    typer.echo(f"{len(ecrits)} fichiers écrits dans {MODELES}")


@app.command()
def jeux() -> None:
    """Télécharge les jeux publics de réglage fin (§12) ; affiche tailles et empreintes."""
    from ccm.config import load_config
    from ccm.data.jeux import telecharger

    for jeu, nom, taille, empreinte in telecharger(load_config("donnees").racine):
        typer.echo(f"{jeu}\t{nom}\t{taille}\t{empreinte}")


@app.command()
def convertir(
    jeu: Annotated[str, typer.Argument(help="hotpot, squad ou finqa")],
    limite: Annotated[int, typer.Option(help="Questions par partie (0 : toutes).")] = 0,
) -> None:
    """Convertit un jeu public en exemples Parquet (§12), dans `racine/converti/<jeu>/`."""
    import json
    from itertools import islice

    from ccm.config import load_config
    from ccm.data import finqa, hotpot, squad_fr
    from ccm.data.publics import convertir_partie, remplir_cache, textes_de

    cfg = load_config("donnees")
    brut = cfg.racine / "brut" / jeu
    ecartes: dict[str, dict[str, int]] = {}
    if jeu == "hotpot":
        parties = {p: hotpot.lire(brut, p) for p in ("train", "validation")}
    elif jeu == "squad":
        parties = {"train": squad_fr.sans_reponse(brut / "train-v2.0.json"),
                   "validation": squad_fr.sans_reponse(brut / "dev-v2.0.json")}  # fmt: skip
    elif jeu == "finqa":
        parties = {}
        for p, f in (("train", "train"), ("validation", "dev"), ("test", "test")):
            parties[p], ecartes[p] = finqa.lire(brut / f"{f}.json")
    else:
        raise typer.BadParameter(f"jeu inconnu : {jeu}")
    lus = {p: list(islice(b, limite or None)) for p, b in parties.items()}
    cache = cfg.racine / "cache-zones.sqlite"
    icfg = load_config("ingest")
    det = icfg.detection.model_copy(
        update={"gliner": icfg.detection.gliner.model_copy(update={"lot": cfg.lot_gliner})}
    )
    remplir_cache((t for b in lus.values() for x in b for t in textes_de(x)), cache,
                  icfg.model_copy(update={"detection": det}), cfg.lot_detection)  # fmt: skip
    sortie = cfg.racine / "converti" / jeu
    bilan = {p: convertir_partie(b, sortie / p, cache, cfg, cfg.processus)
             | {"ecartes": ecartes.get(p, {})}
             for p, b in lus.items()}  # fmt: skip
    (sortie / "bilan.json").write_text(
        json.dumps(bilan, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    typer.echo(json.dumps(bilan))


if __name__ == "__main__":
    app()
