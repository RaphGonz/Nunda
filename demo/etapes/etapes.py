# ruff: noqa: E501  (gabarit HTML)
"""Les étapes d'une réponse de A0, en pages HTML à filmer (une page par question).

Même chaîne que `ccm answer --modele` (`ccm.answer.repondre`), sans rien changer : on garde
au passage le résultat de la recherche, l'exemple anonymisé et la table de la conversation.

    uv run python demo/etapes/etapes.py                   (questions de QUESTIONS)
    uv run python demo/etapes/etapes.py syn-1000000-q05   (une question)

Écrit `demo/etapes/<question>.html`. Dossier synthétique : aucun nom réel.
"""

import html
import re
import sys
import uuid
from pathlib import Path

from ccm.anonymize.table import ORDRE_TYPES

RACINE = Path(__file__).resolve().parents[2]
SORTIE = Path(__file__).resolve().parent
STOCK = RACINE / "runs" / "demo" / "syn-1000000.sqlite"
DOSSIER = RACINE / "runs" / "corpus" / "niveau0-val" / "validation" / "syn-1000000"
MODELE = RACINE / "runs" / "2026-11-06-a0" / "pas-018124.pt"
# (question, ce que la page montre)
QUESTIONS = {
    "syn-1000000-q14": "Une étape : la date d'un vol",
    "syn-1000000-q19": "Deux étapes : une rencontre, puis un contrat",
    "syn-1000000-q34": "Calcul exact : l'écart entre deux montants",
    "syn-1000000-q00": "Conflit : deux pièces donnent deux heures",
    "syn-1000000-q37": "Nom ambigu : le modèle demande",
    "syn-1000000-q33": "Abstention : aucune pièce ne répond",
}

e = html.escape


def _marque(k, noms, valeurs) -> tuple[str, str]:
    """(ce que voit le modèle, valeur rendue après désanonymisation)."""
    if k.genre == "NOM":
        return f"{k.type} n°{k.nom}", noms.get(k.nom, "?")
    u = k.unite if k.unite not in ("", "date") else ""
    return f"{k.genre}{' ' + u if u else ''} n°{k.valeur_id}", valeurs.get(k.valeur_id, "?")


def _marque_html(t, noms, valeurs, clair: bool) -> str:
    def lab(m):
        vu, vrai = _marque(t.marques[int(m.group(1))], noms, valeurs)
        return f'<span class="{"clair" if clair else "slot"}">{e(vrai if clair else vu)}</span>'

    return re.sub(r"⟦(\d+)⟧", lab, e(t.texte))


def _pas_html(pas: str, ex, noms, valeurs) -> str:
    """Un pas du modèle et ce qu'il désigne."""
    m = re.fullmatch(r"([PMN]):(\w+)(?:\.(\d+))?", pas)
    if not m:
        return f'<span class="mot">{e(pas)}</span>'
    g, t, j = m.groups()
    if g == "P":
        return f'<span class="ptr">{e(pas)}</span><small>passage {t}</small>'
    texte = (
        ex.question if t == "q" else next((p for p in ex.propositions if str(p.local) == t), None)
    )
    if texte is None or j is None or int(j) >= len(texte.marques):
        return f'<span class="ptr">{e(pas)}</span>'
    vu, _ = _marque(texte.marques[int(j)], noms, valeurs)
    return f'<span class="ptr">{e(pas)}</span><small>{e(vu)}</small>'


