"""Export Hugging Face (`ccm.publier`) : slots, filtre des canaris."""

from ccm.publier import filtre_canaris, slots


def test_slots():
    ms = [{"genre": "NOM", "type": "PER", "nom": 3}, {"genre": "DATE"}, {"genre": "NUM"}]
    assert slots("⟦0⟧ le ⟦1⟧ : ⟦2⟧ €", ms) == "⟨PER 3⟩ le ⟨DATE⟩ : ⟨NUM⟩ €"


def test_filtre_canaris():
    c = [{"genre": "naturel", "documents": ["d1"], "nom": "Ana Zorb"},
         {"genre": "force", "documents": [], "nom": "Léo Quarm"}]  # fmt: skip
    garder = filtre_canaris(c)
    assert not garder({"document": "d1", "texte": "rien"})
    assert not garder({"document": "d2", "texte": "Selon ses proches, Léo Quarm a pour"})
    assert garder({"document": "d2", "texte": "Selon ses proches, ⟦0⟧ a pour"})
