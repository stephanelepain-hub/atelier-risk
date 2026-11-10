"""Quick-path pages: the home page and the four screens (About you, Risks, Now and after, Results).

Text is in English and French (T). Every piece of user or catalogue text goes through esc(). Levels, confidence and
the honesty statement are the engine's; nothing here computes a level.
"""
from . import engine
from .views import csrf_input, esc, level_classes, page, scale_text, when

STEPS = ("about", "risks", "now", "results")

T = {
    "en": {
        "home_title": "Know your main risks in about 30 minutes",
        "home_lead": "Answer a few simple questions, tick the risks that apply to you, and get a clear picture of where "
                     "you stand and what to do first. No security background needed.",
        "way1": "Start from scratch", "way1_text": "Answer simple questions (about 30 minutes).", "way1_go": "Start",
        "way2": "I have documents", "way2_text": "Upload a document too (Word, PDF or text). It is stored and flagged; reading it comes later.",
        "way2_go": "Start with a document",
        "way3": "I already have a risk analysis", "way3_text": "Import your Excel workbook and review it.", "way3_go": "Import a workbook",
        "continue": "Pick up where you left off", "continue_none": "Nothing here yet. Your analyses will appear here so you can come back to them.",
        "all_studies": "All studies, the guide example and file import", "step_of": "Step {n} of 4",
        "step_about": "About you", "step_risks": "Risks that apply", "step_now": "Now and after", "step_results": "Results",
        "steps_label": "Your progress", "saved": "Saved.", "back": "Back", "continue_btn": "Save and continue",
        "save_btn": "Save", "optional": "optional", "dk": "I don't know",
        "about_title": "About you", "about_lead": "A few questions so we can suggest the risks that fit you. Skip any you do not know: we will say what we assumed.",
        "q_name": "Give this analysis a name", "q_name_ex": "For example: Our company, spring review",
        "q_activity": "What does your organisation do?", "q_activity_ex": "For example: we run three bakeries and deliver to local shops.",
        "q_values": "What matters most to you? (up to 5 things, one per line, most important first)",
        "q_values_ex": "For example: taking orders, our customer list, the payroll, the production line.",
        "q_tools": "What do you use?", "q_tools_ex": "Tick everything that applies. This decides which risks we suggest.",
        "q_downtime": "If your main tools stopped, how soon would it really hurt?",
        "q_sensitivity": "How sensitive is the information you hold?",
        "q_doc": "Do you have a document about your systems or risks?",
        "q_doc_ex": "For example an architecture description, a business impact analysis or a security baseline. It is stored and flagged as provided. Atelier does not read it yet, so it does not change the results.",
        "doc_kind": "What is it?", "doc_file": "File (Word, PDF or text, 20 MB at most)",
        "doc_architecture": "Architecture document", "doc_business-impact": "Business impact analysis",
        "doc_security-baseline": "Security baseline", "doc_other": "Something else",
        "doc_have": "Document stored: {name}. It is flagged as provided and has not been read.", "doc_replace": "Upload another to replace it",
        "downtime_hours": "Within a few hours", "downtime_day": "Within a day or two", "downtime_days": "Within a week",
        "downtime_week": "We could manage for more than a week",
        "sens_public": "Mostly public, or of little interest to others", "sens_internal": "Internal, but harmless if it leaked",
        "sens_confidential": "Customer, personal or financial data", "sens_critical": "Secrets, health or legal data: a leak would be serious",
        "err_name": "Give the analysis a name (up to 200 characters).", "err_values": "Up to 5 things; each at most 200 characters.",
        "err_doc": "The document was not accepted: {why}",
        "risks_title": "Risks that typically apply to you",
        "risks_lead": "These come from a public list, chosen from your answers. Keep the ones that fit, discard the ones that do not, and add your own.",
        "fam_deliberate": "Someone attacks you", "fam_deliberate_text": "A person or a group acts on purpose.",
        "fam_accidental": "Things go wrong", "fam_accidental_text": "Mistakes, failures, outages, loss and natural events.",
        "keep": "Keep this risk", "always": "We always check this one", "always_hint": "If you discard it, tell us why.",
        "reason_ph": "Why does this not apply to you?", "err_reason": "Tell us why you discard this risk.",
        "hits": "Affects", "criteria_confidentiality": "who can see it", "criteria_integrity": "whether it is correct",
        "criteria_availability": "whether you can use it", "typology": "Who and why",
        "add_title": "Add a risk in your own words", "add_hint": "Something we did not list? Describe it in one line.",
        "add_title_label": "The risk", "add_family": "It is", "add_crit": "It affects",
        "mine": "Added by you", "risks_count": "{k} of {n} risks kept", "none_kept": "No risk kept yet. Keep at least one to continue.",
        "now_title": "Now and after", "now_lead": "For each risk: how bad it would be, how likely it is, what you already do, and what you could add. We work out the levels for you.",
        "now_empty": "You have not kept any risk yet.", "now_empty_cta": "Choose your risks",
        "sev_q": "How bad would it be for you?", "sev_proposed": "We suggest", "sev_keep": "Keep our suggestion",
        "sev_reason": "Why another level?", "sev_reason_ph": "Needed when you choose another level", "err_sev_reason": "Tell us why you chose another level.",
        "lik_deliberate": "How likely is it that someone tries this against you in the coming year?",
        "lik_accidental": "Has this happened to you in the last 3 years?", "lik_skip": "Not answered",
        "lik_unlikely": "Unlikely: I do not expect it", "lik_possible": "Possible", "lik_likely": "Likely",
        "lik_very_likely": "Very likely: it may already be happening",
        "lik_never": "No, never", "lik_once": "Yes, once", "lik_sometimes": "Yes, a few times", "lik_often": "Yes, regularly",
        "measures": "What helps", "measures_hint": "For each measure: do you already do it, or would you add it?",
        "m_none": "Not now", "m_in": "Already in place", "m_extra": "Add to my plan",
        "now_level": "Now", "after_level": "After your extra measures", "levels_note": "Levels are worked out by the engine from your answers.",
        "save_stay": "Save", "save_next": "Save and see the results", "err_row": "Check this risk: {msg}",
        "res_title": "Your results", "res_lead": "Where you stand now, and where you could be after the extra measures you ticked.",
        "map_now": "Now", "map_after": "After your extra measures", "map_legend": "Risks on the maps",
        "risk_col": "Risk", "now_col": "Now", "after_col": "After",
        "conf": "Confidence", "conf_text": "How much of this rests on what you told us, rather than on assumptions.",
        "band_low": "low", "band_medium": "medium", "band_high": "high",
        "conf_cap": "Without a document, confidence never goes above {n}%.",
        "top5": "Your top actions", "top5_empty": "No action yet. Go back to “Now and after” and tick the measures you would add.",
        "top5_for": "Helps with", "assumptions": "What we assumed", "assumptions_lead": "Please check these. Each one is a place where we used a typical value instead of your answer.",
        "assumptions_none": "No assumption: every input came from you.", "assumptions_kept": "Typical values you kept (show)",
        "kind_default": "Not answered", "kind_dont_know": "You did not know", "kind_catalogue": "Typical value kept",
        "facts_docs": "Documents", "facts_none": "none", "facts_missing": "Not provided", "facts_answers": "Answers",
        "facts_assumptions": "Assumptions to confirm", "doc_note": "A document is stored but has not been read yet: it does not raise the confidence.",
        "doc_architecture_short": "architecture document", "doc_business-impact_short": "business impact analysis",
        "doc_security-baseline_short": "security baseline", "doc_other_short": "other document",
        "export": "Download Excel", "export_json": "Download the study file", "expert": "Open in expert mode",
        "expert_hint": "Expert mode shows the full method (workshops 1 to 5) on the same study. Changes made there are not carried back into these screens: saving a screen here rebuilds the study from your answers.",
        "edited": "This study was changed in expert mode. Saving this screen rebuilds the study from your quick answers and replaces those changes (the previous version is kept as a .bak file).",
        "edit_answers": "Change my answers",
        "honesty": "Honesty statement",
    },
    "fr": {
        "home_title": "Connaître vos principaux risques en 30 minutes environ",
        "home_lead": "Répondez à quelques questions simples, cochez les risques qui vous concernent et obtenez une vue claire de votre situation "
                     "et de ce qu'il faut faire en premier. Aucune connaissance en sécurité n'est nécessaire.",
        "way1": "Partir de zéro", "way1_text": "Répondre à des questions simples (environ 30 minutes).", "way1_go": "Commencer",
        "way2": "J'ai des documents", "way2_text": "Ajoutez aussi un document (Word, PDF ou texte). Il est conservé et signalé ; sa lecture viendra plus tard.",
        "way2_go": "Commencer avec un document",
        "way3": "J'ai déjà une analyse de risques", "way3_text": "Importez votre classeur Excel et relisez-le.", "way3_go": "Importer un classeur",
        "continue": "Reprendre là où vous en étiez", "continue_none": "Rien ici pour l'instant. Vos analyses apparaîtront ici pour que vous puissiez y revenir.",
        "all_studies": "Toutes les études, l'exemple du guide et l'import de fichier", "step_of": "Étape {n} sur 4",
        "step_about": "Vous", "step_risks": "Risques concernés", "step_now": "Maintenant et après", "step_results": "Résultats",
        "steps_label": "Votre progression", "saved": "Enregistré.", "back": "Retour", "continue_btn": "Enregistrer et continuer",
        "save_btn": "Enregistrer", "optional": "facultatif", "dk": "Je ne sais pas",
        "about_title": "Vous", "about_lead": "Quelques questions pour vous proposer les risques qui vous correspondent. Passez celles que vous ne connaissez pas : nous dirons ce que nous avons supposé.",
        "q_name": "Donnez un nom à cette analyse", "q_name_ex": "Par exemple : Notre société, bilan de printemps",
        "q_activity": "Que fait votre organisation ?", "q_activity_ex": "Par exemple : nous gérons trois boulangeries et livrons des commerces locaux.",
        "q_values": "Qu'est-ce qui compte le plus pour vous ? (jusqu'à 5 éléments, un par ligne, le plus important d'abord)",
        "q_values_ex": "Par exemple : prendre les commandes, notre fichier clients, la paie, la ligne de production.",
        "q_tools": "Qu'utilisez-vous ?", "q_tools_ex": "Cochez tout ce qui s'applique. Cela détermine les risques proposés.",
        "q_downtime": "Si vos outils principaux s'arrêtaient, au bout de combien de temps cela ferait-il vraiment mal ?",
        "q_sensitivity": "Quelle est la sensibilité des informations que vous détenez ?",
        "q_doc": "Avez-vous un document sur vos systèmes ou vos risques ?",
        "q_doc_ex": "Par exemple une description d'architecture, une analyse d'impact sur l'activité ou un socle de sécurité. Il est conservé et signalé comme fourni. Atelier ne le lit pas encore : il ne change donc pas les résultats.",
        "doc_kind": "De quoi s'agit-il ?", "doc_file": "Fichier (Word, PDF ou texte, 20 Mo au plus)",
        "doc_architecture": "Document d'architecture", "doc_business-impact": "Analyse d'impact sur l'activité",
        "doc_security-baseline": "Socle de sécurité", "doc_other": "Autre chose",
        "doc_have": "Document conservé : {name}. Il est signalé comme fourni et n'a pas été lu.", "doc_replace": "En envoyer un autre pour le remplacer",
        "downtime_hours": "En quelques heures", "downtime_day": "En un jour ou deux", "downtime_days": "En une semaine",
        "downtime_week": "Nous tiendrions plus d'une semaine",
        "sens_public": "Surtout publiques, ou sans intérêt pour d'autres", "sens_internal": "Internes, mais sans gravité si elles fuitaient",
        "sens_confidential": "Données de clients, personnelles ou financières", "sens_critical": "Secrets, données de santé ou juridiques : une fuite serait grave",
        "err_name": "Donnez un nom à l'analyse (200 caractères au plus).", "err_values": "5 éléments au plus ; 200 caractères au plus chacun.",
        "err_doc": "Le document n'a pas été accepté : {why}",
        "risks_title": "Les risques qui vous concernent typiquement",
        "risks_lead": "Ils viennent d'une liste publique, choisis d'après vos réponses. Gardez ceux qui conviennent, écartez les autres et ajoutez les vôtres.",
        "fam_deliberate": "Quelqu'un vous attaque", "fam_deliberate_text": "Une personne ou un groupe agit volontairement.",
        "fam_accidental": "Ça se passe mal", "fam_accidental_text": "Erreurs, pannes, interruptions, pertes et événements naturels.",
        "keep": "Garder ce risque", "always": "Nous vérifions toujours celui-ci", "always_hint": "Si vous l'écartez, dites-nous pourquoi.",
        "reason_ph": "Pourquoi cela ne vous concerne-t-il pas ?", "err_reason": "Dites-nous pourquoi vous écartez ce risque.",
        "hits": "Touche", "criteria_confidentiality": "qui peut le voir", "criteria_integrity": "s'il est correct",
        "criteria_availability": "si vous pouvez l'utiliser", "typology": "Qui et pourquoi",
        "add_title": "Ajouter un risque avec vos mots", "add_hint": "Quelque chose que nous n'avons pas listé ? Décrivez-le en une ligne.",
        "add_title_label": "Le risque", "add_family": "C'est", "add_crit": "Cela touche",
        "mine": "Ajouté par vous", "risks_count": "{k} risques gardés sur {n}", "none_kept": "Aucun risque gardé pour l'instant. Gardez-en au moins un pour continuer.",
        "now_title": "Maintenant et après", "now_lead": "Pour chaque risque : sa gravité, sa vraisemblance, ce que vous faites déjà et ce que vous pourriez ajouter. Nous calculons les niveaux pour vous.",
        "now_empty": "Vous n'avez gardé aucun risque.", "now_empty_cta": "Choisir vos risques",
        "sev_q": "Quelle serait la gravité pour vous ?", "sev_proposed": "Nous proposons", "sev_keep": "Garder notre proposition",
        "sev_reason": "Pourquoi un autre niveau ?", "sev_reason_ph": "Nécessaire si vous choisissez un autre niveau", "err_sev_reason": "Dites-nous pourquoi vous avez choisi un autre niveau.",
        "lik_deliberate": "Quelle est la probabilité que quelqu'un tente cela contre vous dans l'année à venir ?",
        "lik_accidental": "Cela vous est-il arrivé au cours des 3 dernières années ?", "lik_skip": "Sans réponse",
        "lik_unlikely": "Peu probable : je ne m'y attends pas", "lik_possible": "Possible", "lik_likely": "Probable",
        "lik_very_likely": "Très probable : cela arrive peut-être déjà",
        "lik_never": "Non, jamais", "lik_once": "Oui, une fois", "lik_sometimes": "Oui, quelques fois", "lik_often": "Oui, régulièrement",
        "measures": "Ce qui aide", "measures_hint": "Pour chaque mesure : la faites-vous déjà, ou l'ajouteriez-vous ?",
        "m_none": "Pas maintenant", "m_in": "Déjà en place", "m_extra": "À ajouter à mon plan",
        "now_level": "Maintenant", "after_level": "Après vos mesures supplémentaires", "levels_note": "Les niveaux sont calculés par le moteur à partir de vos réponses.",
        "save_stay": "Enregistrer", "save_next": "Enregistrer et voir les résultats", "err_row": "Vérifiez ce risque : {msg}",
        "res_title": "Vos résultats", "res_lead": "Où vous en êtes maintenant, et où vous pourriez être après les mesures supplémentaires cochées.",
        "map_now": "Maintenant", "map_after": "Après vos mesures supplémentaires", "map_legend": "Les risques sur les cartes",
        "risk_col": "Risque", "now_col": "Maintenant", "after_col": "Après",
        "conf": "Confiance", "conf_text": "La part de ces résultats qui repose sur vos réponses plutôt que sur des hypothèses.",
        "band_low": "faible", "band_medium": "moyenne", "band_high": "élevée",
        "conf_cap": "Sans document, la confiance ne dépasse jamais {n} %.",
        "top5": "Vos actions prioritaires", "top5_empty": "Aucune action pour l'instant. Retournez à « Maintenant et après » et cochez les mesures que vous ajouteriez.",
        "top5_for": "Aide pour", "assumptions": "Ce que nous avons supposé", "assumptions_lead": "Merci de les vérifier. Chacune est un endroit où nous avons utilisé une valeur typique à la place de votre réponse.",
        "assumptions_none": "Aucune hypothèse : tout vient de vous.", "assumptions_kept": "Valeurs typiques que vous avez gardées (afficher)",
        "kind_default": "Sans réponse", "kind_dont_know": "Vous ne saviez pas", "kind_catalogue": "Valeur typique conservée",
        "facts_docs": "Documents", "facts_none": "aucun", "facts_missing": "Non fournis", "facts_answers": "Réponses",
        "facts_assumptions": "Hypothèses à confirmer", "doc_note": "Un document est conservé mais n'a pas encore été lu : il n'augmente pas la confiance.",
        "doc_architecture_short": "document d'architecture", "doc_business-impact_short": "analyse d'impact sur l'activité",
        "doc_security-baseline_short": "socle de sécurité", "doc_other_short": "autre document",
        "export": "Télécharger Excel", "export_json": "Télécharger le fichier d'étude", "expert": "Ouvrir en mode expert",
        "expert_hint": "Le mode expert montre la méthode complète (ateliers 1 à 5) sur la même étude. Les changements faits là-bas ne reviennent pas dans ces écrans : enregistrer un écran ici reconstruit l'étude à partir de vos réponses.",
        "edited": "Cette étude a été modifiée en mode expert. Enregistrer cet écran reconstruit l'étude à partir de vos réponses rapides et remplace ces modifications (la version précédente est gardée dans un fichier .bak).",
        "edit_answers": "Modifier mes réponses",
        "honesty": "Déclaration d'honnêteté",
    },
}


