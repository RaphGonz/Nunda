"""Réglage fin de A0 (SPEC.md §13) : boucle d'entraînement (un contexte par passe avant,
accumulation pour le lot), échauffement, points de contrôle.

`python -m ccm.train.a0 essai` : essai à blanc (200 pas sur 1 000 exemples, perte en baisse,
point de contrôle rechargé) puis mesure du débit pendant 20 minutes (§13, « Ordre de
lancement et coût »). Le dossier `runs/<date>-a0-essai/` reçoit la configuration, le commit,
les paquets, `metrics.jsonl` et le point de contrôle.
`python -m ccm.train.a0 surapprentissage` : 8 exemples synthétiques appris par cœur."""

import datetime
import itertools
import json
import pickle
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import torch

from ccm.model.a0 import ModeleA0, optimiseur, perte
from ccm.train.chargeur import Tirage

SMOLLM = "HuggingFaceTB/SmolLM2-360M"
JETONS_LOT = 8000  # RTX 3090 : 5,1 contextes/s ; 10 000 déborde de la mémoire


def ordonnanceur(
    opt: torch.optim.Optimizer, echauffement: int
) -> torch.optim.lr_scheduler.LambdaLR:
    """Échauffement linéaire sur `echauffement` pas, puis pas constant (§13 ne fixe pas de
    décroissance pour la phase 4)."""
    return torch.optim.lr_scheduler.LambdaLR(opt, lambda i: min(1.0, (i + 1) / echauffement))


