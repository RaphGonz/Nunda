from hypothesis import given
from hypothesis import strategies as st

from ccm.config import IngestConfig


@given(version=st.integers(), description=st.text())
def test_aller_retour(version, description):
    cfg = IngestConfig(version=version, description=description)
    assert IngestConfig.model_validate(cfg.model_dump()) == cfg
