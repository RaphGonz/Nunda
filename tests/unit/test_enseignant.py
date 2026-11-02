from ccm.data.enseignant import numeros_valides, prompt_question


def test_numeros_valides_regle_du_paragraphe_12():
    assert numeros_valides([1, 4], 4)
    assert not numeros_valides([], 4)
    assert not numeros_valides([5], 4)
    assert not numeros_valides([0], 4)
    assert not numeros_valides([1, 1], 4)
    assert not numeros_valides([1, 2, 3, 4, 5], 9)


def test_prompt_numerote_depuis_un():
    p = prompt_question(["alpha", "beta"])
    assert "[1] alpha" in p and "[2] beta" in p