def paquets(tirages: Sequence[Tirage], jetons: int | None) -> list[list[Tirage]]:
    """Contextes d'un pas groupés par longueur ; un paquet complété à droite tient dans
    `jetons` (None : un contexte par passe)."""
    if jetons is None:
        return [[t] for t in tirages]
    out: list[list[Tirage]] = []
    for t in sorted(tirages, key=lambda t: len(t.encodage.input_ids)):
        n = len(t.encodage.input_ids)
        if out and (len(out[-1]) + 1) * n <= jetons:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def entrainer(modele: ModeleA0, tirages: Sequence[Tirage], pas: int, accumulation: int = 1,
              journal: Callable[[int, float], None] | None = None, opt=None, sched=None,
              debut: int = 0, jetons_lot: int | None = None, details: list | None = None,
              **lr) -> list[float]:  # fmt: skip
    """`pas` mises à jour à partir du pas `debut`, exemples pris en boucle (le pas i lit les
    exemples i·accumulation et suivants) ; rend la perte moyenne de chaque pas. `details`
    reçoit (source, genre, perte) de chaque contexte."""
    opt = opt or optimiseur(modele, **lr)
    dev = modele.lex.weight.device
    bf16 = dev.type == "cuda"
    modele.train()
    pertes = []
    for i in range(debut, debut + pas):
        total = 0.0
        lus = [tirages[k % len(tirages)] for k in range(i * accumulation, (i + 1) * accumulation)]
        for paquet in paquets(lus, jetons_lot):
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=bf16):
                sorties = modele.lot([t.encodage for t in paquet])
                ps = [perte(s, t.encodage, t.exemple.justificatives)["total"]
                      for s, t in zip(sorties, paquet, strict=True)]  # fmt: skip
                p = sum(ps)
            if details is not None:
                details += [(t.source, t.genre, x.item()) for t, x in zip(paquet, ps, strict=True)]
            (p / accumulation).backward()
            total += p.item() / accumulation
        torch.nn.utils.clip_grad_norm_(modele.parameters(), 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        if sched is not None:
            sched.step()
        pertes.append(total)
        if journal:
            journal(i, total)
    return pertes


# Points de contrôle : poids entraînés seulement (LoRA et modules nouveaux), optimiseur, pas.
def poids_entraines(modele: ModeleA0) -> dict[str, torch.Tensor]:
    return {n: p.detach().cpu() for n, p in modele.named_parameters() if p.requires_grad}


def sauver(chemin: Path, modele: ModeleA0, opt, sched, pas: int) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    etat = {"poids": poids_entraines(modele), "opt": opt.state_dict(), "pas": pas,
            "sched": sched.state_dict() if sched is not None else None}  # fmt: skip
    torch.save(etat, chemin.with_suffix(".tmp"))
    chemin.with_suffix(".tmp").replace(chemin)


def recharger(chemin: Path, modele: ModeleA0, opt=None, sched=None) -> int:
    """Recharge les poids entraînés (tous, et rien d'autre), puis l'optimiseur ; rend le pas."""
    etat = torch.load(chemin, map_location="cpu", weights_only=True)
    attendus = {n for n, p in modele.named_parameters() if p.requires_grad}
    if set(etat["poids"]) != attendus:
        raise ValueError(f"poids différents : {sorted(set(etat['poids']) ^ attendus)[:5]}")
    modele.load_state_dict(etat["poids"], strict=False)
    if opt is not None:
        opt.load_state_dict(etat["opt"])
    if sched is not None and etat["sched"] is not None:
        sched.load_state_dict(etat["sched"])
    return etat["pas"]


@torch.no_grad()
def pertes_eval(modele: ModeleA0, tirages: Sequence[Tirage]) -> list[float]:
    dev = modele.lex.weight.device
    modele.eval()
    out = []
    for t in tirages:
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            out.append(
                perte(modele(t.encodage), t.encodage, t.exemple.justificatives)["total"].item()
            )
    modele.train()
    return out


# Données réelles.
def _tokenizer():
    from transformers import AutoTokenizer

    from ccm.anonymize.encode import Vocabulaire
    from ccm.config import load_config

    tok = AutoTokenizer.from_pretrained(SMOLLM)
    voc = Vocabulaire(load_config("model_a0"), load_config("ingest"), len(tok))
    return voc, lambda s: tok(s, add_special_tokens=False).input_ids


def chargeur_reel(voc, decouper, dossiers: int = 20):
    """Sources publiques présentes sur le disque, et `dossiers` dossiers synthétiques de la
    partie d'entraînement rédigés en mémoire (le corpus n'est pas écrit sur le disque)."""
    from ccm.config import load_config
    from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion, generer_monde
    from ccm.data.worldgen.pieces import rediger_dossier
    from ccm.data.worldgen.questions import poser_questions
    from ccm.train.chargeur import Chargeur, SourceSynthetique, sources_disponibles

    icfg, wcfg = load_config("ingest"), load_config("worldgen")
    exclus, g0 = charger_exclusion(EXCLUS_WIKIDATA), wcfg.corpus["entrainement"].graine
    ds = [rediger_dossier(generer_monde(g0 + i, "entrainement", wcfg, exclus), wcfg)
          for i in range(dossiers)]  # fmt: skip
    sources = sources_disponibles(load_config("donnees"), icfg)
    sources["synthetique"] = SourceSynthetique([(d, poser_questions(d, wcfg)) for d in ds], icfg)
    return Chargeur(sources, load_config("finetune").chargeur, icfg, load_config("search"),
                    load_config("grammar"), voc, decouper)  # fmt: skip


def _dossier_run(nom: str) -> Path:
    racine = Path(__file__).resolve().parents[2]
    d = racine / "runs" / f"{datetime.date.today().isoformat()}-{nom}"
    d.mkdir(parents=True, exist_ok=True)
    for c in ("finetune", "model_a0", "ingest", "search", "grammar"):
        shutil.copy(racine / "configs" / f"{c}.yaml", d / f"{c}.yaml")
    run = lambda *a: subprocess.run(a, cwd=racine, capture_output=True, text=True).stdout  # noqa: E731
    (d / "commit.txt").write_text(run("git", "rev-parse", "HEAD") + run("git", "status", "--short"))
    (d / "paquets.txt").write_text(run("uv", "pip", "freeze"))
    return d


def essai(exemples: int = 1000, pas: int = 200, minutes: float = 20.0, accumulation: int = 16,
          echauffement: int = 500, epoques: int = 3) -> dict:  # fmt: skip
    from ccm.config import load_config
    from ccm.model.a0 import charger_smollm

    run = _dossier_run("a0-essai")
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    voc, decouper = _tokenizer()

    t0 = time.time()
    cache = run / "tirages.pkl"  # mêmes exemples d'un essai à l'autre (époque 0, graine fixée)
    ch = None if cache.exists() else chargeur_reel(voc, decouper)
    tirages = (
        pickle.loads(cache.read_bytes())
        if ch is None
        else list(itertools.islice(ch.epoque(0, int(exemples * 1.1)), exemples))
    )
    if ch is not None:
        cache.write_bytes(pickle.dumps(tirages))
    t_donnees = time.time() - t0
    longueurs = sorted(len(t.encodage.input_ids) for t in tirages)
    ecrire(
        etape="donnees",
        exemples=len(tirages),
        secondes=t_donnees,
        bilan=dict(ch.bilan) if ch else None,
        jetons_moyen=sum(longueurs) / len(longueurs),
        jetons_max=longueurs[-1],
    )
    moyen = sum(longueurs) / len(longueurs)
    print(f"{len(tirages)} exemples en {t_donnees:.0f} s ; T moyen {moyen:.0f}", flush=True)

    torch.manual_seed(0)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modele = charger_smollm(voc, SMOLLM).to(dev)
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, echauffement)

    # 1. Essai à blanc.
    t0 = time.time()

    def journal(i, x):
        ecrire(etape="essai", pas=i, perte=x, lr=sched.get_last_lr()[0], secondes=time.time() - t0)
        if i % 10 == 0 or i == pas - 1:
            print(f"pas {i} perte {x:.4f}", flush=True)

    pertes = entrainer(
        modele, tirages, pas, accumulation, journal, opt, sched, jetons_lot=JETONS_LOT
    )
    t_essai = time.time() - t0
    debut, fin = sum(pertes[:20]) / 20, sum(pertes[-20:]) / 20

    # 2. Point de contrôle : sauvé, rechargé dans un modèle neuf, mêmes pertes.
    pc = run / f"pas-{pas}.pt"
    sauver(pc, modele, opt, sched, pas)
    temoins = tirages[:8]
    avant = pertes_eval(modele, temoins)
    torch.manual_seed(1)
    neuf = charger_smollm(voc, SMOLLM).to(dev)
    opt2 = optimiseur(neuf)
    pas_relu = recharger(pc, neuf, opt2, ordonnanceur(opt2, echauffement))
    apres = pertes_eval(neuf, temoins)
    ecart = max(abs(a - b) for a, b in zip(avant, apres, strict=True))
    del neuf, opt2
    torch.cuda.empty_cache()
    ecrire(etape="point_de_controle", pas=pas_relu, ecart_max=ecart, avant=avant, apres=apres)
    print(
        f"perte {debut:.3f} -> {fin:.3f} ; point de contrôle rechargé, écart {ecart:.2e}",
        flush=True,
    )

    # 3. Débit : `minutes` d'entraînement à pleine taille (lot de 16 contextes).
    if dev == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    t0, i, contextes, jetons = time.time(), pas, 0, 0
    while time.time() - t0 < 60 * minutes:
        p = entrainer(modele, tirages, 1, accumulation, None, opt, sched, i, JETONS_LOT)[0]
        lus = [tirages[k % len(tirages)] for k in range(i * accumulation, (i + 1) * accumulation)]
        contextes += len(lus)
        jetons += sum(len(t.encodage.input_ids) for t in lus)
        i += 1
        ecrire(etape="debit", pas=i - 1, perte=p, secondes=time.time() - t0, contextes=contextes,
               jetons=jetons)  # fmt: skip
    if dev == "cuda":
        torch.cuda.synchronize()
    duree = time.time() - t0
    ctx_s = contextes / duree
    par_epoque = load_config("finetune").chargeur.exemples_par_epoque
    total_h = epoques * par_epoque / ctx_s / 3600
    bilan = {
        "exemples": len(tirages), "secondes_donnees": t_donnees, "secondes_essai": t_essai,
        "perte_20_premiers": debut, "perte_20_derniers": fin, "perte_en_baisse": fin < debut,
        "point_de_controle": str(pc), "ecart_rechargement": ecart, "pas_relu": pas_relu,
        "debit_secondes": duree, "debit_pas": i - pas, "contextes_par_s": ctx_s,
        "jetons_par_s": jetons / duree, "memoire_max_go": torch.cuda.max_memory_allocated() / 2**30
        if dev == "cuda" else 0.0,
        "exemples_par_epoque": par_epoque, "epoques": epoques, "duree_totale_h": total_h,
        "secondes_chargeur_par_exemple": t_donnees / len(tirages) if ch else None,
    }  # fmt: skip
    ecrire(etape="bilan", **bilan)
    (run / "bilan.json").write_text(json.dumps(bilan, indent=2))
    print(json.dumps(bilan, indent=2), flush=True)
    return bilan