def page(qid: str, q, r, cap, con) -> str:
    res, ex, table = cap["res"], cap["ex"], cap["table"]
    noms = {}
    for cle, i in table._indices.items():
        if cle[0] == "NOM":
            noms[ORDRE_TYPES.index(cle[1]) * table.k + i] = cle[2]
    valeurs = table.valeurs()
    src = dict(con.execute("SELECT prop_id, texte FROM proposition"))
    pce = dict(con.execute("SELECT p.prop_id, c.chemin FROM proposition p JOIN piece c "
                           "ON c.piece_id = p.piece_id"))  # fmt: skip
    cites = {int(x) for t in r.tours for x in re.findall(r"\b[PMN]:(\d+)", " ".join(t.suite))}

    def ligne_recherche(pid):
        ra = res.raisons.get(pid)
        pourquoi = []
        if ra:
            if ra.noms:
                pourquoi.append("nom : " + ", ".join(ra.noms))
            if ra.texte:
                pourquoi.append("mots de la question")
            if ra.sauts:
                pourquoi.append("lien : " + ", ".join(ra.sauts))
        return (f"<tr><td>{e(Path(pce.get(pid, '')).stem)}</td><td>{e(src.get(pid, ''))}</td>"
                f"<td>{ra.score:.2f}</td><td>{e(' · '.join(pourquoi))}</td></tr>"
                if ra else f"<tr><td>{e(Path(pce.get(pid, '')).stem)}</td>"
                f"<td>{e(src.get(pid, ''))}</td><td>–</td><td></td></tr>")  # fmt: skip

    def ligne_anon(p):
        c = ' class="cite"' if p.local in cites else ""
        return (
            f"<tr{c}><td>passage {p.local}</td><td>{e(src.get(p.prop_id, ''))}</td>"
            f"<td>{_marque_html(p, noms, valeurs, False)}</td></tr>"
        )

    tableau_noms = "".join(
        f"<tr><td>{e(vu)}</td><td>{e(vrai)}</td></tr>"
        for vu, vrai in sorted(
            {_marque(k, noms, valeurs) for t in [ex.question, *ex.propositions] for k in t.marques}
        )  # fmt: skip
    )
    tours = "".join(
        f"<h3>{'Pas du modèle' if i == 0 else 'Pas du modèle après relance'}</h3>"
        f'<div class="pas">{" ".join(_pas_html(p, ex, noms, valeurs) for p in t.suite)}</div>'
        for i, t in enumerate(r.tours)
    )
    reponse = "".join(f"<p>{e(b)}</p>" for b in r.reponse.texte.splitlines())
    return f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<title>CCM : les étapes d'une réponse</title>
