"""Quick-path pages: the home page and the four screens (About you, Risks, Now and after, Results).

Text is in English and French (T). Every piece of user or catalogue text goes through esc(). Levels, confidence and
the honesty statement are the engine's; nothing here computes a level.
"""
import html as html_mod

from . import engine, labels
from .views import csrf_input, esc, level_classes, page, when

STEPS = ("about", "risks", "now", "results")

T = {
    "en": {
        'home_title': 'Know your main risks in about 15 minutes',
        'home_page_title': 'Know your main risks',
        'home_lead': 'A few plain questions show what already works and what to do first.',
        'start': 'Start',
        'built_on': 'Built on EBIOS Risk Manager, the method of ANSSI, the French national cybersecurity agency',
        'built_on_link': 'How it works',
        'continue': 'Pick up where you left off',
        'continue_none': 'Your analyses will appear here, ready to pick up later.',
        'all_studies': 'All your saved studies',
        'step_of': 'Step {n} of 4',
        'step_about': 'About you',
        'step_risks': 'Risks that apply',
        'step_now': 'Now and after',
        'step_results': 'Results',
        'steps_label': 'Your progress',
        'saved': 'Saved.',
        'back': 'Back',
        'continue_btn': 'Save and continue',
        'save_btn': 'Save',
        'dk': 'Not sure',
        'about_title': 'About you',
        'about_lead': 'Answer what you can. Anything you are unsure about gets a typical value, and we tell you.',
        'q_name': 'Give this analysis a name',
        'q_name_ex': 'For example: Our company, spring review',
        'q_activity': 'What does your organisation do?',
        'q_activity_ex': 'For example: we run three bakeries and deliver to local shops.',
        'q_values': 'What matters most to you? (up to 5 things, one per line, most important first)',
        'q_values_ex': 'For example: taking orders, our customer list, the payroll, the production line.',
        'q_tools': 'What do you use?',
        'q_tools_ex': 'Tick everything that applies. This decides which risks we suggest.',
        'q_downtime': 'If your main tools stopped, how soon would it really hurt?',
        'q_downtime_ex': 'For example: email, orders and the till all stop at once.',
        'q_sensitivity': 'How sensitive is the information you hold?',
        'q_sensitivity_ex': 'For example: would a customer, a patient or a regulator be upset to see it?',
        'downtime_hours': 'Within a few hours',
        'downtime_day': 'Within a day or two',
        'downtime_days': 'Within a week',
        'downtime_week': 'We could manage for more than a week',
        'sens_public': 'Mostly public, or of little interest to others',
        'sens_internal': 'Internal, but harmless if it leaked',
        'sens_confidential': 'Customer, personal or financial data',
        'sens_critical': 'Secrets, health or legal data: a leak would be serious',
        'err_name': 'Give the analysis a name (up to 200 characters).',
        'err_values': 'Up to 5 things; each at most 200 characters.',
        'risks_title': 'Risks that typically apply to you',
        'risks_lead': 'A public list, chosen from your answers. Keep what fits, drop the rest, add your own.',
        'fam_deliberate': 'Someone does it on purpose',
        'fam_deliberate_text': 'A person or a group, for example after money or information.',
        'fam_accidental': 'Things go wrong',
        'fam_accidental_text': 'Mistakes, failures, outages, loss and natural events.',
        'keep': 'Keep this risk',
        'always': 'We always check this one',
        'always_hint': 'If you discard it, tell us why.',
        'reason_ph': 'Why can this one be set aside?',
        'err_reason': 'Tell us why you set this risk aside.',
        'hits': 'Affects',
        'criteria_confidentiality': 'who can see it',
        'criteria_integrity': 'whether it is correct',
        'criteria_availability': 'whether you can use it',
        'typology': 'Who and why',
        'add_title': 'Add a risk in your own words',
        'add_hint': 'Something to add? Describe it in one line.',
        'add_title_label': 'The risk',
        'add_family': 'It is',
        'add_crit': 'It affects',
        'mine': 'Added by you',
        'more_risks': 'More risks you can add ({n})',
        'more_hint': 'These apply less often. Tick any that fit you.',
        'risks_count': '{k} of {n} risks kept',
        'none_kept': 'Keep at least one risk to continue.',
        'now_title': 'Now and after',
        'now_lead': 'Rate each risk, then tick what you already do and what you would add.',
        'now_risks_h': 'Your risks',
        'now_meas_h': 'What helps your whole business',
        'now_meas_lead': 'Answer each measure once. It counts for every risk it helps with.',
        'sev_q': 'How much would it matter to you?',
        'now_empty': 'Choose your risks first, then come back here.',
        'now_empty_cta': 'Choose your risks',
        'sev_keep': 'Keep our suggestion',
        'sev_reason': 'Why another level?',
        'sev_reason_ph': 'Needed when you choose another level',
        'err_sev_reason': 'Tell us why you chose another level.',
        'lik_deliberate': 'How likely is it that someone tries this in the coming year?',
        'lik_accidental': 'Has this happened to you in the last 3 years?',
        'lik_skip': 'Skip for now',
        'lik_unlikely': 'Unlikely',
        'lik_possible': 'Possible',
        'lik_likely': 'Likely',
        'lik_very_likely': 'Very likely: it may already be happening',
        'lik_never': 'No',
        'lik_once': 'Yes, once',
        'lik_sometimes': 'Yes, a few times',
        'lik_often': 'Yes, regularly',
        'measures': 'What helps',
        'm_none': 'Later',
        'm_in': 'Already in place',
        'm_extra': 'Add to my plan',
        'now_level': 'Now',
        'after_level': 'After your extra measures',
        'save_stay': 'Save',
        'save_next': 'Save and see the results',
        'err_row': 'Check this risk: {msg}',
        'res_title': 'Your results',
        'see_all': 'See all your risks ({n})',
        'in_place_h': 'Already in place ({n})',
        'rough': 'Rough guide',
        'rough_text': 'time and who are estimates.',
        'map_key': 'Your risks on the maps',
        'conf_cap': 'up to {n}%',
        'assumed_h': 'What we assumed ({n})',
        'in_place': 'Already in place',
        'in_place_none': 'Tick what you already do in “Now and after”: it appears here.',
        'risks_h': 'Your risks',
        'map_now': 'Now',
        'map_after': 'After your extra measures',
        'risk_col': 'Risk',
        'now_col': 'Now',
        'after_col': 'After',
        'conf': 'Confidence',
        'band_low': 'low',
        'band_medium': 'medium',
        'band_high': 'high',
        'top5': 'Your top actions',
        'top5_empty': 'Tick the measures you would add in “Now and after”: your actions appear here.',
        'assumptions': 'What we assumed',
        'assumptions_lead': 'Places where we used a typical value. Check them when you can.',
        'assumptions_none': 'Every question was answered by you.',
        'assumptions_kept': 'Typical values you kept (show)',
        'kind_default': 'Left open',
        'kind_dont_know': 'Not sure',
        'kind_catalogue': 'Typical value kept',
        'export': 'Download Excel',
        'xlsx_missing': 'Add the openpyxl package to enable the Excel download. The study file download is ready now.',
        'export_json': 'Download the study file',
        'expert': 'Open in expert view',
        'edited': 'This study was changed in expert mode. Saving this screen rebuilds the study from your quick answers and replaces those changes (the previous version is kept as a .bak file).',
        'edit_answers': 'Change my answers',
        'honesty': 'Honesty statement',
        'gap_lbl': 'To strengthen',
        'evid_lbl': 'Based on',
        'fix_lbl': 'Next step',
    },
    "fr": {
        'home_title': 'Connaître vos principaux risques en 15 minutes environ',
        'home_page_title': 'Connaître vos principaux risques',
        'home_lead': 'Quelques questions simples montrent ce qui fonctionne déjà et par quoi commencer.',
        'start': 'Commencer',
        'built_on': "Fondé sur EBIOS Risk Manager, la méthode de l'ANSSI, l'agence nationale française de la cybersécurité",
        'built_on_link': 'Comment ça marche',
        'continue': 'Reprendre là où vous en étiez',
        'continue_none': 'Vos analyses apparaîtront ici, prêtes à être reprises.',
        'all_studies': 'Toutes vos études enregistrées',
        'step_of': 'Étape {n} sur 4',
        'step_about': 'Vous',
        'step_risks': 'Risques concernés',
        'step_now': 'Maintenant et après',
        'step_results': 'Résultats',
        'steps_label': 'Votre progression',
        'saved': 'Enregistré.',
        'back': 'Retour',
        'continue_btn': 'Enregistrer et continuer',
        'save_btn': 'Enregistrer',
        'dk': 'Pas sûr',
        'about_title': 'Vous',
        'about_lead': 'Répondez à ce que vous pouvez. Ce dont vous êtes peu sûr reçoit une valeur typique, et nous vous le disons.',
        'q_name': 'Donnez un nom à cette analyse',
        'q_name_ex': 'Par exemple : Notre société, bilan de printemps',
        'q_activity': 'Que fait votre organisation ?',
        'q_activity_ex': 'Par exemple : nous gérons trois boulangeries et livrons des commerces locaux.',
        'q_values': "Qu'est-ce qui compte le plus pour vous ? (jusqu'à 5 éléments, un par ligne, le plus important d'abord)",
        'q_values_ex': 'Par exemple : prendre les commandes, notre fichier clients, la paie, la ligne de production.',
        'q_tools': "Qu'utilisez-vous ?",
        'q_tools_ex': "Cochez tout ce qui s'applique. Cela détermine les risques proposés.",
        'q_downtime': "Si vos outils principaux s'arrêtaient, au bout de combien de temps cela ferait-il vraiment mal ?",
        'q_downtime_ex': "Par exemple : la messagerie, les commandes et la caisse s'arrêtent en même temps.",
        'q_sensitivity': 'Quelle est la sensibilité des informations que vous détenez ?',
        'q_sensitivity_ex': 'Par exemple : un client, un patient ou une autorité serait-il contrarié de les voir ?',
        'downtime_hours': 'En quelques heures',
        'downtime_day': 'En un jour ou deux',
        'downtime_days': 'En une semaine',
        'downtime_week': "Nous tiendrions plus d'une semaine",
        'sens_public': "Surtout publiques, ou d'un intérêt limité pour d'autres",
        'sens_internal': 'Internes, sans grande conséquence si elles fuitaient',
        'sens_confidential': 'Données de clients, personnelles ou financières',
        'sens_critical': 'Secrets, données de santé ou juridiques : une fuite serait grave',
        'err_name': "Donnez un nom à l'analyse (200 caractères au plus).",
        'err_values': '5 éléments au plus ; 200 caractères au plus chacun.',
        'risks_title': 'Les risques qui vous concernent typiquement',
        'risks_lead': "Une liste publique, choisie d'après vos réponses. Gardez ce qui convient, écartez le reste, ajoutez les vôtres.",
        'fam_deliberate': "Quelqu'un le fait exprès",
        'fam_deliberate_text': "Une personne ou un groupe, par exemple pour de l'argent ou des informations.",
        'fam_accidental': 'Ça se passe mal',
        'fam_accidental_text': 'Erreurs, pannes, interruptions, pertes et événements naturels.',
        'keep': 'Garder ce risque',
        'always': 'Nous vérifions toujours celui-ci',
        'always_hint': "Si vous l'écartez, dites-nous pourquoi.",
        'reason_ph': "Pourquoi peut-on l'écarter ?",
        'err_reason': 'Dites-nous pourquoi vous écartez ce risque.',
        'hits': 'Touche',
        'criteria_confidentiality': 'qui peut le voir',
        'criteria_integrity': "s'il est correct",
        'criteria_availability': "si vous pouvez l'utiliser",
        'typology': 'Qui et pourquoi',
        'add_title': 'Ajouter un risque avec vos mots',
        'add_hint': 'Quelque chose à ajouter ? Décrivez-le en une ligne.',
        'add_title_label': 'Le risque',
        'add_family': "C'est",
        'add_crit': 'Cela touche',
        'mine': 'Ajouté par vous',
        'more_risks': 'Autres risques à ajouter ({n})',
        'more_hint': 'Ceux-ci concernent moins souvent. Cochez ceux qui vous conviennent.',
        'risks_count': '{k} risques gardés sur {n}',
        'none_kept': 'Gardez au moins un risque pour continuer.',
        'now_title': 'Maintenant et après',
        'now_lead': 'Notez chaque risque, puis cochez ce que vous faites déjà et ce que vous ajouteriez.',
        'now_risks_h': 'Vos risques',
        'now_meas_h': 'Ce qui aide toute votre activité',
        'now_meas_lead': "Répondez une fois par mesure. Elle compte pour tous les risques qu'elle aide.",
        'sev_q': 'Quelle importance cela aurait-il pour vous ?',
        'now_empty': "Choisissez d'abord vos risques, puis revenez ici.",
        'now_empty_cta': 'Choisir vos risques',
        'sev_keep': 'Garder notre proposition',
        'sev_reason': 'Pourquoi un autre niveau ?',
        'sev_reason_ph': 'Nécessaire si vous choisissez un autre niveau',
        'err_sev_reason': 'Dites-nous pourquoi vous avez choisi un autre niveau.',
        'lik_deliberate': "Quelle est la probabilité que quelqu'un tente cela dans l'année à venir ?",
        'lik_accidental': 'Cela vous est-il arrivé au cours des 3 dernières années ?',
        'lik_skip': "Passer pour l'instant",
        'lik_unlikely': 'Peu probable',
        'lik_possible': 'Possible',
        'lik_likely': 'Probable',
        'lik_very_likely': 'Très probable : cela arrive peut-être déjà',
        'lik_never': 'Non',
        'lik_once': 'Oui, une fois',
        'lik_sometimes': 'Oui, quelques fois',
        'lik_often': 'Oui, régulièrement',
        'measures': 'Ce qui aide',
        'm_none': 'Plus tard',
        'm_in': 'Déjà en place',
        'm_extra': 'À ajouter à mon plan',
        'now_level': 'Maintenant',
        'after_level': 'Après vos mesures supplémentaires',
        'save_stay': 'Enregistrer',
        'save_next': 'Enregistrer et voir les résultats',
        'err_row': 'Vérifiez ce risque : {msg}',
        'res_title': 'Vos résultats',
        'see_all': 'Voir tous vos risques ({n})',
        'in_place_h': 'Déjà en place ({n})',
        'rough': "Ordre d'idée",
        'rough_text': 'durée et qui sont des estimations.',
        'map_key': 'Vos risques sur les cartes',
        'conf_cap': "jusqu'à {n} %",
        'assumed_h': 'Ce que nous avons supposé ({n})',
        'in_place': 'Déjà en place',
        'in_place_none': 'Cochez ce que vous faites déjà dans « Maintenant et après » : cela apparaît ici.',
        'risks_h': 'Vos risques',
        'map_now': 'Maintenant',
        'map_after': 'Après vos mesures supplémentaires',
        'risk_col': 'Risque',
        'now_col': 'Maintenant',
        'after_col': 'Après',
        'conf': 'Confiance',
        'band_low': 'faible',
        'band_medium': 'moyenne',
        'band_high': 'élevée',
        'top5': 'Vos actions prioritaires',
        'top5_empty': 'Cochez les mesures que vous ajouteriez dans « Maintenant et après » : vos actions apparaissent ici.',
        'assumptions': 'Ce que nous avons supposé',
        'assumptions_lead': 'Des endroits où nous avons utilisé une valeur typique. Vérifiez-les quand vous le pouvez.',
        'assumptions_none': 'Vous avez répondu à toutes les questions.',
        'assumptions_kept': 'Valeurs typiques que vous avez gardées (afficher)',
        'kind_default': 'Laissé ouvert',
        'kind_dont_know': 'Pas sûr',
        'kind_catalogue': 'Valeur typique conservée',
        'export': 'Télécharger Excel',
        'xlsx_missing': "Ajoutez le paquet openpyxl pour activer le téléchargement Excel. Le fichier d'étude se télécharge dès maintenant.",
        'export_json': "Télécharger le fichier d'étude",
        'expert': 'Ouvrir en vue expert',
        'edited': "Cette étude a été modifiée en mode expert. Enregistrer cet écran reconstruit l'étude à partir de vos réponses rapides et remplace ces modifications (la version précédente est gardée dans un fichier .bak).",
        'edit_answers': 'Modifier mes réponses',
        'honesty': "Déclaration d'honnêteté",
        'gap_lbl': 'À renforcer',
        'evid_lbl': "D'après",
        'fix_lbl': 'Prochaine étape',
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
    # a constant text in an element, not in an attribute: only & < > need escaping, so the apostrophe stays readable
    text = html_mod.escape(engine.HONESTY.get(lang) or engine.HONESTY["en"], quote=False)
    return (f'<aside class="honesty" aria-labelledby="honesty-h"><h2 id="honesty-h">{esc(tr(lang, "honesty"))}</h2>'
            f'<p lang="{esc(lang)}">{text}</p></aside>')


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


def _edited_banner(lang, edited):
    return f'<p class="notice" role="note">{esc(tr(lang, "edited"))}</p>' if edited else ""


def _err(msg):
    return f'<span class="field-error" role="alert">{esc(msg)}</span>' if msg else ""


# ------------------------------------------------------------------ home

def home(session, lang, recent, flash=""):
    """recent: [(sid, name, mtime, step)] quick studies, newest first."""
    if recent:
        rows = "".join(
            f'<li><a href="/quick/{sid}/{step}?lang={lang}"><span class="r-name">{esc(name)}</span>'
            f'<span class="r-when">{esc(when(mt))}</span></a></li>' for sid, name, mt, step in recent)
        cont = f'<ul class="recent">{rows}</ul>'
    else:
        cont = f'<p class="empty-state">{esc(tr(lang, "continue_none"))}</p>'
    built = (f'<p class="built-on">{esc(tr(lang, "built_on"))}. '
             f'<a href="/how?lang={lang}">{esc(tr(lang, "built_on_link"))}</a></p>')
    body = f"""<section class="hero"><h1>{esc(tr(lang, "home_title"))}</h1>{built}<p class="lead">{esc(tr(lang, "home_lead"))}</p>
<p><a class="button primary big" href="/quick/new?lang={lang}">{esc(tr(lang, "start"))} <span aria-hidden="true">&rarr;</span></a></p></section>
{honesty_box(lang)}
<section class="continue"><h2>{esc(tr(lang, "continue"))}</h2>{cont}
<p><a href="/studies">{esc(tr(lang, "all_studies"))}</a></p></section>"""
    return page(tr(lang, "home_page_title"), body, session, flash=flash, lang=lang, lang_path="/")


# ------------------------------------------------------------------ screen 1: about you

def about(session, sid, lang, cat, state, errors=None, edited=False, flash=""):
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
    action = f"/quick/{sid}/about" if sid else "/quick/new"
    body = f"""{stepper(sid, "about", lang, reachable=bool(sid))}
<h1>{esc(tr(lang, "about_title"))}</h1><p class="lead">{esc(tr(lang, "about_lead"))}</p>
{_flash(lang, flash)}{_edited_banner(lang, edited)}
<form method="post" action="{action}" class="flow">{csrf_input(session)}
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
<fieldset class="q"><legend><span class="q-t">{esc(tr(lang, "q_downtime"))}</span><span class="example">{esc(tr(lang, "q_downtime_ex"))}</span></legend>
<div class="choice-grid">{radios("downtime", engine.DOWNTIME_KEYS, "downtime_", cur_down)}</div></fieldset>
<fieldset class="q"><legend><span class="q-t">{esc(tr(lang, "q_sensitivity"))}</span><span class="example">{esc(tr(lang, "q_sensitivity_ex"))}</span></legend>
<div class="choice-grid">{radios("sensitivity", engine.SENSITIVITY_KEYS, "sens_", cur_sens)}</div></fieldset>
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


def risks(session, sid, lang, cat, quick, state=None, errors=None, edited=False, flash="", shortlist=None):
    """state: {"keep": {id: bool}, "reasons": {id: text}, "new": [{"title","family","criteria"}]} when a form was refused.
    `shortlist`: the engine's short list for the profile. Its risks, the kept ones and the person's own are shown
    in the main list; every other applicable risk goes under the collapsed "More risks you can add" section."""
    errors = errors or {}
    state = state or {}
    by_id = {r["id"]: r for r in cat["risks"]}
    keep_state = state.get("keep") or {}
    origins = {o["id"]: o for o in cat["origins"]}
    objectives = {o["id"]: o for o in cat["objectives"]}
    groups = {"deliberate": [], "accidental": []}
    more = {"deliberate": [], "accidental": []}
    n_kept = n_main = 0
    short = set(shortlist) if shortlist is not None else None
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
        card = _risk_card(lang, rdef, kept, reason, errors, mine=bool(custom))
        if short is None or custom or kept or e["id"] in short or errors.get(e["id"]):
            groups[rdef["family"]].append(card)
            n_main += 1
        else:
            more[rdef["family"]].append(card)
        n_kept += 1 if kept else 0
    sections = ""
    for fam in ("deliberate", "accidental"):
        if groups[fam]:
            sections += (f'<section class="family"><h2>{esc(tr(lang, "fam_" + fam))}</h2><p class="hint">{esc(tr(lang, "fam_" + fam + "_text"))}</p>'
                         f'{"".join(groups[fam])}</section>')
    n_more = sum(len(v) for v in more.values())
    if n_more:
        inner = "".join(f'<h3>{esc(tr(lang, "fam_" + fam))}</h3>{"".join(more[fam])}' for fam in ("deliberate", "accidental") if more[fam])
        sections += (f'<details class="q more-risks"><summary><span class="q-t">{esc(tr(lang, "more_risks", n=n_more))}</span></summary>'
                     f'<p class="example">{esc(tr(lang, "more_hint"))}</p>{inner}</details>')
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
    count = tr(lang, "risks_count", k=n_kept, n=n_main)
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

def _level_chip(cal, name, cls, lang="en"):
    return f'<span class="lvl {cls.get(name, "")}">{esc(labels.level_label(cal, name, lang))}</span>'


def numbers(rows):
    """{risk id: 1..n}: the plain numbers shown for the risks on the pages and the maps (codes stay in Expert mode and Excel)."""
    return {r["id"]: i for i, r in enumerate(rows, 1)}


def _risk_row(lang, cal, cls, r, n, e, state, errors):
    rid, d = r["id"], r["def"]
    sev_value = (state.get("sev") or {}).get(rid, (e.get("severity") or {}).get("value"))
    sev_reason = (state.get("sevreason") or {}).get(rid, (e.get("severity") or {}).get("reason") or "")
    lik_value = (state.get("lik") or {}).get(rid, (e.get("likelihood") or {}).get("answer") or "")
    words = labels.SEVERITY_WORDS[lang]
    proposed = r["severity_proposed"]
    sev_opts = f'<option value="">{esc(tr(lang, "sev_keep"))} ({esc(words[proposed].split(":")[0])})</option>' + "".join(
        f'<option value="{k}"{" selected" if sev_value == k or str(sev_value) == str(k) else ""}>{esc(words[k])}</option>'
        for k in (1, 2, 3, 4) if k != proposed)
    fam = d["family"]
    lik_opts = f'<option value="">{esc(tr(lang, "lik_skip"))}</option>' + "".join(
        f'<option value="{k}"{" selected" if lik_value == k else ""}>{esc(tr(lang, "lik_" + k))}</option>' for k in engine.LIKELIHOOD_KEYS[fam]) + (
        f'<option value="dont_know"{" selected" if lik_value == "dont_know" else ""}>{esc(tr(lang, "dk"))}</option>')
    sev_err = errors.get(rid)
    return f"""<article class="risk-row{" has-error" if sev_err else ""}" id="risk-{esc(rid)}">
<h3><span class="rid">{n}</span> {esc(_pick(d["title"], lang))}</h3>
<div class="rr"><div class="blk sev"><label for="sev-{esc(rid)}">{esc(tr(lang, "sev_q"))}</label>
<select id="sev-{esc(rid)}" name="sev_{esc(rid)}">{sev_opts}</select></div>
<div class="blk lik"><label for="lik-{esc(rid)}">{esc(tr(lang, "lik_" + fam))}</label>
<select id="lik-{esc(rid)}" name="lik_{esc(rid)}">{lik_opts}</select></div></div>
<div class="reason{" needed" if sev_err else ""}"><label for="sr-{esc(rid)}">{esc(tr(lang, "sev_reason"))}</label>
<input id="sr-{esc(rid)}" name="sevreason_{esc(rid)}" value="{esc(sev_reason)}" maxlength="500" placeholder="{esc(tr(lang, "sev_reason_ph"))}">{_err(sev_err)}</div>
<p class="result" aria-live="polite"><span>{esc(tr(lang, "now_level"))}: {_level_chip(cal, r["level"], cls, lang)}</span>
<span aria-hidden="true">&rarr;</span>
<span>{esc(tr(lang, "after_level"))}: {_level_chip(cal, r["level_target"], cls, lang)}</span></p></article>"""


def _measure_groups(lang, measures, current):
    """The measures of the kept risks, each once, under a few plain headings. `current`: {measure id: "in" | "extra" | ""}."""
    groups = {g: [] for g in labels.GROUPS}
    for m in measures:
        mid = m["id"]
        cur = current.get(mid, "")
        radios = "".join(
            f'<label class="seg-opt"><input type="radio" name="m_{esc(mid)}" value="{v}"{" checked" if cur == v else ""}>'
            f'<span>{esc(tr(lang, "m_" + (v or "none")))}</span></label>' for v in ("", "in", "extra"))
        groups[labels.group_of(mid)].append(
            f'<div class="meas-row" role="group" aria-labelledby="mt-{esc(mid)}"><p class="m-t" id="mt-{esc(mid)}">{esc(_pick(m, lang))}</p>'
            f'<div class="seg">{radios}</div></div>')
    return "".join(f'<fieldset class="blk meas"><legend><span class="q-t">{esc(labels.group_title(g, lang))}</span></legend>{"".join(groups[g])}</fieldset>'
                   for g in labels.GROUPS if groups[g])


def now(session, sid, lang, cat, quick, cal, rows, state=None, errors=None, edited=False, flash=""):
    """rows: engine.quick_compute rows (one per kept risk). state: {"sev": {id: v}, "sevreason": {id: t}, "lik": {id: v},
    "m": {measure id: "in" | "extra" | ""}} when a form was refused, to show what was typed.
    The measures are answered once for the whole business: each is listed once, whatever the number of risks."""
    errors = errors or {}
    state = state or {}
    cls = level_classes(cal)
    saved = {e["id"]: e for e in quick.get("risks") or []}
    if rows:
        org = engine.quick_org_measures(quick)
        current = {m: "in" for m in org["in_place"]}
        current.update({m: "extra" for m in org["extra"]})
        current.update(state.get("m") or {})
        risk_rows = "".join(_risk_row(lang, cal, cls, r, i, saved[r["id"]], state, errors) for i, r in enumerate(rows, 1))
        meas = _measure_groups(lang, engine.quick_measure_list(quick, cat), current)
        actions = (f'<div class="actions"><a class="button secondary" href="/quick/{sid}/risks">{esc(tr(lang, "back"))}</a>'
                   f'<button class="secondary big" name="go" value="stay">{esc(tr(lang, "save_stay"))}</button>'
                   f'<button class="primary big" name="go" value="next">{esc(tr(lang, "save_next"))} <span aria-hidden="true">&rarr;</span></button></div>')
        form = (f'<form method="post" action="/quick/{sid}/now" class="flow wide">{csrf_input(session)}<input type="hidden" name="lang" value="{esc(lang)}">'
                f'<section class="card"><h2>{esc(tr(lang, "now_risks_h"))}</h2>{risk_rows}</section>'
                f'<section class="card"><h2>{esc(tr(lang, "now_meas_h"))}</h2><p class="hint">{esc(tr(lang, "now_meas_lead"))}</p>{meas}</section>{actions}</form>')
    else:
        form = (f'<div class="empty-state"><p>{esc(tr(lang, "now_empty"))}</p>'
                f'<a class="button primary" href="/quick/{sid}/risks">{esc(tr(lang, "now_empty_cta"))}</a></div>')
    body = f"""{stepper(sid, "now", lang)}
<h1>{esc(tr(lang, "now_title"))}</h1><p class="lead">{esc(tr(lang, "now_lead"))}</p>
{_flash(lang, flash)}{_edited_banner(lang, edited)}{form}"""
    return page(tr(lang, "now_title"), body, session, cal_id=cal["id"], lang=lang, lang_path=f"/quick/{sid}/now")


# ------------------------------------------------------------------ screen 4: results

def results(session, sid, lang, cat, quick, cal, rows, reg_rows, facts, actions, assumptions, fnd, edited=False, can_xlsx=True):
    """Order: the closing summary, your top actions, the maps with their numbered risk list, "See all your risks"
    and "Already in place" (both collapsed), then confidence, the honesty statement, assumptions, downloads and the
    closing line again."""
    cls = level_classes(cal)
    conf, band = facts["confidence"], facts["band"]
    num = numbers(rows)
    # 1. the summary: one positive line
    closing = f'<p class="closing" role="status">{esc(fnd["closing"])}</p>' if fnd["closing"] else ""
    summary = f'<p class="summary" role="status">{esc(fnd["closing"])}</p>' if fnd["closing"] else ""

    # 2. your top actions: three short lines each, one "Rough guide" label above them
    def three(f):
        return (f'<p class="f-gap"><b>{esc(tr(lang, "gap_lbl"))}</b> {esc(f["gap"])}</p>'
                f'<p class="f-evid"><b>{esc(tr(lang, "evid_lbl"))}</b> {esc(f["evidence"])}</p>'
                f'<p class="f-fix"><b>{esc(tr(lang, "fix_lbl"))}</b> {esc(f["fix"])}</p>')
    if fnd["actions"]:
        acts = "".join(f'<li><span class="a-n">{i}</span><div class="finding">{three(f)}</div></li>'
                       for i, f in enumerate(fnd["actions"], 1))
        top = f'<ol class="actions-list">{acts}</ol>'
    else:
        top = f'<p class="empty-state">{esc(tr(lang, "top5_empty"))}</p>'

    # 3. the maps, with a short numbered list of the risks next to them
    if reg_rows:
        dcal = labels.display_cal(cal, lang)  # plain names on the maps; the numbers and colours are the engine's
        plain_rows = [dict(r, id=str(num.get(r["id"], r["id"]))) for r in reg_rows]
        key = "".join(f'<li value="{num[r["id"]]}">{esc(_pick(r["def"]["title"], lang))}</li>' for r in rows)
        maps = (f'<div class="maps-wrap"><div class="maps"><figure><figcaption id="map-now">{esc(tr(lang, "map_now"))}</figcaption>'
                f'{engine.risk_map(plain_rows, dcal, "now", tr(lang, "map_now"), plain=True, lang=lang, labelled_by="map-now")}</figure>'
                f'<figure><figcaption id="map-after">{esc(tr(lang, "map_after"))}</figcaption>'
                f'{engine.risk_map(plain_rows, dcal, "target", tr(lang, "map_after"), plain=True, lang=lang, labelled_by="map-after")}</figure></div>'
                f'<div class="map-key"><h3>{esc(tr(lang, "map_key"))}</h3><ol>{key}</ol></div></div>')
    else:
        maps = (f'<div class="empty-state"><p>{esc(tr(lang, "now_empty"))}</p>'
                f'<a class="button primary" href="/quick/{sid}/risks">{esc(tr(lang, "now_empty_cta"))}</a></div>')

    # 4. collapsed: all the risks, and what is already in place
    risk_items = "".join(
        f'<article class="risk-finding"><h3><span class="rid">{num[f["id"]]}</span> {esc(f["title"])} '
        f'{_level_chip(cal, r["level"], cls, lang)} <span aria-hidden="true">&rarr;</span> '
        f'{_level_chip(cal, r["level_target"], cls, lang)}</h3>{three(f)}</article>'
        for f, r in zip(fnd["risks"], rows))
    all_risks = (f'<details class="see-all"><summary>{esc(tr(lang, "see_all", n=len(rows)))}</summary>{risk_items}</details>'
                 if risk_items else "")
    placed = [labels.short_action(m["id"], lang) or _pick(m, lang) for m in engine.quick_measure_list(quick, cat)
              if m["id"] in engine.quick_org_measures(quick)["in_place"]]
    in_place = (f'<details class="in-place-box"><summary>{esc(tr(lang, "in_place_h", n=len(placed)))}</summary>'
                + (f'<ul class="in-place">{"".join(f"<li>{esc(t)}</li>" for t in placed)}</ul>' if placed else
                   f'<p class="empty-state">{esc(tr(lang, "in_place_none"))}</p>') + '</details>')

    # 5. below: confidence (one plain line), honesty, assumptions, downloads
    kinds = {"default": "kind_default", "dont_know": "kind_dont_know", "catalogue": "kind_catalogue"}
    main_ass = [a for a in assumptions if a["kind"] != "catalogue"]
    cat_ass = [a for a in assumptions if a["kind"] == "catalogue"]

    def li(a):
        return f'<li><span class="badge k-{esc(a["kind"])}">{esc(tr(lang, kinds[a["kind"]]))}</span> {esc(_pick(a["text"], lang))}</li>'
    ass_inner = (f'<p class="hint">{esc(tr(lang, "assumptions_lead"))}</p>'
                 + (f'<ul class="assumptions">{"".join(li(a) for a in main_ass)}</ul>' if main_ass else f'<p class="ok">{esc(tr(lang, "assumptions_none"))}</p>')
                 + (f'<ul class="assumptions">{"".join(li(a) for a in cat_ass)}</ul>' if cat_ass else ""))
    ass = f'<details class="assumed"><summary>{esc(tr(lang, "assumed_h", n=len(assumptions)))}</summary>{ass_inner}</details>'
    ceiling = facts.get("ceiling", 100)
    cap = f' <span class="cap">{esc(tr(lang, "conf_cap", n=ceiling))}</span>' if ceiling < 100 else ""
    export = (f'<a class="button primary" href="/s/{sid}/export.xlsx">{esc(tr(lang, "export"))}</a>' if can_xlsx else
              f'<p class="notice" role="note">{esc(tr(lang, "xlsx_missing"))}</p>')
    expert = (f'<a class="button secondary" href="/s/{sid}" rel="nofollow">{esc(tr(lang, "expert"))}</a>'
              if getattr(session, "expert", False) else "")
    rough = html_mod.escape(tr(lang, "rough"), quote=False)       # a label in an element: the apostrophe of "Ordre d'idée" stays readable
    body = f"""{stepper(sid, "results", lang)}
<h1>{esc(tr(lang, "res_title"))}</h1>
{_edited_banner(lang, edited)}{summary}
<section class="card"><h2>{esc(tr(lang, "top5"))}</h2><p class="rough"><b>{rough}</b> {esc(tr(lang, "rough_text"))}</p>{top}</section>
<section class="card maps-card">{maps}</section>
{all_risks}
{in_place}
<section class="card conf"><div class="conf-n"><span class="big-n">{conf}%</span><span class="band b-{esc(band)}">{esc(tr(lang, "band_" + band))}</span>{cap}</div>
<div><h2>{esc(tr(lang, "conf"))}</h2><progress max="100" value="{conf}" aria-label="{esc(tr(lang, "conf"))}">{conf}%</progress>
<p>{esc(engine.CONFIDENCE_LINE[lang])}</p></div></section>
{honesty_box(lang)}
{ass}
<section class="card next-steps"><div class="btns">{export}
<a class="button secondary" href="/s/{sid}/export.json">{esc(tr(lang, "export_json"))}</a>
<a class="button secondary" href="/quick/{sid}/about">{esc(tr(lang, "edit_answers"))}</a>{expert}</div></section>
{closing}"""
    return page(tr(lang, "res_title"), body, session, cal_id=cal["id"], lang=lang, lang_path=f"/quick/{sid}/results")