def tr(lang, key, **kw):
    s = T.get(lang, T["en"]).get(key)
    if s is None:
        s = T["en"][key]
    return s.format(**kw) if kw else s


def _pick(d, lang):
    """A catalogue text {"en": .., "fr": ..} in the page language."""
    return d.get(lang) or d.get("en") or ""


def honesty_box(lang):
    return (f'<aside class="honesty" aria-labelledby="honesty-h"><h2 id="honesty-h">{esc(tr(lang, "honesty"))}</h2>'
            f'<p lang="{esc(lang)}">{esc(engine.HONESTY.get(lang) or engine.HONESTY["en"])}</p></aside>')


def stepper(sid, current, lang, reachable=True):
    n = STEPS.index(current) + 1
    items = []
    for i, key in enumerate(STEPS, 1):
        label = tr(lang, f"step_{key}")
        href = f"/quick/{sid}/{key}" if sid and reachable else None
        cls = "current" if key == current else ("done" if i < n else "todo")
        inner = f'<span class="n">{i}</span><span class="t">{esc(label)}</span>'
        cur = ' aria-current="step"' if key == current else ""
        items.append(f'<li class="{cls}">' + (f'<a href="{href}"{cur}>{inner}</a>' if href else f'<span{cur}>{inner}</span>') + "</li>")
    return (f'<nav class="stepper" aria-label="{esc(tr(lang, "steps_label"))}"><p class="step-count">{esc(tr(lang, "step_of", n=n))}</p>'
            f'<ol>{"".join(items)}</ol></nav>')


