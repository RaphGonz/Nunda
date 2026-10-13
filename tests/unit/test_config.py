import pydantic
import pytest

from ccm.config import CONFIG_CLASSES, CONFIGS_DIR, load_config


def test_chaque_yaml_a_sa_classe():
    noms = {p.stem for p in CONFIGS_DIR.glob("*.yaml")}
    assert noms == set(CONFIG_CLASSES)


@pytest.mark.parametrize("name", sorted(CONFIG_CLASSES))
def test_chaque_config_se_lit(name):
    cfg = load_config(name)
    assert isinstance(cfg, CONFIG_CLASSES[name])


def test_cle_inconnue_refusee(tmp_path):
    (tmp_path / "ingest.yaml").write_text("version: 1\ndescription: x\ninconnue: 3\n")
    with pytest.raises(pydantic.ValidationError):
        load_config("ingest", tmp_path)