def lancer(heures: float = 8.0, epoques: int = 3, accumulation: int = 16,
           echauffement: int = 500, tous_les: int = 2000, nom: str = "a0") -> None:  # fmt: skip
    """Une nuit d'entraînement de A0 sur les exemples préchargés (`precharger`) : une époque
    par nuit, jusqu'à sa fin ou jusqu'à `heures` (15 min gardées pour finir). Si l'heure
    arrive avant la fin de l'époque, le reste est sauté : la nuit suivante commence l'époque
    suivante, et `epoques` époques font `epoques` nuits. Point de contrôle tous les
    `tous_les` pas et à l'arrêt ; les 3 derniers et le meilleur (perte moyenne la plus basse
    sur les `tous_les` derniers pas) sont gardés. Après une panne (pas d'arrêt écrit), la
    relance reprend au dernier point de contrôle, au même exemple."""
    from ccm.config import load_config
    from ccm.model.a0 import charger_smollm
    from ccm.train.precharger import lire

    racine = Path(__file__).resolve().parents[2] / "runs"
    anciens = sorted(racine.glob(f"*-{nom}"))
    run = anciens[-1] if anciens else _dossier_run(nom)
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    par_epoque = load_config("finetune").chargeur.exemples_par_epoque // accumulation
    total = epoques * par_epoque

    etat_f = run / "etat.json"
    etat = json.loads(etat_f.read_text()) if etat_f.exists() else {}
    meilleure = etat.get("meilleure", float("inf"))
    voc, _ = _tokenizer()
    torch.manual_seed(0)
    modele = charger_smollm(voc, SMOLLM).to("cuda")
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, echauffement)
    pcs = sorted(run.glob("pas-*.pt"))
    i = recharger(pcs[-1], modele, opt, sched) if pcs else 0
    sautes = 0
    if etat.get("nuit_finie") and i % par_epoque:  # l'heure est arrivée avant la fin
        sautes = par_epoque - i % par_epoque
        i += sautes
    if i >= total:
        print(f"{run.name} : entraînement fini ({i} pas)", flush=True)
        return
    e = i // par_epoque
    nuit = e + 1
    ecrire(etape="reprise", pas=i, epoque=e, nuit=nuit, pas_sautes=sautes,
           point_de_controle=pcs[-1].name if pcs else None,
           heure=time.strftime("%Y-%m-%d %H:%M"))  # fmt: skip
    print(f"{run.name} : nuit {nuit}, époque {e}, reprise au pas {i} ({sautes} pas sautés)",
          flush=True)  # fmt: skip

    def garder(nom_pc: str | None = None, nuit_finie: bool = False) -> None:
        sauver(run / f"pas-{i:06d}.pt", modele, opt, sched, i)
        for vieux in sorted(run.glob("pas-*.pt"))[:-3]:
            vieux.unlink()
        if nom_pc:
            shutil.copy(run / f"pas-{i:06d}.pt", run / nom_pc)
        etat_f.write_text(json.dumps({"pas": i, "meilleure": meilleure, "nuit_finie": nuit_finie}))

    if sys.platform == "win32":  # pas de mise en veille pendant la nuit
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    t0, fenetre, fin = time.time(), [], 3600 * heures - 900
    flux = itertools.islice(lire(e), (i % par_epoque) * accumulation, None)
    while i < (e + 1) * par_epoque and time.time() - t0 < fin:
        lus = list(itertools.islice(flux, accumulation))
        if len(lus) < accumulation:  # époque plus courte (exemples sautés au préchargement)
            i = (e + 1) * par_epoque
            break
        details: list = []
        p = entrainer(modele, lus, 1, accumulation, None, opt, sched, 0, JETONS_LOT, details)[0]
        par_source: dict[str, list[float]] = {}
        for src, _, x in details:
            par_source.setdefault(src, []).append(x)
        fenetre.append(p)
        ecrire(etape="pas", pas=i, epoque=e, perte=p, lr=sched.get_last_lr()[0],
               secondes=time.time() - t0, jetons=sum(len(t.encodage.input_ids) for t in lus),
               sources={k: sum(v) / len(v) for k, v in par_source.items()},
               genres=dict(Counter(g for _, g, _ in details)))  # fmt: skip
        i += 1
        if i % 100 == 0:
            print(f"pas {i} époque {e} perte {sum(fenetre[-100:]) / 100:.4f}", flush=True)
        if i % tous_les == 0:
            m = sum(fenetre) / len(fenetre)
            nom_pc = None
            if m < meilleure:
                meilleure, nom_pc = m, "meilleur.pt"
            garder(nom_pc)
            ecrire(etape="point_de_controle", pas=i, perte_fenetre=m, meilleur=nom_pc is not None)
            fenetre = []
    garder(nuit_finie=True)
    ecrire(etape="arret", pas=i, epoque=e, nuit=nuit, secondes=time.time() - t0,
           fin_epoque=i >= (e + 1) * par_epoque, fini=i >= total,
           heure=time.strftime("%Y-%m-%d %H:%M"))  # fmt: skip
    print(f"nuit {nuit} finie au pas {i} sur {total}", flush=True)


