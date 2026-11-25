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
    modele: Annotated[
        Path | None, typer.Option(help="Point de contrôle de A0 à la place de l'oracle.")
    ] = None,
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
        raise typer.BadParameter("--oracle DOSSIER requis : questions et vérité terrain du dossier")
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
        dec = None
        if modele is not None:
            from ccm.model.decodeur import charger_decodeur

            dec = charger_decodeur(modele)
        r = repondre(con, index, o, q, *cfgs, conv_id=conv, synthese=synthese, graine=graine,
                     modele=dec)  # fmt: skip
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
def questions(
    cible: Annotated[int, typer.Option(help="Exemples gardés visés, moitié par source.")] = 20_000,
    paralleles: Annotated[int, typer.Option(help="Requêtes simultanées au serveur.")] = 4,
    nom: Annotated[str, typer.Option(help="Nom du fichier JSONL.")] = "questions",
) -> None:
    """Questions de l'enseignant sur Légifrance et Judilibre, second passage compris (§12)."""
    from ccm.config import load_config
    from ccm.data.questions import generer

    typer.echo(generer(load_config("donnees").racine, cible, paralleles, nom))


@app.command()
def enseignant(
    modeles: Annotated[list[str] | None, typer.Argument(help="Modèles (tous par défaut).")] = None,
    n: Annotated[int, typer.Option(help="Nombre d'articles de Légifrance.")] = 10,
    nom: Annotated[str, typer.Option(help="Nom du fichier de résultats.")] = "comparaison",
) -> None:
    """Compare les modèles enseignants sur des articles de Légifrance (§12, §16)."""
    from ccm.config import load_config
    from ccm.data.enseignant import MODELES, comparer

    typer.echo(comparer(load_config("donnees").racine, modeles or list(MODELES), n, nom))


@app.command()
def jeux() -> None:
    """Télécharge les jeux publics de réglage fin (§12) ; affiche tailles et empreintes."""
    from ccm.config import load_config
    from ccm.data.jeux import telecharger

    for jeu, nom, taille, empreinte in telecharger(load_config("donnees").racine):
        typer.echo(f"{jeu}\t{nom}\t{taille}\t{empreinte}")


