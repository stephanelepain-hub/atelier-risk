"""Public mode: the "Send my study to CPLT" card on the results page and its answer pages, English and French.

Wording: plain, kind, positive, few words. Nothing a visitor typed is printed back on these pages.
"""
from .views import csrf_input, esc, page

MAX_MESSAGE = 500
T = {
    "en": {
        "card_h": "Want a deeper look?",
        "card_p": "Send your study to CPLT. We reply by email with a fuller strategy.",
        "service_intro": "Atelier is free, made by CPLT. CPLT builds AI for small businesses: you decide where your data goes, and a person approves every result. ",
        "service_link": "See how CPLT works",
        "service_url": "https://cplt.tech/proof",
        "email": "Your email address",
        "message": "A message (optional, up to 500 characters)",
        "consent": "I agree to send my answers, including the text I typed, to CPLT, who keeps them for 12 months to reply to me.",
        "send": "Send my study",
        "thanks_title": "Thank you",
        "thanks": "Your study is with CPLT. We reply by email to the address you gave, with a fuller strategy.",
        "thanks_keep": "CPLT keeps your study and your message for 12 months to reply to you. Delete my data leaves this copy in "
                       "place; write to {email} to remove it sooner.",
        "back": "Back to your results",
        "bad_consent": "Please tick the box to agree, then send again.",
        "bad_email": "Please check the email address, then send again.",
        "bad_message": "Please keep your message to 500 characters or fewer, then send again.",
        "err_title": "One more step",
        "limit_title": "See you tomorrow",
        "limit": "You have sent 3 studies today. Please come back tomorrow.",
        "full_title": "Almost there",
        "full": "We are full for now, please write to {email}.",
    },
    "fr": {
        "card_h": "Envie d'aller plus loin ?",
        "card_p": "Envoyez votre étude à CPLT. Nous répondons par e-mail avec une stratégie plus complète.",
        "service_intro": "Atelier est gratuit, proposé par CPLT. CPLT conçoit de l’IA pour les petites entreprises : vous décidez où vont vos données, et une personne valide chaque résultat. ",
        "service_link": "Voyez comment travaille CPLT",
        "service_url": "https://cplt.tech/fr",
        "email": "Votre adresse e-mail",
        "message": "Un message (facultatif, 500 caractères au plus)",
        "consent": "J'accepte d'envoyer mes réponses, y compris les textes saisis, à CPLT, qui les conserve 12 mois pour me répondre.",
        "send": "Envoyer mon étude",
        "thanks_title": "Merci",
        "thanks": "Votre étude est chez CPLT. Nous répondons par e-mail à l'adresse indiquée, avec une stratégie plus complète.",
        "thanks_keep": "CPLT conserve votre étude et votre message 12 mois pour vous répondre. Effacer mes données laisse cette "
                       "copie en place ; écrivez à {email} pour la faire retirer plus tôt.",
        "back": "Retour à vos résultats",
        "bad_consent": "Cochez la case pour accepter, puis envoyez à nouveau.",
        "bad_email": "Vérifiez l'adresse e-mail, puis envoyez à nouveau.",
        "bad_message": "Gardez votre message à 500 caractères au plus, puis envoyez à nouveau.",
        "err_title": "Encore une étape",
        "limit_title": "À demain",
        "limit": "Vous avez envoyé 3 études aujourd'hui. Revenez demain.",
        "full_title": "Presque",
        "full": "Nous sommes complets pour le moment, écrivez à {email}.",
    },
}


def t(lang, key):
    return T.get(lang, T["en"])[key]


def card(session, sid, lang):
    """The card at the end of the results page: a short offer and the form (consent box left unticked)."""
    return f"""<section class="card share-card">
<h2>{esc(t(lang, "card_h"))}</h2>
<p>{esc(t(lang, "card_p"))}</p>
<p>{esc(t(lang, "service_intro"))}<a href="{esc(t(lang, "service_url"))}">{esc(t(lang, "service_link"))}</a>.</p>
<form method="post" action="/quick/{esc(sid)}/share" class="share-form">
{csrf_input(session)}<input type="hidden" name="lang" value="{esc(lang)}">
<label>{esc(t(lang, "email"))} <input type="email" name="email" autocomplete="email" required maxlength="254"></label>
<label>{esc(t(lang, "message"))} <textarea name="message" rows="3" maxlength="{MAX_MESSAGE}"></textarea></label>
<label class="choice"><input type="checkbox" name="consent" value="1" required> <span>{esc(t(lang, "consent"))}</span></label>
<button class="primary">{esc(t(lang, "send"))}</button>
</form>
</section>"""


def _page(lang, session, sid, title_key, text, link=True):
    more = f'<p><a class="button" href="/quick/{esc(sid)}/results">{esc(t(lang, "back"))}</a></p>' if link else ""
    body = f'<section class="card narrow"><h1>{esc(t(lang, title_key))}</h1><p>{esc(text)}</p>{more}</section>'
    return page(t(lang, title_key), body, session, lang=lang)


def bad_page(lang, session, sid, key):
    return _page(lang, session, sid, "err_title", t(lang, key))


def limit_page(lang, session, sid):
    return _page(lang, session, sid, "limit_title", t(lang, "limit"))


def full_page(lang, session, sid, email):
    return _page(lang, session, sid, "full_title", t(lang, "full").format(email=email))


def thanks_page(lang, session, sid, email):
    body = (f'<section class="card narrow"><h1>{esc(t(lang, "thanks_title"))}</h1><p>{esc(t(lang, "thanks"))}</p>'
            f'<p>{esc(t(lang, "thanks_keep").format(email=email))}</p>'
            f'<p><a class="button" href="/quick/{esc(sid)}/results">{esc(t(lang, "back"))}</a></p></section>')
    return page(t(lang, "thanks_title"), body, session, lang=lang)