def _huit_exemples(voc, decouper, n=8):
    from ccm.config import load_config
    from ccm.data.worldgen.monde import generer_monde
    from ccm.data.worldgen.pieces import rediger_dossier
    from ccm.data.worldgen.questions import poser_questions
    from ccm.train.chargeur import Chargeur, SourceSynthetique

    icfg, wcfg = load_config("ingest"), load_config("worldgen")
    d = rediger_dossier(generer_monde(0, "entrainement", wcfg, frozenset()), wcfg)
    src = SourceSynthetique([(d, poser_questions(d, wcfg))], icfg)
    ch = Chargeur({"synthetique": src}, load_config("finetune").chargeur, icfg,
                  load_config("search"), load_config("grammar"), voc, decouper)  # fmt: skip
    return list(itertools.islice(ch.epoque(0, 4 * n), n))


def surapprentissage(pas: int = 200) -> None:
    from ccm.model.a0 import charger_smollm

    voc, decouper = _tokenizer()
    tirages = _huit_exemples(voc, decouper)
    torch.manual_seed(0)
    modele = charger_smollm(voc, SMOLLM).to("cuda" if torch.cuda.is_available() else "cpu")
    t0 = time.time()
    pertes = entrainer(modele, tirages, pas, accumulation=len(tirages),
                       journal=lambda i, x: print(f"pas {i} perte {x:.4f}", flush=True)
                       if i % 10 == 0 or i == pas - 1 else None)  # fmt: skip
    print(json.dumps({"premiere": pertes[0], "derniere": pertes[-1], "secondes": time.time() - t0}))


if __name__ == "__main__":
    commande, *args = sys.argv[1:] or ["essai"]
    fonctions = {"essai": essai, "surapprentissage": surapprentissage, "lancer": lancer}
    lu = lambda a: int(a) if a.isdigit() else float(a) if a.replace(".", "").isdigit() else a  # noqa: E731
    fonctions[commande](*map(lu, args))
