"""Public mode pages: join, full, study limit, goodbye, and the "Open a saved file" form. English and French.

Wording: plain, kind, positive, few words. User text never reaches these pages (nothing here prints a field value).
"""
from .views import csrf_input, esc, page
from .views_quick import honesty_box

OPEN_MAX = 512 * 1024           # a saved study file, in bytes
T = {
    "en": {
        "join_title": "Welcome",
        "join_line": "Atelier helps you see your main risks in about 15 minutes.",
        "code": "Invite code",
        "start": "Start",
        "bad_code": "Check the invite code and try again.",
        "expired": "The form timed out. Try once more.",
        "wait": "Take a short break, then try again in a few minutes.",
        "full_title": "Almost there",
        "full": "We are full for now, please come back soon.",
        "limit_title": "Your studies",
        "limit": "You have 20 studies. Delete one to start a new one.",
        "limit_link": "Go to your studies",
        "bye_title": "Goodbye",
        "bye": "Your data is deleted. Thank you for trying Atelier.",
        "again": "Start again",
        "open_h": "Open a saved file",
        "open_hint": "Choose a study file you saved earlier with “Download the study file”.",
        "open_btn": "Open",
        "open_bad": "Choose a study file saved with “Download the study file”, then try again.",
        "open_big": "Choose a smaller file: 512 KB at most.",
        "open_title": "Open a saved file",
        "open_back": "Back to your studies",
    },
    "fr": {
        "join_title": "Bienvenue",
        "join_line": "Atelier vous aide à voir vos principaux risques en 15 minutes environ.",
        "code": "Code d'invitation",
        "start": "Commencer",
        "bad_code": "Vérifiez le code d'invitation et réessayez.",
        "expired": "Le formulaire a expiré. Réessayez.",
        "wait": "Faites une courte pause, puis réessayez dans quelques minutes.",
        "full_title": "Presque",
        "full": "Nous sommes complets pour le moment, revenez bientôt.",
        "limit_title": "Vos études",
        "limit": "Vous avez 20 études. Effacez-en une pour en commencer une nouvelle.",
        "limit_link": "Voir vos études",
        "bye_title": "Au revoir",
        "bye": "Vos données sont effacées. Merci d'avoir essayé Atelier.",
        "again": "Recommencer",
        "open_h": "Ouvrir un fichier enregistré",
        "open_hint": "Choisissez un fichier d'étude enregistré plus tôt avec « Télécharger le fichier d'étude ».",
        "open_btn": "Ouvrir",
        "open_bad": "Choisissez un fichier d'étude enregistré avec « Télécharger le fichier d'étude », puis réessayez.",
        "open_big": "Choisissez un fichier plus petit : 512 Ko au maximum.",
        "open_title": "Ouvrir un fichier enregistré",
        "open_back": "Retour à vos études",
    },
}


def t(lang, key):
    return T.get(lang, T["en"])[key]


def join_page(pre, lang, need_code, message_key="", src=""):
    """The one short screen a visitor sees first. `message_key` names a kind note shown above the form."""
    note = f'<p class="error" role="alert">{esc(t(lang, message_key))}</p>' if message_key else ""
    code = (f'<label>{esc(t(lang, "code"))} <input type="text" name="code" autocomplete="off" required '
            f'autocapitalize="off" spellcheck="false"></label>' if need_code else "")
    body = f"""<section class="card narrow join">
<h1>{esc(t(lang, "join_title"))}</h1>
<p class="lead">{esc(t(lang, "join_line"))}</p>
{honesty_box(lang)}
{note}
<form method="post" action="/join">
<input type="hidden" name="pre" value="{esc(pre)}">
<input type="hidden" name="src" value="{esc(src)}">
{code}
<button class="primary big">{esc(t(lang, "start"))}</button>
</form>
</section>"""
    return page(t(lang, "join_title"), body, None, lang=lang, lang_path="/join")


def simple_page(lang, title_key, text_key, link=None, session=None, lang_path=None):
    """A short kind page: a title, one sentence and one link (href, label key)."""
    more = f'<p><a class="button" href="{esc(link[0])}">{esc(t(lang, link[1]))}</a></p>' if link else ""
    body = f'<section class="card narrow"><h1>{esc(t(lang, title_key))}</h1><p>{esc(t(lang, text_key))}</p>{more}</section>'
    return page(t(lang, title_key), body, session, lang=lang, lang_path=lang_path)


def full_page(lang):
    return simple_page(lang, "full_title", "full", lang_path="/join")


def limit_page(lang, session):
    return simple_page(lang, "limit_title", "limit", ("/studies", "limit_link"), session)


def goodbye_page(lang):
    return simple_page(lang, "bye_title", "bye", ("/join", "again"))


def open_error_page(lang, key, session):
    return simple_page(lang, "open_title", key, ("/studies", "open_back"), session)


def open_form(session, lang):
    """The "Open a saved file" block of the studies page. It needs the small script in static/app.js (same origin);
    the form is hidden until the script runs, so a browser without it shows nothing that cannot work."""
    return f"""<section class="open-file" data-open-file hidden>
<h2>{esc(t(lang, "open_h"))}</h2>
<p class="hint">{esc(t(lang, "open_hint"))}</p>
<form method="post" action="/quick/open" data-bad="{esc(t(lang, "open_bad"))}" data-big="{esc(t(lang, "open_big"))}">
{csrf_input(session)}<input type="hidden" name="study" value="">
<input type="file" id="open-file-input" accept=".json,application/json" aria-label="{esc(t(lang, "open_h"))}">
<button type="submit">{esc(t(lang, "open_btn"))}</button>
<p class="error" role="alert" data-open-msg></p>
</form>
</section>"""
