"""Lecture des configurations YAML, validées par pydantic (SPEC.md §3).

Chaque fichier de `configs/` a sa classe. Les champs s'ajoutent phase par phase ;
une clé inconnue est une erreur.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


class ConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    description: str


class IngestConfig(ConfigBase):
    pass


class SearchConfig(ConfigBase):
    pass


class ModelConfig(ConfigBase):
    pass


class PretrainConfig(ConfigBase):
    pass


class FinetuneConfig(ConfigBase):
    pass


CONFIG_CLASSES: dict[str, type[ConfigBase]] = {
    "ingest": IngestConfig,
    "search": SearchConfig,
    "model_a0": ModelConfig,
    "model_a1": ModelConfig,
    "model_b_s": ModelConfig,
    "model_b_m": ModelConfig,
    "pretrain": PretrainConfig,
    "finetune": FinetuneConfig,
}


def load_config(name: str, configs_dir: Path = CONFIGS_DIR) -> ConfigBase:
    """Lit `configs_dir/<name>.yaml` et le valide avec la classe de `CONFIG_CLASSES`."""
    cls = CONFIG_CLASSES[name]
    with (configs_dir / f"{name}.yaml").open(encoding="utf-8") as f:
        return cls.model_validate(yaml.safe_load(f))
