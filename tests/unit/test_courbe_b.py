"""Page de suivi de B : tranches, validation, nuits (chronomètre qui repart), heures."""

from ccm.train import courbe_b


def _l(pas, s, val=False):
    x = {"pas": pas, "s": s, "mots": 2.0, "pointeur": 1.0, "attributs": 2.0}
    return x | ({"val_mots": 3.0, "val_pointeur": 1.0, "val_attributs": 2.0} if val else {})


def test_donnees_nuits_et_heures():
    lignes = [_l(p, 10.0 * p) for p in range(1, 61)] + [
        _l(p, 10.0 * (p - 60)) for p in range(61, 101)
    ]
    lignes[99] = _l(100, 400.0, val=True)
    d = courbe_b.donnees(lignes, 1000)
    assert d["pas"] == [50, 100] and d["pre"] == [4.0, 4.0]
    assert d["val"]["pas"] == [100] and d["val"]["pre"] == [5.0]
    assert d["nuits"] == [0, 60] and abs(d["heures"] - 1000 / 3600) < 1e-9
    assert "__" not in courbe_b.page(lignes, 1000).replace("__DATA__", "")


def test_reprise_en_arriere_et_sessions():
    # 1..60, reprise au pas 41 (41..60 refaits), puis tranche suivante au pas 81.
    lignes = ([_l(p, 10.0 * p) for p in range(1, 61)]
              + [_l(p, 10.0 * (p - 40)) for p in range(41, 81)]
              + [_l(p, 10.0 * (p - 80)) for p in range(81, 101)])  # fmt: skip
    d = courbe_b.donnees(lignes, 1000, sessions=[1, 41])
    assert d["pas"] == [50, 100] and d["nuits"] == [0, 40]
    assert abs(d["heures"] - 1000 / 3600) < 1e-9  # 400 + 400 + 200 s, refaits exclus
    assert courbe_b.donnees(lignes, 1000)["nuits"] == [0, 40, 80]