def _flash(lang, flash):
    return f'<p class="flash" role="status">{esc(tr(lang, "saved"))}</p>' if flash == "saved" else ""


def _err(msg):
    return f'<span class="field-error" role="alert">{esc(msg)}</span>' if msg else ""


def _edited_banner(lang, edited):
    return f'<p class="notice" role="note">{esc(tr(lang, "edited"))}</p>' if edited else ""


# ------------------------------------------------------------------ home

def home(session, lang, recent, flash=""):
    """recent: [(sid, name, mtime, step)] quick studies, newest first."""
    ways = [("1", "/quick/new", "way1", "primary"), ("2", "/quick/new?doc=1", "way2", ""), ("3", "/reviews", "way3", "")]
    cards = "".join(
        f'<a class="way {cls}" href="{href}{"&" if "?" in href else "?"}lang={lang}"><span class="way-n" aria-hidden="true">{n}</span>'
        f'<span class="way-t">{esc(tr(lang, key))}</span><span class="way-d">{esc(tr(lang, key + "_text"))}</span>'
        f'<span class="way-go">{esc(tr(lang, key + "_go"))} <span aria-hidden="true">&rarr;</span></span></a>'
        for n, href, key, cls in ways)
    if recent:
        rows = "".join(
            f'<li><a href="/quick/{sid}/{step}?lang={lang}"><span class="r-name">{esc(name)}</span>'
            f'<span class="r-when">{esc(when(mt))}</span></a></li>' for sid, name, mt, step in recent)
        cont = f'<ul class="recent">{rows}</ul>'
    else:
        cont = f'<p class="empty-state">{esc(tr(lang, "continue_none"))}</p>'
    body = f"""<section class="hero"><h1>{esc(tr(lang, "home_title"))}</h1><p class="lead">{esc(tr(lang, "home_lead"))}</p></section>
{honesty_box(lang)}
<section class="ways" aria-label="{esc(tr(lang, "home_title"))}">{cards}</section>
<section class="continue"><h2>{esc(tr(lang, "continue"))}</h2>{cont}
<p><a href="/studies">{esc(tr(lang, "all_studies"))}</a></p></section>"""
    return page(tr(lang, "home_title"), body, session, flash=flash, lang=lang, lang_path="/")


