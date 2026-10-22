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
def modeles() -> None:
    """Télécharge les modèles de la détection des noms dans `runs/modeles/` (§6)."""
    from ccm.data.modeles import MODELES, telecharger

    ecrits = telecharger()
    typer.echo(f"{len(ecrits)} fichiers écrits dans {MODELES}")


if __name__ == "__main__":
    app()
