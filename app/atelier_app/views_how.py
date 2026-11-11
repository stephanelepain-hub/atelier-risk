"""The "How it works" page (GET /how): plain words, EN and FR, for a business owner."""
import html

from . import engine, labels
from .views import esc, page

METHOD_URL = "https://cyber.gouv.fr/securisation/analyse-des-risques/methode-ebios-rm"
GUIDE_URL = "https://messervices.cyber.gouv.fr/guides/la-methode-ebios-risk-manager-le-guide"

T = {
    "en": {
        "title": "How it works",
        "lead": "Atelier gives you a first look at your main risks. Here is what stands behind it.",
        "h_method": "The method",
        "method": "Atelier follows <b>EBIOS Risk Manager</b>, the risk analysis method published by <b>ANSSI</b>, the French "
                  "national cybersecurity agency. ANSSI states that the method conforms with ISO/IEC 27005:2022.",
        "method_link": "The method page (ANSSI)", "guide_link": "The guide (ANSSI)",
        "h_screens": "Your four screens and the five workshops of the method",
        "screens": ["<b>About you</b> is workshop 1: what matters to you and what you use.",
                    "<b>Risks that apply</b> are workshops 2 and 3: who or what could cause each risk, and how.",
                    "<b>Now and after</b> are workshops 4 and 5: how likely each risk is, what you already do and what you could add.",
                    "<b>Results</b> are workshop 5: your risks on two maps, and the actions to start with."],
        "screens_note": "It is a shorter form of the method, a first view rather than a full analysis.",
        "h_numbers": "Where the numbers come from",
        "numbers": ["The scales and the risk grid come from the ANSSI guide, version 1.5 (September 2024). The numbers are "
                    "the guide's; only the names are in plain words.",
                    "The list of typical risks comes from two public sources: the ANSSI guide (risks caused on purpose) and "
                    "NIST SP 800-30 (accidents, outages and mistakes).",
                    "The first suggestions for each risk and the confidence figure are simple Atelier rules that "
                    "complete the method."],
        "h_scales": "The scales, in plain words",
        "sev": "How much it would matter", "lik": "How likely", "lvl": "Level of the risk",
        "lik_words": [labels.LIKELIHOOD_LABEL["en"][n] for n in (1, 2, 3, 4)],
        "grid": "The grid crosses the two: the more it would matter and the more likely it is, the higher the level.",
        "h_conf": "What the confidence figure means",
        "conf": "It shows how much of the picture rests on your own answers rather than on typical values. Each answer "
                "adds to it, up to {n}%. Confidence grows as you answer more questions yourself.",
        "h_honesty": "Honesty statement",
        "h_data": "Your data",
        "data": "Your data stays on the computer that runs Atelier: your answers are saved there, and only there.",
        "h_indep": "Independence",
        "indep": "Atelier is an independent project, separate from ANSSI, SGDSN and Club EBIOS. "
                 "EBIOS is a registered trademark of SGDSN.",
        "back": "Back to the home page",
    },
    "fr": {
        "title": "Comment ça marche",
        "lead": "Atelier vous donne un premier regard sur vos principaux risques. Voici ce qu'il y a derrière.",
        "h_method": "La méthode",
        "method": "Atelier suit <b>EBIOS Risk Manager</b>, la méthode d'analyse de risques publiée par l'<b>ANSSI</b>, l'agence "
                  "nationale française de la cybersécurité. L'ANSSI indique que la méthode est conforme à la norme "
                  "ISO/IEC 27005:2022.",
        "method_link": "La page de la méthode (ANSSI)", "guide_link": "Le guide (ANSSI)",
        "h_screens": "Vos quatre écrans et les cinq ateliers de la méthode",
        "screens": ["<b>Vous</b> correspond à l'atelier 1 : ce qui compte pour vous et ce que vous utilisez.",
                    "<b>Risques concernés</b> correspond aux ateliers 2 et 3 : qui ou quoi pourrait causer chaque risque, et comment.",
                    "<b>Maintenant et après</b> correspond aux ateliers 4 et 5 : la vraisemblance de chaque risque, ce que vous faites déjà et ce que vous pourriez ajouter.",
                    "<b>Résultats</b> correspond à l'atelier 5 : vos risques sur deux cartes, et les actions par lesquelles commencer."],
        "screens_note": "C'est une forme abrégée de la méthode : une première vue, pas une analyse complète.",
        "h_numbers": "D'où viennent les chiffres",
        "numbers": ["Les échelles et la grille des risques viennent du guide de l'ANSSI, version 1.5 (septembre 2024). Les "
                    "chiffres sont ceux du guide ; seuls les noms sont en mots simples.",
                    "La liste des risques typiques vient de deux sources publiques : le guide de l'ANSSI (risques causés "
                    "volontairement) et NIST SP 800-30 (accidents, pannes et erreurs).",
                    "Les premières propositions pour chaque risque et le chiffre de confiance sont des règles simples "
                    "d'Atelier qui complètent la méthode."],
        "h_scales": "Les échelles, en mots simples",
        "sev": "L'importance que cela aurait", "lik": "La vraisemblance", "lvl": "Le niveau du risque",
        "lik_words": [labels.LIKELIHOOD_LABEL["fr"][n] for n in (1, 2, 3, 4)],
        "grid": "La grille croise les deux : plus c'est important et plus c'est vraisemblable, plus le niveau monte.",
        "h_conf": "Ce que veut dire le chiffre de confiance",
        "conf": "Il montre la part de la vue d'ensemble qui repose sur vos réponses plutôt que sur des valeurs typiques. "
                "Chaque réponse l'augmente, jusqu'à {n} %. La confiance grandit à mesure que vous répondez vous-même à plus de questions.",
        "h_honesty": "Déclaration d'honnêteté",
        "h_data": "Vos données",
        "data": "Vos données restent sur l'ordinateur qui fait tourner Atelier : vos réponses y sont enregistrées, et seulement là.",
        "h_indep": "Indépendance",
        "indep": "Atelier est un projet indépendant, distinct de l'ANSSI, du SGDSN et du Club EBIOS. "
                 "EBIOS est une marque déposée du SGDSN.",
        "back": "Retour à l'accueil",
    },
}