# ------------------------------------------------------------------ screen 1: about you

def about(session, sid, lang, cat, state, errors=None, doc_open=False, edited=False, flash="", doc=None):
    """state: the profile being edited (the "profile" object of the quick answers, or what was typed)."""
    errors = errors or {}
    prof = state or {}

    def slot(key):
        s = prof.get(key)
        return s if isinstance(s, dict) else {}

    def dk(key, checked):
        return (f'<label class="dk"><input type="checkbox" name="{key}_dk" value="1"{" checked" if checked else ""}> '
                f'{esc(tr(lang, "dk"))}</label>')
    vals = "\n".join(slot("values").get("value") or [])
    tools_chosen = set(slot("tools").get("value") or [])
    tool_boxes = "".join(
        f'<label class="choice"><input type="checkbox" name="tools" value="{esc(t["id"])}"{" checked" if t["id"] in tools_chosen else ""}>'
        f'<span class="c-t">{esc(_pick(t, lang))}</span><span class="c-d">{esc(_pick(t["example"], lang))}</span></label>'
        for t in cat["tools"])

    def radios(name, keys, prefix, current):
        out = "".join(
            f'<label class="choice"><input type="radio" name="{name}" value="{k}"{" checked" if current == k else ""}>'
            f'<span class="c-t">{esc(tr(lang, prefix + k))}</span></label>' for k in keys)
        return out + (f'<label class="choice dk-choice"><input type="radio" name="{name}" value="dont_know"'
                      f'{" checked" if current == "dont_know" else ""}><span class="c-t">{esc(tr(lang, "dk"))}</span></label>')
    cur_down = "dont_know" if slot("downtime").get("dont_know") else slot("downtime").get("answer")
    cur_sens = "dont_know" if slot("sensitivity").get("dont_know") else slot("sensitivity").get("answer")
    doc = doc or {}
    have = (f'<p class="doc-have">{esc(tr(lang, "doc_have", name=doc.get("filename") or ""))}</p>') if doc.get("provided") else ""
    kinds = "".join(f'<option value="{k}"{" selected" if (doc.get("kind") or state.get("doc_kind")) == k else ""}>{esc(tr(lang, "doc_" + k))}</option>'
                    for k in engine.DOCUMENT_KINDS)
    action = f"/quick/{sid}/about" if sid else "/quick/new"
    doc_attr = " open" if doc_open or doc.get("provided") or errors.get("doc") else ""
    body = f"""{stepper(sid, "about", lang, reachable=bool(sid))}
<h1>{esc(tr(lang, "about_title"))}</h1><p class="lead">{esc(tr(lang, "about_lead"))}</p>
{_flash(lang, flash)}{_edited_banner(lang, edited)}
<form method="post" action="{action}" enctype="multipart/form-data" class="flow">{csrf_input(session)}
<input type="hidden" name="lang" value="{esc(lang)}">
<section class="q"><label for="f-name"><span class="q-t">{esc(tr(lang, "q_name"))}</span><span class="example">{esc(tr(lang, "q_name_ex"))}</span></label>
<input id="f-name" name="name" value="{esc(prof.get("name", ""))}" maxlength="200" required>{_err(errors.get("name"))}</section>
<section class="q"><label for="f-activity"><span class="q-t">{esc(tr(lang, "q_activity"))}</span><span class="example">{esc(tr(lang, "q_activity_ex"))}</span></label>
<textarea id="f-activity" name="activity" rows="3" maxlength="2000">{esc(slot("activity").get("value", ""))}</textarea>
{dk("activity", slot("activity").get("dont_know"))}</section>
<section class="q"><label for="f-values"><span class="q-t">{esc(tr(lang, "q_values"))}</span><span class="example">{esc(tr(lang, "q_values_ex"))}</span></label>
<textarea id="f-values" name="values" rows="5">{esc(vals)}</textarea>{_err(errors.get("values"))}
{dk("values", slot("values").get("dont_know"))}</section>
<fieldset class="q"><legend><span class="q-t">{esc(tr(lang, "q_tools"))}</span><span class="example">{esc(tr(lang, "q_tools_ex"))}</span></legend>
<div class="choice-grid">{tool_boxes}</div>{dk("tools", slot("tools").get("dont_know"))}</fieldset>
<fieldset class="q"><legend><span class="q-t">{esc(tr(lang, "q_downtime"))}</span></legend>
<div class="choice-grid">{radios("downtime", engine.DOWNTIME_KEYS, "downtime_", cur_down)}</div></fieldset>
<fieldset class="q"><legend><span class="q-t">{esc(tr(lang, "q_sensitivity"))}</span></legend>
<div class="choice-grid">{radios("sensitivity", engine.SENSITIVITY_KEYS, "sens_", cur_sens)}</div></fieldset>
<details class="q doc"{doc_attr}><summary><span class="q-t">{esc(tr(lang, "q_doc"))}</span> <span class="opt">({esc(tr(lang, "optional"))})</span></summary>
<p class="example">{esc(tr(lang, "q_doc_ex"))}</p>{have}
<label>{esc(tr(lang, "doc_kind"))} <select name="doc_kind">{kinds}</select></label>
<label>{esc(tr(lang, "doc_replace") if doc.get("provided") else tr(lang, "doc_file"))} <input type="file" name="document" accept=".txt,.md,.docx,.pdf"></label>
{_err(errors.get("doc"))}</details>
<div class="actions"><button class="primary big">{esc(tr(lang, "continue_btn"))} <span aria-hidden="true">&rarr;</span></button></div>
</form>"""
    return page(tr(lang, "about_title"), body, session, lang=lang, lang_path=action)