@app.command()
def convertir(
    jeu: Annotated[str, typer.Argument(help="hotpot, squad, finqa ou piaf")],
    limite: Annotated[int, typer.Option(help="Questions par partie (0 : toutes).")] = 0,
) -> None:
    """Convertit un jeu public en exemples Parquet (§12), dans `racine/converti/<jeu>/`."""
    import json
    from itertools import chain, islice

    from ccm.config import load_config
    from ccm.data import finqa, hotpot, squad_fr
    from ccm.data.publics import convertir_partie, detecter_minuscules, remplir_cache, textes_de
    from ccm.ner.union import detecter

    cfg = load_config("donnees")
    brut = cfg.racine / "brut" / jeu
    icfg = load_config("ingest")
    gliner = icfg.detection.gliner.model_copy(update={"lot": cfg.lot_gliner})
    det = icfg.detection.model_copy(update={"gliner": gliner})
    icfg = icfg.model_copy(update={"detection": det})
    en = icfg.model_copy(
        update={"detection": det.model_copy(update={"detecteurs": cfg.detecteurs_en})}
    )
    ecartes: dict[str, dict[str, int]] = {}
    if jeu == "hotpot":
        chaine, detection = "en", lambda ts: detecter(ts, en)
        lecteurs = {p: (lambda p=p: hotpot.lire(brut, p)) for p in ("train", "validation")}
    elif jeu == "squad":
        chaine, detection = "en", lambda ts: detecter(ts, en)
        lecteurs = {"train": lambda: squad_fr.sans_reponse(brut / "train-v2.0.json"),
                    "validation": lambda: squad_fr.sans_reponse(brut / "dev-v2.0.json"),
                    }  # fmt: skip
    elif jeu == "finqa":
        chaine = "minuscules"
        detection = lambda ts: detecter_minuscules(ts, en, cfg.seuil_minuscules)  # noqa: E731
        lecteurs = {}
        for p, f in (("train", "train"), ("validation", "dev"), ("test", "test")):
            lus, ecartes[p] = finqa.lire(brut / f"{f}.json")
            lecteurs[p] = lambda lus=lus: lus
    elif jeu == "piaf":
        chaine, detection = "fr", lambda ts: detecter(ts, icfg)
        lecteurs = {"train": lambda: squad_fr.avec_reponse(
            brut / "piaf-v1.2.json", "piaf", "fr", cfg.distracteurs, cfg.graine)}  # fmt: skip
    else:
        raise typer.BadParameter(f"jeu inconnu : {jeu}")

    def lire(p: str):
        return islice(lecteurs[p](), limite or None)

    cache = cfg.racine / f"cache-zones-{chaine}.sqlite"
    remplir_cache((t for x in chain.from_iterable(map(lire, lecteurs)) for t in textes_de(x)),
                  cache, detection, cfg.lot_detection)  # fmt: skip
    sortie = cfg.racine / "converti" / jeu
    bilan = {p: convertir_partie(lire(p), sortie / p, cache, cfg, cfg.processus)
             | {"ecartes": ecartes.get(p, {})} for p in lecteurs}  # fmt: skip
    (sortie / "bilan.json").write_text(
        json.dumps(bilan, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    typer.echo(json.dumps(bilan))


@app.command()
def legi(
    processus: Annotated[int | None, typer.Option(help="Processus de découpe.")] = None,
) -> None:
    """Découpe les articles en vigueur des codes (dump LEGI, lu en flux) en propositions (§12)."""
    import json
    from collections import Counter

    from ccm.config import load_config
    from ccm.data import legi as source
    from ccm.data.droit import ecrire_textes, ouvrir_droit, taille_disque

    cfg = load_config("donnees")
    archive = cfg.racine / "brut" / "legi" / cfg.legi.archive
    if not archive.exists():
        raise typer.BadParameter(f"archive absente : {archive} (ccm jeux)")
    stock = cfg.racine / cfg.stock_droit
    lus: Counter = Counter()
    con = ouvrir_droit(stock)
    try:
        bilan = ecrire_textes(
            con, source.textes(archive, cfg.legi.date_dump, lus), processus or cfg.processus
        )
    finally:
        con.close()
    typer.echo(json.dumps(bilan | dict(lus) | {"octets_archive": taille_disque(archive),
                                               "octets_stock": taille_disque(stock)}))  # fmt: skip


@app.command()
def judilibre(
    processus: Annotated[int | None, typer.Option(help="Processus de découpe.")] = None,
) -> None:
    """Échantillon de Judilibre par l'API de PISTE, avec reprise, puis découpe (§12)."""
    import json

    from ccm.config import load_config
    from ccm.data import judilibre as source
    from ccm.data.droit import ecrire_textes, ouvrir_droit, taille_disque

    cfg = load_config("donnees")
    ids = source.lire_identifiants(cfg.racine)
    if not ids:
        raise typer.BadParameter(
            f"identifiants absents : {cfg.racine / source.FICHIER_IDENTIFIANTS} ou l'environnement"
        )
    try:
        recu = source.telecharger(cfg.racine, cfg, source.Jetons(cfg.judilibre.oauth, *ids))
    except source.ArretJudilibre as e:
        typer.echo(f"arrêt : {e}. Relancer la commande reprend là où elle s'est arrêtée.", err=True)
        raise typer.Exit(1) from None
    stock = cfg.racine / cfg.stock_droit
    con = ouvrir_droit(stock)
    try:
        bilan = ecrire_textes(con, source.textes(cfg.racine), processus or cfg.processus)
    finally:
        con.close()
    dossier = cfg.racine / "brut" / "judilibre"
    typer.echo(json.dumps(recu | bilan | {"octets_decisions": taille_disque(dossier),
                                          "octets_stock": taille_disque(stock)}))  # fmt: skip


pretrain = typer.Typer(no_args_is_help=True, help="Corpus de pré-entraînement de B (§12, §14).")
app.add_typer(pretrain, name="pretrain")


def _pretrain():
    from ccm.config import load_config
    from ccm.data.pretrain.chaine import chemins

    dcfg, cfg = load_config("donnees"), load_config("pretrain").corpus
    return dcfg, cfg, chemins(dcfg.racine, cfg)


@pretrain.command("telecharger")
def pretrain_telecharger(
    figer: Annotated[bool, typer.Option(help="Résout les versions datées et les fige.")] = False,
) -> None:
    """Télécharge les sources (versions figées, SHA-256 contrôlés)."""
    from ccm.data.pretrain import sources

    dcfg, _, _ = _pretrain()
    if figer:
        for f in sources.figer(dcfg.racine):
            typer.echo(f"{f['dossier']}	{f['fichier']}	{f['taille']}	{f['sha256']}")
        return
    for d, nom, taille, empreinte in sources.telecharger(dcfg.racine):
        typer.echo(f"{d}	{nom}	{taille}	{empreinte}")


@pretrain.command("brut")
def pretrain_brut(
    essai: Annotated[int, typer.Option(help="Lit N documents par source, sans rien écrire.")] = 0,
) -> None:
    """Lit les sources jusqu'à leur quota et écrit `brut/`, mélangé par graine."""
    import json
    from itertools import islice

    from ccm.data.pretrain.chaine import ecrire_brut, melanger
    from ccm.data.pretrain.fenetres import compteur
    from ccm.data.pretrain.lecteurs import documents

    dcfg, cfg, ch = _pretrain()
    compter = compteur(cfg.decoupeur)
    if essai:
        for nom, s in cfg.sources.items():
            docs = list(islice(documents(nom, s, cfg, dcfg), essai))
            jetons = sum(compter([d["texte"]])[0] for d in docs)
            typer.echo(f"{nom}	{len(docs)} documents	{jetons} jetons")
        return
    flux = {nom: documents(nom, s, cfg, dcfg) for nom, s in cfg.sources.items()}
    quotas = {nom: s.quota for nom, s in cfg.sources.items()}
    etat = ecrire_brut(melanger(flux, quotas, compter, cfg.graine), ch.brut,
                       cfg.documents_par_paquet)  # fmt: skip
    typer.echo(json.dumps({"paquets": len(etat["paquets"])}))


@pretrain.command("canaris")
def pretrain_canaris() -> None:
    """Écrit les 600 canaris (liste hors du corpus) et insère les naturels : `brut+canaris/`."""
    import json

    from ccm.data import canaries
    from ccm.data.pretrain.chaine import inserer_canaris
    from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion
    from ccm.ner.detectors import RACINE

    _, cfg, ch = _pretrain()
    c = cfg.canaris_cfg
    if ch.canaris.exists():
        liste = canaries.lire(ch.canaris)
    else:
        fins = {lg: canaries.fins_candidates(RACINE / f"{d}.dic", lg, c, cfg.graine)
                for lg, d in c.lexiques.items()}  # fmt: skip
        liste = canaries.generer(c, fins, charger_exclusion(EXCLUS_WIKIDATA), cfg.graine)
    etat = inserer_canaris(ch, cfg, liste)
    typer.echo(json.dumps({"canaris": len(liste), "paquets": len(etat["paquets"])}))


@pretrain.command("debit")
def pretrain_debit() -> None:
    """Mesure chaque détecteur seul sur l'échantillon, extrapole, décide GLiNER : `debit.json`."""
    import json

    from ccm.config import load_config
    from ccm.data.pretrain import debit
    from ccm.data.pretrain.chaine import _paquets
    from ccm.data.pretrain.fenetres import compteur

    dcfg, cfg, ch = _pretrain()
    compter = compteur(cfg.decoupeur)
    phrases = debit.echantillon([p for _, p in _paquets(ch.brut)], cfg, compter)
    res = debit.mesurer(debit.detecteurs(load_config("ingest"), dcfg), phrases, cfg, compter)
    (ch.racine / "debit.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    typer.echo(json.dumps({"heures_gliner": res["heures_gliner"], "gliner": res["gliner"]}))


@pretrain.command("bpe")
def pretrain_bpe() -> None:
    """Entraîne le BPE de B (§8) sur le corpus anonymisé (`final/`)."""
    import json

    from ccm.config import load_config
    from ccm.data.pretrain.bpe import entrainer
    from ccm.data.pretrain.chaine import _paquets

    _, _, ch = _pretrain()
    b = load_config("pretrain").bpe
    paquets = [p for _, p in _paquets(ch.final)]
    typer.echo(json.dumps(entrainer(paquets, Path(b.dossier), b.vocabulaire, b.part, b.graine)))


@pretrain.command("essai-b")
def pretrain_essai_b(dossier: Path) -> None:
    """Essai à blanc du pré-entraînement de B (§13). Avec l'accord de Raphael seulement."""
    from ccm.train.b import lancer

    typer.echo(lancer(dossier, essai=True))


@pretrain.command("debit-b")
def pretrain_debit_b(
    dossier: Path, minutes: Annotated[float, typer.Option(help="Durée de la mesure.")] = 20.0
) -> None:
    """Mesure du débit du pré-entraînement de B à pleine taille (§13) : `debit.json`."""
    import json

    from ccm.train.b import lancer

    typer.echo(json.dumps(lancer(dossier, debit_s=minutes * 60), indent=1))


@pretrain.command("entrainer-b")
def pretrain_entrainer_b(
    dossier: Path,
    heures: Annotated[
        float | None, typer.Option(help="Arrêt (avec point de contrôle) après ce temps.")
    ] = None,
) -> None:
    """Pré-entraînement de B-S (§13), reprend au dernier point de contrôle. Avec l'accord
    de Raphael seulement."""
    from ccm.train.b import lancer

    typer.echo(lancer(dossier, heures=heures))


@pretrain.command("canaris-b")
def pretrain_canaris_b(point: Path, sortie: Path) -> None:
    """Mesure des canaris (§14) sur un point de contrôle de B."""
    import json

    from ccm.config import load_config
    from ccm.data import canaries
    from ccm.data.pretrain import bpe
    from ccm.data.pretrain.exemples import Jetons
    from ccm.eval.canaris_b import mesurer
    from ccm.model.b import ModeleB, attributs_b
    from ccm.train.b import recharger

    dcfg, cfg, _ = _pretrain()
    b = load_config("pretrain").bpe
    j = Jetons(bpe.charger(Path(b.dossier)))
    m = ModeleB(load_config("model_b_s").tronc, j.tok.get_vocab_size(),
                attributs_b(load_config("ingest")))  # fmt: skip
    recharger(point, m)
    res = mesurer(m.cuda().eval(), j, canaries.lire(dcfg.racine / cfg.canaris))
    sortie.write_text(json.dumps(res, indent=1), encoding="utf-8")
    typer.echo(json.dumps(res["par_groupe"], indent=1))


@pretrain.command("generer-b")
def pretrain_generer_b(point: Path, sortie: Path, n: int = 120) -> None:
    """Exemples de génération libre sur un point de contrôle de B."""
    import json

    from ccm.config import load_config
    from ccm.data.pretrain import bpe
    from ccm.data.pretrain.exemples import Jetons
    from ccm.eval.generation_b import exemples
    from ccm.model.b import ModeleB, attributs_b
    from ccm.train.b import recharger

    b = load_config("pretrain").bpe
    j = Jetons(bpe.charger(Path(b.dossier)))
    m = ModeleB(load_config("model_b_s").tronc, j.tok.get_vocab_size(),
                attributs_b(load_config("ingest")))  # fmt: skip
    recharger(point, m)
    res = exemples(m.cuda().eval(), j, n=n)
    sortie.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    typer.echo(json.dumps(res, indent=1, ensure_ascii=True))


@pretrain.command("chaine")
def pretrain_chaine(
    gliner: Annotated[
        str | None, typer.Option(help="tout ou 10pct (debit.json par défaut).")
    ] = None,
) -> None:
    """Nettoyer, fenêtres, détecter, propager, remplacer, relations, [P] : `final/`. Reprend."""
    import json

    from ccm.config import load_config
    from ccm.data.pretrain.chaine import chaine, detections

    dcfg, cfg, ch = _pretrain()
    if gliner is None:
        chemin = ch.racine / "debit.json"
        if not chemin.exists():
            raise typer.BadParameter("debit.json absent : lancer `ccm pretrain debit`")
        gliner = json.loads(chemin.read_text(encoding="utf-8"))["gliner"]
    icfg = load_config("ingest")
    res = chaine(ch, cfg, icfg, detections(icfg, dcfg), gliner, dcfg.lot_detection)
    typer.echo(json.dumps(res))


@pretrain.command("bilan")
def pretrain_bilan() -> None:
    """Jetons par source et par langue, rejets, noms et nombres, canaris : `bilan.json`."""
    import json

    from ccm.data.pretrain.chaine import bilan

    _, _, ch = _pretrain()
    res = bilan(ch)
    (ch.racine / "bilan.json").write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                          encoding="utf-8")  # fmt: skip
    typer.echo(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    app()
