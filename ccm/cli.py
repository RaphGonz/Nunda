"""Commandes `ccm` (SPEC.md §3). Les commandes arrivent avec les phases 2 et 3."""

import typer

app = typer.Typer(no_args_is_help=True, help="CCM : modèle de citation amnésique.")


@app.callback()
def main() -> None:
    """CCM : modèle de citation amnésique."""


if __name__ == "__main__":
    app()