# ------------------------------------------------------------------ screen 2: risks

def _risk_card(lang, rdef, kept, reason, errors, mine=False):
    rid = rdef["id"]
    crit = ", ".join(tr(lang, "criteria_" + c) for c in rdef["criteria"])
    always = rdef.get("always_assessed")
    badges = []
    if always:
        badges.append(f'<span class="badge always">{esc(tr(lang, "always"))}</span>')
    if mine:
        badges.append(f'<span class="badge mine">{esc(tr(lang, "mine"))}</span>')
    typology = ""
    if rdef["family"] == "deliberate" and rdef.get("origin"):
        typology = (f'<p class="meta">{esc(tr(lang, "typology"))}: {esc(rdef["_origin"])} &middot; {esc(rdef["_objective"])}</p>')
    reason_html = ""
    if always:
        reason_html = (f'<div class="reason{" needed" if errors.get(rid) else ""}"><label for="r-{esc(rid)}">{esc(tr(lang, "always_hint"))}</label>'
                       f'<input id="r-{esc(rid)}" name="reason_{esc(rid)}" value="{esc(reason)}" maxlength="500" '
                       f'placeholder="{esc(tr(lang, "reason_ph"))}">{_err(errors.get(rid))}</div>')
    desc = _pick(rdef["description"], lang)
    return f"""<article class="risk-card{" has-error" if errors.get(rid) else ""}">
<label class="keep"><input class="keep-box" type="checkbox" name="keep" value="{esc(rid)}"{" checked" if kept else ""}>
<span class="r-title">{esc(_pick(rdef["title"], lang))}</span></label>
<div class="badges">{"".join(badges)}</div>
<p class="r-desc">{esc(desc)}</p>
<p class="meta">{esc(tr(lang, "hits"))}: {esc(crit)}</p>{typology}{reason_html}</article>"""


