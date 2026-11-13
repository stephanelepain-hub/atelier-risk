"""Public mode: the privacy and legal page (/privacy), English and French.

It describes exactly what the public instance does. Keep it true: change it in the same commit as any change to what
is stored, for how long, where, or who receives it. Wording rules as everywhere: plain, kind, positive, few words.
"""
from . import views
from .views import esc, page

T = {
    "en": {
        "title": "Your data",
        "intro": "Here is everything Atelier does with your data, in plain words.",
        "sections": [
            ("Who is responsible",
             "{publisher}{email_sentence} Legal notice: {legal}."),
            ("What we keep",
             "The answers you type, in a private space linked to one cookie in your browser. Atelier asks for no "
             "account and no name. An email address is asked only if you choose to send us your study (see below). In the text boxes, describe your work in general terms and "
             "leave out names and confidential details. We also keep anonymous counts, such as how many people open the "
             "start page and the kind of site they came from (LinkedIn, X, GitHub, a search engine), how many studies reach the "
             "results or which measures people choose. They have no identifier, no IP address and none of your text, and we keep "
             "them to improve Atelier (legal basis: GDPR article 6(1)(f))."),
            ("For how long",
             "Your private space is deleted 30 days after your last visit, or at once with Delete my data. "
             "Download the results or the study file to keep a copy. A study you send us is kept for 12 months (see below)."),
            ("Who can see your answers",
             "Through the app, only your browser opens your private space. Your answers go to no AI service, "
             "advertiser or other company: only our hosting provider stores them. The CPLT team reads a study only "
             "when you send it to us, and opens a private space only when you ask us for help with it."),
            ("If you send us your study",
             "When you choose Send your study to CPLT, we receive a copy of your answers, including the text you typed, "
             "your email address and your optional message. We use them to reply to you by email with a fuller "
             "strategy. We keep them for 12 months, then delete them. The legal basis is your consent (GDPR article "
             "6(1)(a)). You can withdraw it, or ask us to delete your copy, with one email to {email}. Delete my data "
             "leaves this copy in place, because you sent it on purpose."),
            ("Cookies",
             "Only the cookies the app needs to work: your private space, your language, Expert mode and a "
             "protection for the forms. Atelier uses no analytics, tracking or advertising cookies, so there is "
             "nothing to accept."),
            ("Server logs",
             "For security, the web server records the IP address, the page address, the time and the browser of "
             "each visit. These logs are kept for 15 days at most."),
            ("Where it runs",
             "On a server in the European Union (Lithuania), rented from Hostinger International Ltd."),
            ("Your rights",
             "You can ask to access, correct, delete or receive your data, or object to its use, with one email to "
             "{email}. Delete my data and the study file download give you the main ones at once. You can also "
             "contact the CNIL, the French data protection authority."),
            ("Legal basis",
             "We keep your answers to provide the service you ask for (GDPR article 6(1)(b)), and the server logs "
             "and the anonymous counts to keep the service safe and improve it (article 6(1)(f)). A study you send us "
             "rests on your consent (article 6(1)(a))."),
        ],
        "updated": "Last updated: {date}.",
    },
    "fr": {
        "title": "Vos données",
        "intro": "Voici tout ce qu'Atelier fait de vos données, en mots simples.",
        "sections": [
            ("Qui est responsable",
             "{publisher}{email_sentence} Mentions légales : {legal}."),
            ("Ce que nous gardons",
             "Les réponses que vous saisissez, dans un espace privé lié à un cookie de votre navigateur. Atelier "
             "fonctionne sans compte et sans nom. Une adresse e-mail est demandée uniquement si vous choisissez de nous envoyer votre étude (voir plus bas). Dans les zones de texte, décrivez votre "
             "activité en termes généraux, sans noms ni détails confidentiels. Nous gardons aussi des comptages anonymes, "
             "par exemple combien de personnes ouvrent la page d'accueil et le type de site d'où elles viennent (LinkedIn, X, "
             "GitHub, un moteur de recherche), combien d'études arrivent aux résultats ou quelles mesures les personnes choisissent. Ils "
             "sont anonymes, sans identifiant, sans adresse IP et sans aucun de vos textes, et nous les gardons pour améliorer Atelier "
             "(base légale : article 6(1)(f) du RGPD)."),
            ("Combien de temps",
             "Votre espace privé est effacé 30 jours après votre dernière visite, ou tout de suite avec Effacer mes "
             "données. Téléchargez les résultats ou le fichier d'étude pour en garder une copie. Une étude que vous nous "
             "envoyez est conservée 12 mois (voir plus bas)."),
            ("Qui voit vos réponses",
             "Dans l'application, seul votre navigateur ouvre votre espace privé. Aucun service d'IA, annonceur ou "
             "autre entreprise ne reçoit vos réponses : seul notre hébergeur les stocke. L'équipe CPLT lit une étude "
             "uniquement si vous nous l'envoyez, et ouvre un espace privé uniquement si vous lui demandez de l'aide à "
             "son sujet."),
            ("Si vous nous envoyez votre étude",
             "Quand vous choisissez Envoyer votre étude à CPLT, nous recevons une copie de vos réponses, y compris les "
             "textes saisis, votre adresse e-mail et votre message facultatif. Nous les utilisons pour vous répondre "
             "par e-mail avec une stratégie plus complète. Nous les conservons 12 mois, puis nous les supprimons. La "
             "base légale est votre consentement (article 6(1)(a) du RGPD). Vous pouvez le retirer, ou demander la "
             "suppression de votre copie, par un e-mail à {email}. Effacer mes données laisse cette copie en place, "
             "car vous l'avez envoyée volontairement."),
            ("Cookies",
             "Uniquement les cookies utiles au fonctionnement : votre espace privé, votre langue, le mode Expert et "
             "une protection des formulaires. Atelier se passe de cookies de mesure d'audience, de suivi ou de "
             "publicité : rien à accepter."),
            ("Journaux du serveur",
             "Pour la sécurité, le serveur web enregistre l'adresse IP, l'adresse de la page, l'heure et le "
             "navigateur de chaque visite. Ces journaux sont gardés 15 jours au plus."),
            ("Où cela tourne",
             "Sur un serveur dans l'Union européenne (Lituanie), loué à Hostinger International Ltd."),
            ("Vos droits",
             "Vous pouvez demander l'accès, la rectification, l'effacement ou la portabilité de vos données, ou vous "
             "opposer à leur usage, par un e-mail à {email}. Effacer mes données et le téléchargement du fichier "
             "d'étude vous en donnent l'essentiel tout de suite. Vous pouvez aussi saisir la CNIL."),
            ("Base légale",
             "Nous gardons vos réponses pour fournir le service que vous demandez (article 6(1)(b) du RGPD), et les "
             "journaux du serveur et les comptages anonymes pour garder le service sûr et l'améliorer (article "
             "6(1)(f)). Une étude que vous nous envoyez repose sur votre consentement (article 6(1)(a))."),
        ],
        "updated": "Dernière mise à jour : {date}.",
    },
}
UPDATED = {"en": "11 November 2026", "fr": "11 novembre 2026"}