def how(session, lang):
    t = T[lang if lang in T else "en"]
    lang = lang if lang in T else "en"
    levels = [labels.LEVEL_LABEL[lang][k] for k in ("Low", "Medium", "High")]
    sev = "".join(f"<li>{esc(labels.SEVERITY_WORDS[lang][n])}</li>" for n in (1, 2, 3, 4))
    body = f"""<article class="how">
<h1>{esc(t["title"])}</h1><p class="lead">{esc(t["lead"])}</p>
<section class="card"><h2>{esc(t["h_method"])}</h2><p>{t["method"]}</p>
<p><a href="{METHOD_URL}" rel="noopener noreferrer">{esc(t["method_link"])}</a> &middot;
<a href="{GUIDE_URL}" rel="noopener noreferrer">{esc(t["guide_link"])}</a></p></section>
<section class="card"><h2>{esc(t["h_screens"])}</h2>
<ol>{"".join(f"<li>{x}</li>" for x in t["screens"])}</ol><p class="hint">{esc(t["screens_note"])}</p></section>
<section class="card"><h2>{esc(t["h_numbers"])}</h2>
<ul>{"".join(f"<li>{esc(x)}</li>" for x in t["numbers"])}</ul>
<h3>{esc(t["h_scales"])}</h3>
<p><b>{esc(t["sev"])}</b></p><ol>{sev}</ol>
<p><b>{esc(t["lik"])}</b>: {esc(", ".join(t["lik_words"]))}.</p>
<p><b>{esc(t["lvl"])}</b>: {esc(", ".join(levels))}.</p><p class="hint">{esc(t["grid"])}</p></section>
<section class="card"><h2>{esc(t["h_conf"])}</h2><p>{esc(t["conf"].format(n=engine.NO_DOCUMENT_CEILING))}</p></section>
<aside class="honesty" aria-labelledby="how-honesty-h"><h2 id="how-honesty-h">{esc(t["h_honesty"])}</h2>
<p lang="{lang}">{html.escape(engine.HONESTY[lang], quote=False)}</p></aside>
<section class="card"><h2>{esc(t["h_data"])}</h2><p>{esc(t["data"])}</p></section>
<section class="card"><h2>{esc(t["h_indep"])}</h2><p>{esc(t["indep"])}</p></section>
<p><a href="/?lang={lang}">{esc(t["back"])}</a></p>
</article>"""
    return page(t["title"], body, session, lang=lang, lang_path="/how")