def risks(session, sid, lang, cat, quick, state=None, errors=None, edited=False, flash=""):
    """state: {"keep": {id: bool}, "reasons": {id: text}, "new": [{"title","family","criteria"}]} when a form was refused."""
    errors = errors or {}
    state = state or {}
    by_id = {r["id"]: r for r in cat["risks"]}
    keep_state = state.get("keep") or {}
    origins = {o["id"]: o for o in cat["origins"]}
    objectives = {o["id"]: o for o in cat["objectives"]}
    groups = {"deliberate": [], "accidental": []}
    n_kept = 0
    for e in quick.get("risks") or []:
        custom = e.get("custom")
        if custom:
            fam = custom.get("family") if custom.get("family") in groups else "accidental"
            rdef = {"id": e["id"], "family": fam, "title": {"en": custom.get("title", ""), "fr": custom.get("title", "")},
                    "description": {"en": custom.get("description", ""), "fr": custom.get("description", "")},
                    "criteria": custom.get("criteria") or list(("confidentiality", "integrity", "availability")), "always_assessed": False}
        else:
            rdef = dict(by_id[e["id"]])
            if rdef["family"] == "deliberate":
                rdef["_origin"] = _pick(origins[rdef["origin"]], lang)
                rdef["_objective"] = _pick(objectives[rdef["objective"]], lang)
        kept = keep_state.get(e["id"], e.get("decision") == "keep")
        reason = (state.get("reasons") or {}).get(e["id"], e.get("reason") or "")
        groups[rdef["family"]].append(_risk_card(lang, rdef, kept, reason, errors, mine=bool(custom)))
        n_kept += 1 if kept else 0
    sections = ""
    for fam in ("deliberate", "accidental"):
        if groups[fam]:
            sections += (f'<section class="family"><h2>{esc(tr(lang, "fam_" + fam))}</h2><p class="hint">{esc(tr(lang, "fam_" + fam + "_text"))}</p>'
                         f'{"".join(groups[fam])}</section>')
    new_rows = state.get("new") or [{}, {}, {}]
    crit_names = ("confidentiality", "integrity", "availability")
    add_rows = ""
    for i, row in enumerate(new_rows[:3], 1):
        fam = row.get("family") or "accidental"
        crit = set(row.get("criteria") or [])
        fam_opts = "".join(f'<option value="{f}"{" selected" if fam == f else ""}>{esc(tr(lang, "fam_" + f))}</option>' for f in ("deliberate", "accidental"))
        boxes = "".join(f'<label class="check"><input type="checkbox" name="new_crit_{i}" value="{c}"{" checked" if c in crit else ""}> '
                        f'{esc(tr(lang, "criteria_" + c))}</label>' for c in crit_names)
        add_rows += (f'<div class="add-row"><label>{esc(tr(lang, "add_title_label"))} <input name="new_title_{i}" maxlength="200" '
                     f'value="{esc(row.get("title", ""))}"></label>'
                     f'<label>{esc(tr(lang, "add_family"))} <select name="new_family_{i}">{fam_opts}</select></label>'
                     f'<fieldset class="inline-set"><legend>{esc(tr(lang, "add_crit"))}</legend>{boxes}</fieldset></div>')
    count = tr(lang, "risks_count", k=n_kept, n=len(quick.get("risks") or []))
    body = f"""{stepper(sid, "risks", lang)}
<h1>{esc(tr(lang, "risks_title"))}</h1><p class="lead">{esc(tr(lang, "risks_lead"))}</p>
{_flash(lang, flash)}{_edited_banner(lang, edited)}
<form method="post" action="/quick/{sid}/risks" class="flow">{csrf_input(session)}
<input type="hidden" name="lang" value="{esc(lang)}">
<p class="count-line" role="status">{esc(count)}</p>
{sections}
<details class="q add"{" open" if state.get("new") else ""}><summary><span class="q-t">{esc(tr(lang, "add_title"))}</span></summary>
<p class="example">{esc(tr(lang, "add_hint"))}</p>{add_rows}{_err(errors.get("new"))}</details>
<div class="actions"><a class="button secondary" href="/quick/{sid}/about">{esc(tr(lang, "back"))}</a>
<button class="primary big">{esc(tr(lang, "continue_btn"))} <span aria-hidden="true">&rarr;</span></button></div>
</form>"""
    return page(tr(lang, "risks_title"), body, session, lang=lang, lang_path=f"/quick/{sid}/risks")


# ------------------------------------------------------------------ screen 3: now and after

def _level_chip(cal, name, cls):
    return f'<span class="lvl {cls.get(name, "")}">{esc(name)}</span>'


