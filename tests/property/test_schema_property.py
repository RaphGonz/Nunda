from hypothesis import given
from hypothesis import strategies as st

from ccm.schema import TexteMarque

mots = st.text(
    alphabet=st.characters(blacklist_characters="⟦⟧", blacklist_categories=("Cs",)), max_size=10
)


@given(st.lists(mots, min_size=1, max_size=8))
def test_texte_marque_aller_retour(morceaux):
    texte = "".join(f"{m}⟦{i}⟧" for i, m in enumerate(morceaux[:-1])) + morceaux[-1]
    marques = [{"genre": "NOM", "type": "PER", "nom": i} for i in range(len(morceaux) - 1)]
    tm = TexteMarque(texte=texte, marques=marques)
    assert TexteMarque.model_validate_json(tm.model_dump_json()) == tm