def _link(url, text=None):
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text or url.split("://", 1)[1].rstrip("/"))}</a>'


def privacy(session, lang):
    t = T.get(lang, T["en"])
    pub = views.PUBLISHER or {}
    name = pub.get("name") or "the publisher of this site"
    email = pub.get("email")
    mail = f'<a href="mailto:{esc(email)}">{esc(email)}</a>' if email else esc(pub.get("url", ""))
    if lang == "fr":
        publisher = f"{esc(name)}, qui propose Atelier" + (f" ({_link(pub['url'])})." if pub.get("url") else ".")
        email_sentence = f" Écrivez-nous à {mail}." if email else ""
    else:
        publisher = f"{esc(name)}, who offers Atelier" + (f" ({_link(pub['url'])})." if pub.get("url") else ".")
        email_sentence = f" Write to us at {mail}." if email else ""
    legal = _link(pub["legal_url"]) if pub.get("legal_url") else esc(pub.get("url", ""))
    parts = [f'<section class="card"><h1>{esc(t["title"])}</h1><p>{esc(t["intro"])}</p></section>']
    for h, body in t["sections"]:
        text = esc(body).replace("{publisher}", publisher).replace("{email_sentence}", email_sentence)
        text = text.replace("{legal}", legal).replace("{email}", mail)
        parts.append(f'<section class="card"><h2>{esc(h)}</h2><p>{text}</p></section>')
    parts.append(f'<p class="muted">{esc(t["updated"].format(date=UPDATED.get(lang, UPDATED["en"])))}</p>')
    return page(t["title"], "\n".join(parts), session, lang=lang, lang_path="/privacy")