def now(session, sid, lang, cat, quick, cal, rows, state=None, errors=None, edited=False, flash=""):
    """rows: engine.quick_compute rows (one per kept risk). state: {"sev": {id: v}, "sevreason": {id: t}, "lik": {id: v},
    "in": {id: [..]}, "extra": {id: [..]}} when a form was refused, to show what was typed."""
    errors = errors or {}
    state = state or {}
    cls = level_classes(cal)
    saved = {e["id"]: e for e in quick.get("risks") or []}
    cards = []
    for r in rows:
        rid, d = r["id"], r["def"]
        e = saved[rid]
        sev_value = (state.get("sev") or {}).get(rid, (e.get("severity") or {}).get("value"))
        sev_reason = (state.get("sevreason") or {}).get(rid, (e.get("severity") or {}).get("reason") or "")
        lik_value = (state.get("lik") or {}).get(rid, (e.get("likelihood") or {}).get("answer") or "")
        in_place = set((state.get("in") or {}).get(rid, r["in_place"]))
        extra = set((state.get("extra") or {}).get(rid, r["extra"]))
        words = engine.SEVERITY_WORDS[lang]
        proposed = r["severity_proposed"]
        sev_opts = f'<option value="">{esc(tr(lang, "sev_keep"))} ({esc(words[proposed].split(":")[0])})</option>' + "".join(
            f'<option value="{n}"{" selected" if sev_value == n or str(sev_value) == str(n) else ""}>{esc(words[n])}</option>'
            for n in (1, 2, 3, 4) if n != proposed)
        fam = d["family"]
        lik_opts = f'<option value="">{esc(tr(lang, "lik_skip"))}</option>' + "".join(
            f'<option value="{k}"{" selected" if lik_value == k else ""}>{esc(tr(lang, "lik_" + k))}</option>' for k in engine.LIKELIHOOD_KEYS[fam]) + (
            f'<option value="dont_know"{" selected" if lik_value == "dont_know" else ""}>{esc(tr(lang, "dk"))}</option>')

        def measure_rows():
            out = []
            for m in d["measures"]:
                cur = "in" if m["id"] in in_place else ("extra" if m["id"] in extra else "")
                name = f"m_{rid}_{m['id']}"
                radios = "".join(
                    f'<label class="seg-opt"><input type="radio" name="{esc(name)}" value="{v}"{" checked" if cur == v else ""}>'
                    f'<span>{esc(tr(lang, "m_" + (v or "none")))}</span></label>' for v in ("", "in", "extra"))
                out.append(f'<div class="meas-row" role="group" aria-labelledby="mt-{esc(rid)}-{esc(m["id"])}">'
                           f'<p class="m-t" id="mt-{esc(rid)}-{esc(m["id"])}">{esc(_pick(m, lang))}</p><div class="seg">{radios}</div></div>')
            return "".join(out)
        result = (f'<p class="result" aria-live="polite"><span>{esc(tr(lang, "now_level"))}: {_level_chip(cal, r["level"], cls)}</span>'
                  f'<span aria-hidden="true">&rarr;</span>'
                  f'<span>{esc(tr(lang, "after_level"))}: {_level_chip(cal, r["level_target"], cls)}</span></p>')
        sev_err = errors.get(rid)
        cards.append(f"""<article class="row-card{" has-error" if sev_err else ""}" id="risk-{esc(rid)}">
<header><h2><span class="rid">{esc(rid)}</span> {esc(_pick(d["title"], lang))}</h2><p class="r-desc">{esc(_pick(d["description"], lang))}</p></header>
<div class="row-grid">
<div class="blk sev"><label for="sev-{esc(rid)}"><span class="q-t">{esc(tr(lang, "sev_q"))}</span></label>
<p class="proposed">{esc(tr(lang, "sev_proposed"))}: <strong>{esc(words[proposed])}</strong>
<small>({esc(scale_text(cal, "severity", proposed))})</small></p>
<select id="sev-{esc(rid)}" name="sev_{esc(rid)}">{sev_opts}</select>
<div class="reason{" needed" if sev_err else ""}"><label for="sr-{esc(rid)}">{esc(tr(lang, "sev_reason"))}</label>
<input id="sr-{esc(rid)}" name="sevreason_{esc(rid)}" value="{esc(sev_reason)}" maxlength="500" placeholder="{esc(tr(lang, "sev_reason_ph"))}">{_err(sev_err)}</div></div>
<div class="blk lik"><label for="lik-{esc(rid)}"><span class="q-t">{esc(tr(lang, "lik_" + fam))}</span></label>
<select id="lik-{esc(rid)}" name="lik_{esc(rid)}">{lik_opts}</select></div>
</div>
<fieldset class="blk meas"><legend><span class="q-t">{esc(tr(lang, "measures"))}</span> <small>{esc(tr(lang, "measures_hint"))}</small></legend>{measure_rows()}</fieldset>{result}</article>""")
    if cards:
        main = "".join(cards)
        actions = (f'<div class="actions"><a class="button secondary" href="/quick/{sid}/risks">{esc(tr(lang, "back"))}</a>'
                   f'<button class="secondary big" name="go" value="stay">{esc(tr(lang, "save_stay"))}</button>'
                   f'<button class="primary big" name="go" value="next">{esc(tr(lang, "save_next"))} <span aria-hidden="true">&rarr;</span></button></div>')
        form = (f'<form method="post" action="/quick/{sid}/now" class="flow">{csrf_input(session)}<input type="hidden" name="lang" value="{esc(lang)}">'
                f'<p class="hint">{esc(tr(lang, "levels_note"))}</p>{main}{actions}</form>')
    else:
        form = (f'<div class="empty-state"><p>{esc(tr(lang, "now_empty"))}</p>'
                f'<a class="button primary" href="/quick/{sid}/risks">{esc(tr(lang, "now_empty_cta"))}</a></div>')
    body = f"""{stepper(sid, "now", lang)}
<h1>{esc(tr(lang, "now_title"))}</h1><p class="lead">{esc(tr(lang, "now_lead"))}</p>
{_flash(lang, flash)}{_edited_banner(lang, edited)}{form}"""
    return page(tr(lang, "now_title"), body, session, cal_id=cal["id"], lang=lang, lang_path=f"/quick/{sid}/now")


# ------------------------------------------------------------------ screen 4: results

