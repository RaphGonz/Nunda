"""Décodage glouton de A0 sous le masque de l'automate (SPEC.md §10, §14 : T9).

À chaque pas, l'exemple est encodé avec le préfixe décodé suivi d'un pas factice (FIN) :
la ligne du préfixe donne les logits du pas suivant (le masque causal cache le pas
factice). Les deux passes sont refaites à chaque pas : plus lent qu'un cache, mais le même
calcul que l'entraînement."""

from collections.abc import Callable, Sequence

import torch

from ccm.anonymize.encode import Vocabulaire, encode, masque_pas
from ccm.config import GrammarConfig
from ccm.grammar.automaton import Automate, Contexte
from ccm.model.a0 import ModeleA0
from ccm.schema import Exemple


class DecodeurA0:
    nom = "a0"
    vocabulaire: frozenset[str] = frozenset()

    def __init__(self, modele: ModeleA0, voc: Vocabulaire, decouper: Callable, gcfg: GrammarConfig,
                 jetons_lot: int = 8000, apres: Callable | None = None,
                 t_max: int | None = None):  # fmt: skip
        """`apres` : encodage → entrée du modèle (A1 : retrait de l'en-tête [REL]).
        `t_max` : une suite dont l'entrée dépasse `t_max` jetons s'arrête et devient
        `["HORS_LIMITE"]` (A1 : biais dense, §9)."""
        self.modele, self.voc, self.decouper, self.gcfg = modele, voc, decouper, gcfg
        self.jetons_lot, self.apres, self.t_max = jetons_lot, apres or (lambda e: e), t_max

    @torch.no_grad()
    def suites(self, items: Sequence[tuple[Exemple, Contexte]], synthese: bool = False
               ) -> list[list[str]]:  # fmt: skip
        """Suite gloutonne de chaque (exemple, contexte) ; contextes groupés par longueur."""
        m = self.modele
        dev = m.lex.weight.device
        etat = m.training
        m.eval()
        autos = [Automate(ctx, self.gcfg, synthese) for _, ctx in items]
        prefixes: list[list[str]] = [[] for _ in items]
        actifs = list(range(len(items)))
        while actifs:
            encs = {i: self.apres(encode(items[i][0].model_copy(
                        update={"cible": [*prefixes[i], "FIN"]}), self.voc, self.decouper))
                    for i in actifs}  # fmt: skip
            if self.t_max is not None:
                for i in [i for i in actifs if len(encs[i].input_ids) > self.t_max]:
                    prefixes[i] = ["HORS_LIMITE"]
                    actifs.remove(i)
            for groupe in _groupes(actifs, {i: len(e.input_ids) for i, e in encs.items()},
                                   self.jetons_lot):  # fmt: skip
                with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                    sorties = m.lot([encs[i] for i in groupe])
                for i, s in zip(groupe, sorties, strict=True):
                    enc, a = encs[i], autos[i]
                    permis = torch.as_tensor(masque_pas(enc.espace, a.autorises()), device=dev)
                    lg = s.logits[len(prefixes[i])].float().masked_fill(~permis, float("-inf"))
                    pas = enc.espace[int(lg.argmax())]
                    a.avancer(pas)
                    prefixes[i].append(pas)
            actifs = [i for i in actifs if not autos[i].fini]
        m.train(etat)
        return prefixes

    def decoder(self, con, q, ex: Exemple, msg, ctx: Contexte, cfg, gcfg, *,
                synthese: bool = False, relance: bool = False):  # fmt: skip
        """Même interface que `Oracle.decoder` (`ccm.answer.repondre`)."""
        from ccm.model.oracle import Decodage

        return Decodage(self.suites([(ex, ctx)], synthese)[0])


def _groupes(ids: list[int], longueur: dict[int, int], jetons: int) -> list[list[int]]:
    out: list[list[int]] = []
    for i in sorted(ids, key=longueur.__getitem__):
        if out and (len(out[-1]) + 1) * longueur[i] <= jetons:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def charger_decodeur(chemin) -> DecodeurA0:
    """SmolLM2 + poids entraînés du point de contrôle `chemin`, sur le GPU s'il y en a un."""
    from ccm.config import load_config
    from ccm.model.a0 import charger_smollm
    from ccm.train.a0 import SMOLLM, _tokenizer, recharger

    voc, decouper = _tokenizer()
    modele = charger_smollm(voc, SMOLLM).to("cuda" if torch.cuda.is_available() else "cpu")
    recharger(chemin, modele)
    return DecodeurA0(modele, voc, decouper, load_config("grammar"))
