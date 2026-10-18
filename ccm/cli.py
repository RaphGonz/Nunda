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


if __name__ == "__main__":
    app()