def results(session, sid, lang, cat, quick, cal, rows, reg_rows, facts, actions, assumptions, edited=False, can_xlsx=True):
    cls = level_classes(cal)
    conf, band = facts["confidence"], facts["band"]
    doc_names = ", ".join(tr(lang, f"doc_{k}_short") for k in facts["documents"]) or tr(lang, "facts_none")
    missing = ", ".join(tr(lang, f"doc_{k}_short") for k in facts["not_provided"]) or tr(lang, "facts_none")
    line = (f'{tr(lang, "facts_docs")}: {doc_names}. {tr(lang, "facts_missing")}: {missing}. '
            f'{tr(lang, "facts_answers")}: {facts["answers"]}. {tr(lang, "facts_assumptions")}: {facts["assumptions"]}. '
            f'{tr(lang, "conf")}: {conf} % ({tr(lang, "band_" + band)}).')
    doc_note = f'<p class="hint">{esc(tr(lang, "doc_note"))}</p>' if facts["document_provided"] else ""
    cap = f'<p class="hint">{esc(tr(lang, "conf_cap", n=engine.NO_DOCUMENT_CEILING))}</p>' if not facts["document_provided"] else ""
    maps = ""
    if reg_rows:
        maps = (f'<div class="maps"><figure><figcaption>{esc(tr(lang, "map_now"))}</figcaption>{engine.risk_map(reg_rows, cal, "now", tr(lang, "map_now"))}</figure>'
                f'<figure><figcaption>{esc(tr(lang, "map_after"))}</figcaption>{engine.risk_map(reg_rows, cal, "target", tr(lang, "map_after"))}</figure></div>')
        legend = "".join(
            f'<tr><th scope="row">{esc(r["id"])}</th><td>{esc(_pick(r["def"]["title"], lang))}</td>'
            f'<td>{_level_chip(cal, r["level"], cls)}</td><td>{_level_chip(cal, r["level_target"], cls)}</td></tr>' for r in rows)
        maps += (f'<details class="legend-table" open><summary>{esc(tr(lang, "map_legend"))}</summary><div class="scroll"><table class="list">'
                 f'<thead><tr><th>#</th><th>{esc(tr(lang, "risk_col"))}</th><th>{esc(tr(lang, "now_col"))}</th><th>{esc(tr(lang, "after_col"))}</th></tr></thead>'
                 f'<tbody>{legend}</tbody></table></div></details>')
    else:
        maps = (f'<div class="empty-state"><p>{esc(tr(lang, "now_empty"))}</p>'
                f'<a class="button primary" href="/quick/{sid}/risks">{esc(tr(lang, "now_empty_cta"))}</a></div>')
    if actions:
        acts = "".join(
            f'<li><span class="a-n">{i}</span><div><p class="a-t">{esc(_pick(a, lang))}</p>'
            f'<p class="meta">{esc(tr(lang, "top5_for"))}: {esc(", ".join(a["risks"]))}</p></div></li>' for i, a in enumerate(actions, 1))
        top = f'<ol class="actions-list">{acts}</ol>'
    else:
        top = f'<p class="empty-state">{esc(tr(lang, "top5_empty"))}</p>'
    kinds = {"default": "kind_default", "dont_know": "kind_dont_know", "catalogue": "kind_catalogue"}
    main_ass = [a for a in assumptions if a["kind"] != "catalogue"]
    cat_ass = [a for a in assumptions if a["kind"] == "catalogue"]

    def li(a):
        return f'<li><span class="badge k-{esc(a["kind"])}">{esc(tr(lang, kinds[a["kind"]]))}</span> {esc(_pick(a["text"], lang))}</li>'
    ass = (f'<ul class="assumptions">{"".join(li(a) for a in main_ass)}</ul>' if main_ass else f'<p class="ok">{esc(tr(lang, "assumptions_none"))}</p>')
    if cat_ass:
        ass += f'<details><summary>{esc(tr(lang, "assumptions_kept"))} ({len(cat_ass)})</summary><ul class="assumptions">{"".join(li(a) for a in cat_ass)}</ul></details>'
    export = (f'<a class="button primary" href="/s/{sid}/export.xlsx">{esc(tr(lang, "export"))}</a>' if can_xlsx else "")
    body = f"""{stepper(sid, "results", lang)}
<h1>{esc(tr(lang, "res_title"))}</h1><p class="lead">{esc(tr(lang, "res_lead"))}</p>
{_edited_banner(lang, edited)}
{honesty_box(lang)}
<section class="card conf"><div class="conf-n"><span class="big-n">{conf}%</span><span class="band b-{esc(band)}">{esc(tr(lang, "band_" + band))}</span></div>
<div><h2>{esc(tr(lang, "conf"))}</h2><progress max="100" value="{conf}" aria-label="{esc(tr(lang, "conf"))}">{conf}%</progress>
<p>{esc(tr(lang, "conf_text"))}</p>{cap}{doc_note}<p class="facts">{esc(line)}</p></div></section>
<section class="card"><h2>{esc(tr(lang, "map_now"))} &rarr; {esc(tr(lang, "map_after"))}</h2>{maps}</section>
<section class="card"><h2>{esc(tr(lang, "top5"))}</h2>{top}</section>
<section class="card"><h2>{esc(tr(lang, "assumptions"))}</h2><p class="hint">{esc(tr(lang, "assumptions_lead"))}</p>{ass}</section>
<section class="card next-steps"><div class="btns">{export}
<a class="button secondary" href="/s/{sid}/export.json">{esc(tr(lang, "export_json"))}</a>
<a class="button secondary" href="/quick/{sid}/about">{esc(tr(lang, "edit_answers"))}</a>
<a class="button secondary" href="/s/{sid}" rel="nofollow">{esc(tr(lang, "expert"))}</a></div>
<p class="hint">{esc(tr(lang, "expert_hint"))}</p></section>"""
    return page(tr(lang, "res_title"), body, session, cal_id=cal["id"], lang=lang, lang_path=f"/quick/{sid}/results")
