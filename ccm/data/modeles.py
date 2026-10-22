"""Téléchargement des modèles de la détection des noms (SPEC.md §3, §6) dans `runs/modeles/`.

Révisions figées, empreintes SHA-256 contrôlées ; licences dans `DATA_LICENSES.md`. Un
fichier déjà présent avec la bonne empreinte n'est pas retéléchargé. Seul ce module touche
au réseau : la détection lit ensuite les fichiers sur le disque.

    uv run ccm modeles
"""

import hashlib
import json
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
MODELES = RACINE / "runs" / "modeles"

_HF = "https://huggingface.co/{depot}/resolve/{rev}/{fichier}"
_GLINER = ("urchade/gliner_multi-v2.1", "443d26d654e0324125a96bebd8e796c14ff2efe6")
_MDEBERTA = ("microsoft/mdeberta-v3-base", "a0484667b22365f84929a935b5e50a51f71f159d")
_LO = "https://raw.githubusercontent.com/LibreOffice/dictionaries/67032ee957631908098a72edf48dc81cac27e369"

# (dossier local, fichier local, URL, SHA-256 ou None pour un petit fichier de réglages)
FICHIERS = [
    *(
        ("gliner_multi-v2.1", f, _HF.format(depot=_GLINER[0], rev=_GLINER[1], fichier=f), h)
        for f, h in [
            ("gliner_config.json", None),
            ("model.safetensors", "2100142f31627531497850659dcb3821c99d5e71c08a8e01a98e4b11ef32a199"),
        ]
    ),
    *(
        ("mdeberta-v3-base", f, _HF.format(depot=_MDEBERTA[0], rev=_MDEBERTA[1], fichier=f), h)
        for f, h in [
            ("config.json", None),
            ("tokenizer_config.json", None),
            ("spm.model", "13c8d666d62a7bc4ac8f040aab68e942c861f93303156cc28f5c7e885d86d6e3"),
        ]
    ),
    *(
        ("lexique", f, f"{_LO}/{chemin}", h)
        for f, chemin, h in [
            ("fr.dic", "fr_FR/dictionaries/fr.dic",
             "b78a868e31dd6e373b6c3217969afb898a9acde828a5e7ef97308da42218c88c"),
            ("fr.aff", "fr_FR/dictionaries/fr.aff",
             "c176610cd5dc4846806a65ddd029f422d87978bf58f224aa44222662a16a2de5"),
            ("README_dict_fr.txt", "fr_FR/dictionaries/README_dict_fr.txt", None),
            ("en_US.dic", "en/en_US.dic",
             "f0b1a234bd178bdd01875b2a392a9647f888b8fe879f79c52aae62c2759b3647"),
            ("en_US.aff", "en/en_US.aff",
             "e746c882dd6f303c2c46e7452804b9201115a6942cfeb15f18f8edf774d2e24e"),
            ("README_en_US.txt", "en/README_en_US.txt", None),
        ]
    ),
]  # fmt: skip


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        while bloc := f.read(1 << 20):
            h.update(bloc)
    return h.hexdigest()


def telecharger(dossier: Path = MODELES) -> list[Path]:
    """Télécharge ce qui manque ; rend les fichiers écrits."""
    ecrits = []
    for sous, nom, url, empreinte in FICHIERS:
        cible = dossier / sous / nom
        if cible.exists() and (empreinte is None or _sha256(cible) == empreinte):
            continue
        cible.parent.mkdir(parents=True, exist_ok=True)
        partiel = cible.with_suffix(cible.suffix + ".part")
        with urllib.request.urlopen(url) as r, partiel.open("wb") as f:
            while bloc := r.read(1 << 20):
                f.write(bloc)
        if empreinte is not None and _sha256(partiel) != empreinte:
            partiel.unlink()
            raise ValueError(f"empreinte inattendue : {url}")
        partiel.replace(cible)
        ecrits.append(cible)
    # GLiNER construit son encodeur depuis `model_name` : le dossier local, pas le Hub.
    conf = dossier / "gliner_multi-v2.1" / "gliner_config.json"
    c = json.loads(conf.read_text(encoding="utf-8"))
    local = (dossier / "mdeberta-v3-base").resolve().as_posix()
    if c["model_name"] != local:
        c["model_name"] = local
        conf.write_text(json.dumps(c, indent=1), encoding="utf-8")
    return ecrits
