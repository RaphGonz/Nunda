from hypothesis import given
from hypothesis import strategies as st

from ccm.config import IngestConfig, load_config

INGEST = load_config("ingest")


@given(version=st.integers(), description=st.text())
def test_aller_retour(version, description):
    cfg = IngestConfig.model_validate(
        INGEST.model_dump() | dict(version=version, description=description)
    )
    assert IngestConfig.model_validate(cfg.model_dump()) == cfg