<style>
:root{{--fond:#fbfaf7;--texte:#1d1d1b;--gris:#6b6a66;--ligne:#e3e0d8;--slot:#7a4fd0;--clair:#1f7a4d;--ptr:#b5541c}}
body{{margin:0;background:var(--fond);color:var(--texte);font:18px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:32px 16px 80px}}
h1{{font-size:28px;margin:0 0 4px}} .sous{{color:var(--gris);margin:0 0 32px}}
section{{border-top:1px solid var(--ligne);padding:24px 0}}
h2{{font-size:22px;margin:0 0 4px}} h2 b{{color:var(--gris);font-weight:600;margin-right:8px}}
.but{{color:var(--gris);margin:0 0 16px}}
.question{{font-size:24px;background:#fff;border:1px solid var(--ligne);border-radius:8px;padding:16px 20px}}
table{{border-collapse:collapse;width:100%;font-size:16px}}
td,th{{border-bottom:1px solid var(--ligne);padding:6px 10px;text-align:left;vertical-align:top}}
th{{color:var(--gris);font-weight:600}} tr.cite td{{background:#fff4e8}}
.slot{{color:var(--slot);font-weight:600;background:#f1ebfb;border-radius:4px;padding:0 4px}}
.clair{{color:var(--clair);font-weight:600;background:#e7f4ec;border-radius:4px;padding:0 4px}}
.pas{{display:flex;flex-wrap:wrap;gap:8px;font-family:ui-monospace,Consolas,monospace}}
.pas>span{{display:inline-flex;flex-direction:column}} .pas small{{font:12px system-ui;color:var(--gris)}}
.ptr{{color:var(--ptr);font-weight:600}} .mot{{color:var(--gris)}}
.reponse{{font-size:20px;background:#fff;border:2px solid var(--clair);border-radius:8px;padding:12px 20px}}
.flux{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--gris);font-size:15px;margin:0 0 24px}}
.flux span{{border:1px solid var(--ligne);border-radius:16px;padding:2px 12px;background:#fff}}
</style><main>
<h1>Les étapes d'une réponse</h1>
<p class="sous">Modèle A0 ({e(MODELE.name)}), dossier synthétique {e(DOSSIER.name)}, question {e(qid)}</p>
<div class="flux"><span>1. Question</span>→<span>2. Recherche</span>→<span>3. Anonymisation</span>→<span>4. Modèle</span>→<span>5. Désanonymisation</span></div>

<section><h2><b>1</b>Question de l'utilisateur</h2>
<p class="question">{e(q.message.texte)}</p></section>

<section><h2><b>2</b>Recherche dans le dossier</h2>
<p class="but">BM25 et liens du graphe, sans modèle génératif : {len(res.prop_ids)} passages gardés, dans l'ordre du contexte.</p>
<table><tr><th>pièce</th><th>passage</th><th>score</th><th>pourquoi</th></tr>
{"".join(ligne_recherche(p) for p in res.prop_ids)}</table></section>

<section><h2><b>3</b>Anonymisation</h2>
<p class="but">Chaque nom, nombre et date devient une marque. Le modèle ne voit jamais la valeur.</p>
<p class="question">{_marque_html(ex.question, noms, valeurs, False)}</p>
<table><tr><th></th><th>texte d'origine</th><th>ce que reçoit le modèle</th></tr>
{"".join(ligne_anon(p) for p in ex.propositions)}</table>
<h3>Table de la conversation (reste hors du modèle)</h3>
<table><tr><th>marque</th><th>valeur</th></tr>{tableau_noms}</table></section>

<section><h2><b>4</b>Ce que répond le modèle</h2>
<p class="but">Le modèle n'écrit ni nom ni chiffre : des pointeurs vers les passages (P) et les marques (M, N). Les passages cités sont surlignés à l'étape 3.</p>
{tours}</section>

<section><h2><b>5</b>Désanonymisation et vérification</h2>
<p class="but">Le vérificateur contrôle chaque pointeur, puis remplace les marques par le texte d'origine des pièces.</p>
<div class="reponse">{reponse}</div></section>
</main></html>"""


def main(args: list[str]) -> None:
    import ccm.answer as A
    from ccm.config import load_config
    from ccm.model.decodeur import charger_decodeur
    from ccm.model.oracle import Oracle
    from ccm.schema import ouvrir_stock
    from ccm.search.bm25 import charger_index, dossier_index

    cap: dict = {}
    chercher, anonymiser = A.chercher, A.anonymiser

    def chercher_(*a, **k):
        res = chercher(*a, **k)
        cap.setdefault("res", res)  # premier tour seulement
        return res

    def anonymiser_(con, ids, msg, table, *a, **k):
        ex = anonymiser(con, ids, msg, table, *a, **k)
        cap.setdefault("table", table)
        cap.setdefault("ex", ex)
        return ex

    A.chercher, A.anonymiser = chercher_, anonymiser_
    cfgs = tuple(load_config(x) for x in ("ingest", "search", "grammar", "verify"))
    con = ouvrir_stock(STOCK)
    index, oracle, dec = (
        charger_index(dossier_index(STOCK)),
        Oracle(DOSSIER),
        charger_decodeur(MODELE),
    )
    for qid in args or QUESTIONS:
        q = oracle.question(id=qid)
        cap.clear()
        r = A.repondre(con, index, oracle, q, *cfgs, conv_id=uuid.uuid4().hex, modele=dec)
        f = SORTIE / f"{qid}.html"
        f.write_text(page(qid, q, r, cap, con), encoding="utf-8")
        print(f, "erreur : " + r.reponse.erreur if r.reponse.erreur else "", flush=True)
    liens = "".join(
        f'<li><a href="{k}.html">{e(v)}</a> <small>{k}</small></li>'
        for k, v in QUESTIONS.items()
        if (SORTIE / f"{k}.html").exists()
    )
    (SORTIE / "index.html").write_text(
        '<!doctype html><html lang="fr"><meta charset="utf-8"><title>CCM : étapes</title>'
        '<body style="font:20px/1.6 system-ui;max-width:800px;margin:40px auto;padding:0 16px">'
        f"<h1>Les étapes d'une réponse</h1><ol>{liens}</ol></body></html>",
        encoding="utf-8",
    )
    con.close()


if __name__ == "__main__":
    main(sys.argv[1:])
