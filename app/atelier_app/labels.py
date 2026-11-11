"""What people see: plain words for severities and risk levels, and a rough "how long, who" line for each action.

The engine and the calibration files keep the ANSSI wording (G1-G4 "Mineure ... Critique", Faible / Moyen / Élevé).
The mapping to plain words lives here, in the app, and changes no number: the same severity and the same level are
shown under another name. `display_cal` returns a copy of a calibration with these names, for the maps, the Excel
export and the pages; the original is never modified.

The calibration `anssi-v1.5` has three risk levels, so three plain level names exist (there is no fourth level to
name, and none is invented).
"""
import copy

# Severity (gravité), 1 to 4. The short label, then a one-line description.
SEVERITY_LABEL = {
    "en": {1: "Minor", 2: "Noticeable", 3: "Serious", 4: "Very serious"},
    "fr": {1: "Mineur", 2: "Notable", 3: "Sérieux", 4: "Très sérieux"},
}
SEVERITY_WORDS = {
    "en": {1: "Minor: a nuisance", 2: "Noticeable: it weighs on you for a few days",
           3: "Serious: lasting damage or a high cost", 4: "Very serious: the organisation would struggle to carry on"},
    "fr": {1: "Mineur : une gêne", 2: "Notable : cela pèse pendant quelques jours",
           3: "Sérieux : dégâts durables ou coût élevé", 4: "Très sérieux : l'organisation aurait du mal à continuer"},
}
# Likelihood (vraisemblance), 1 to 4: the same words as the quick-path question, so the maps and the question agree.
LIKELIHOOD_LABEL = {
    "en": {1: "Unlikely", 2: "Possible", 3: "Likely", 4: "Very likely"},
    "fr": {1: "Peu probable", 2: "Possible", 3: "Probable", 4: "Très probable"},
}
# Risk levels of the calibration, keyed by the calibration's English level name (`name_en`).
LEVEL_LABEL = {
    "en": {"Low": "Low", "Medium": "Moderate", "High": "High"},
    "fr": {"Low": "Faible", "Medium": "Modéré", "High": "Élevé"},
}
# What each level means, in plain words (the method's acceptability class, without the alarm).
LEVEL_ACCEPTABILITY = {
    "en": {"Low": "Acceptable as it is", "Medium": "Tolerable under control", "High": "To be reduced in the short term"},
    "fr": {"Low": "Acceptable en l'état", "Medium": "Tolérable sous contrôle", "High": "À réduire à court terme"},
}
LEVEL_ACTION = {
    "en": {"Low": "Keep it as it is",
           "Medium": "Follow the risk, and put actions in place as part of continuous improvement over the medium and long term",
           "High": "Put risk-reduction measures in place in the short term"},
    "fr": {"Low": "À garder en l'état",
           "Medium": "Suivre le risque et mettre des actions en place dans une démarche d'amélioration continue à moyen et long terme",
           "High": "Mettre en place des mesures de réduction du risque à court terme"},
}


def _lang(lang):
    return lang if lang in ("en", "fr") else "en"


def level_label(cal, name, lang):
    """Plain name of a level (`name` is the calibration's own key, as the engine returns it)."""
    for lv in cal["levels"]:
        if lv["name"] == name:
            key = lv.get("name_en") or name
            return LEVEL_LABEL[_lang(lang)].get(key) or (lv.get("name_en") if _lang(lang) == "en" else name) or name
    return name


def display_cal(cal, lang):
    """A copy of `cal` with plain names: severity labels, level names (also in the grid), acceptability and action
    texts. The numbers, the grid cells and the colours are unchanged."""
    lang = _lang(lang)
    out = copy.deepcopy(cal)
    rename = {}
    for lv in out["levels"]:
        key = lv.get("name_en") or lv["name"]
        plain = LEVEL_LABEL[lang].get(key)
        if plain:
            rename[lv["name"]] = plain
            lv["name"] = plain
            lv["name_en"] = LEVEL_LABEL["en"].get(key, lv.get("name_en"))
            lv["acceptability"] = LEVEL_ACCEPTABILITY[lang][key]
            lv["acceptability_en"] = LEVEL_ACCEPTABILITY["en"][key]
            lv["action"] = LEVEL_ACTION[lang][key]
            lv["action_en"] = LEVEL_ACTION["en"][key]
    out["grid_by_severity"] = {s: [rename.get(c, c) for c in row] for s, row in out["grid_by_severity"].items()}
    for x in out["severity"]:
        if x["n"] in SEVERITY_LABEL[lang]:
            x["label"] = SEVERITY_LABEL["fr"][x["n"]]
            x["label_en"] = SEVERITY_LABEL["en"][x["n"]]
    for x in out["likelihood"]:
        if x["n"] in LIKELIHOOD_LABEL[lang]:
            x["label"] = LIKELIHOOD_LABEL["fr"][x["n"]]
            x["label_en"] = LIKELIHOOD_LABEL["en"][x["n"]]
    return out


# ---- one short name, a rough "how long or how much" and "who can do it" for each measure of the catalogue ----
# These are rough guides written for Atelier, not measured figures and not from a standard. Only figures that suit any
# small business are used (FIGURES below: ranges and plain words, no precise price). A test checks that every
# measure of the catalogue has an entry, that every figure is one of FIGURES and that every line built from them
# stays within 15 words.
FIGURES = (("under an hour", "moins d'une heure"), ("an hour or two", "une heure ou deux"), ("a few hours", "quelques heures"),
           ("half a day", "une demi-journée"), ("a day or two", "un jour ou deux"), ("a few minutes", "quelques minutes"),
           ("a short call", "un court appel"), ("free", "gratuit"), ("small monthly fee", "petit abonnement mensuel"),
           ("small one-off cost", "petit achat unique"))
WHO = {
    "you": ("you", "vous"),
    "it": ("your IT contact", "votre contact informatique"),
    "manager": ("a manager", "un responsable"),
    "team": ("everyone", "toute l'équipe"),
    "pay": ("whoever pays invoices", "qui règle les factures"),
    "web": ("your website person", "votre responsable du site"),
    "premises": ("whoever manages premises", "qui gère les locaux"),
    "insurer": ("you and your insurer", "vous et votre assureur"),
}
# measure id: (short name EN, short name FR, how long or how much EN, FR, who)
EFFORT = {
    "backup_offline": ("Keep tested backups offline or elsewhere", "Garder des sauvegardes testées hors ligne", "half a day", "une demi-journée", "it"),
    "updates": ("Install updates quickly", "Installer vite les mises à jour", "under an hour", "moins d'une heure", "it"),
    "mfa": ("Turn on a second sign-in step", "Activer une seconde étape de connexion", "under an hour", "moins d'une heure", "it"),
    "awareness": ("Show people what fake messages look like", "Montrer à quoi ressemblent les faux messages", "under an hour", "moins d'une heure", "manager"),
    "protection": ("Run protection software on every computer", "Installer un logiciel de protection partout", "under an hour", "moins d'une heure", "it"),
    "incident_plan": ("Write a one-page incident plan", "Écrire un plan d'incident d'une page", "an hour or two", "une heure ou deux", "manager"),
    "password_manager": ("Use a password manager", "Utiliser un gestionnaire de mots de passe", "under an hour", "moins d'une heure", "it"),
    "monitoring": ("Switch on sign-in alerts", "Activer les alertes de connexion", "under an hour", "moins d'une heure", "it"),
    "payment_check": ("Confirm payment changes by phone", "Confirmer les changements par téléphone", "a few minutes", "quelques minutes", "pay"),
    "least_access": ("Give people only the access they need", "Donner à chacun seulement les accès utiles", "a few hours", "quelques heures", "it"),
    "data_minimise": ("Keep only the personal data you need", "Garder seulement les données personnelles utiles", "a few hours", "quelques heures", "manager"),
    "payment_provider": ("Let a certified provider take card payments", "Confier les cartes à un prestataire certifié", "a day or two", "un jour ou deux", "web"),
    "site_updates": ("Keep the website software up to date", "Tenir à jour le logiciel du site", "under an hour", "moins d'une heure", "web"),
    "site_checks": ("Watch the website and test checkout", "Surveiller le site et tester le paiement", "under an hour", "moins d'une heure", "web"),
    "admin_accounts": ("Keep few administrator accounts", "Limiter les comptes administrateur", "an hour or two", "une heure ou deux", "it"),
    "backup_auto": ("Automate backups and check them weekly", "Automatiser les sauvegardes et les vérifier", "an hour or two", "une heure ou deux", "it"),
    "traffic_filter": ("Add a traffic-filtering service", "Filtrer le trafic du site", "small monthly fee", "petit abonnement mensuel", "web"),
    "contract_outage": ("Agree restore times with providers", "Convenir de délais de rétablissement", "a short call", "un court appel", "manager"),
    "data_rules": ("Set clear rules on sharing data", "Fixer des règles de partage des données", "an hour or two", "une heure ou deux", "manager"),
    "encrypt_devices": ("Encrypt laptops and phones", "Chiffrer ordinateurs portables et téléphones", "an hour or two", "une heure ou deux", "it"),
    "offboarding": ("Remove access on the day someone leaves", "Retirer les accès le jour d'un départ", "a few minutes", "quelques minutes", "manager"),
    "segmentation": ("Put key systems on a separate network", "Séparer les systèmes clés du reste", "a day or two", "un jour ou deux", "it"),
    "share_review": ("Review online sharing settings", "Revoir les réglages de partage en ligne", "under an hour", "moins d'une heure", "it"),
    "own_copy": ("Keep your own copy of online data", "Garder votre copie des données en ligne", "an hour or two", "une heure ou deux", "it"),
    "remote_access": ("Protect remote access", "Protéger l'accès à distance", "a few hours", "quelques heures", "it"),
    "vendor_access": ("Give suppliers named accounts", "Donner un accès nominatif aux fournisseurs", "an hour or two", "une heure ou deux", "it"),
    "exit_plan": ("Note your alternatives to each supplier", "Noter vos solutions de remplacement", "a few hours", "quelques heures", "manager"),
    "ics_isolation": ("Keep machine controls off the office network", "Séparer les machines du réseau de bureau", "a day or two", "un jour ou deux", "it"),
    "manual_fallback": ("Practise key tasks by hand", "Prévoir les tâches clés à la main", "a few hours", "quelques heures", "manager"),
    "usb_scan": ("Scan USB sticks before use", "Analyser les clés USB avant usage", "under an hour", "moins d'une heure", "it"),
    "restore_test": ("Test a full restore", "Tester une restauration complète", "half a day", "une demi-journée", "it"),
    "key_tasks": ("Write down key tasks, train a deputy", "Écrire les tâches clés, former un suppléant", "a few hours", "quelques heures", "manager"),
    "recipient_check": ("Check the recipient before sending", "Vérifier le destinataire avant l'envoi", "a few minutes", "quelques minutes", "team"),
    "change_control": ("Test changes first, keep a way back", "Tester d'abord, garder un retour arrière", "an hour or two", "une heure ou deux", "it"),
    "spares": ("Keep a spare for key equipment", "Prévoir un équipement de remplacement", "small one-off cost", "petit achat unique", "manager"),
    "battery": ("Add a battery backup", "Ajouter une alimentation de secours", "small one-off cost", "petit achat unique", "it"),
    "dual_link": ("Add a backup internet connection", "Ajouter une connexion internet de secours", "small monthly fee", "petit abonnement mensuel", "it"),
    "device_wipe": ("Enable remote lock and erase", "Activer le verrouillage à distance", "under an hour", "moins d'une heure", "it"),
    "physical": ("Lock rooms and escort visitors", "Fermer les locaux, accompagner les visiteurs", "a few hours", "quelques heures", "premises"),
    "insurance": ("Check what your insurance covers", "Vérifier ce que couvre votre assurance", "a short call", "un court appel", "insurer"),
    "fire_safety": ("Add fire detection and an outside copy", "Détection incendie et copie externe", "small one-off cost", "petit achat unique", "premises"),
    "alt_site": ("Plan to work from another place", "Prévoir de travailler ailleurs", "a few hours", "quelques heures", "manager"),
    "surge_flood": ("Keep equipment off floors and pipes", "Surélever le matériel, loin des canalisations", "under an hour", "moins d'une heure", "premises"),
}


def short_action(measure_id, lang):
    e = EFFORT.get(measure_id)
    return e[0 if _lang(lang) == "en" else 1] if e else ""


def effort_line(measure_id, lang):
    """"about an hour, your IT contact" in the page language, or "" for a measure without an entry."""
    e = EFFORT.get(measure_id)
    if not e:
        return ""
    i = 0 if _lang(lang) == "en" else 1
    return f"{e[2 + i]}, {WHO[e[4]][i]}"



# ---- measures grouped under a few plain headings on "Now and after" ----
GROUPS = ("access", "devices", "recovery", "people", "outside")
GROUP_TITLE = {
    "en": {"access": "Sign-ins and access", "devices": "Computers and network", "recovery": "Backups and getting back to work",
           "people": "People and habits", "outside": "Website, suppliers and premises"},
    "fr": {"access": "Connexions et accès", "devices": "Ordinateurs et réseau", "recovery": "Sauvegardes et reprise du travail",
           "people": "Équipe et habitudes", "outside": "Site web, fournisseurs et locaux"},
}
MEASURE_GROUP = {
    "mfa": "access", "password_manager": "access", "least_access": "access", "admin_accounts": "access", "offboarding": "access",
    "remote_access": "access", "vendor_access": "access", "share_review": "access", "monitoring": "access",
    "updates": "devices", "protection": "devices", "encrypt_devices": "devices", "device_wipe": "devices", "usb_scan": "devices",
    "segmentation": "devices", "ics_isolation": "devices", "change_control": "devices", "traffic_filter": "devices",
    "backup_offline": "recovery", "backup_auto": "recovery", "restore_test": "recovery", "own_copy": "recovery",
    "incident_plan": "recovery", "manual_fallback": "recovery", "alt_site": "recovery", "spares": "recovery",
    "battery": "recovery", "dual_link": "recovery",
    "awareness": "people", "payment_check": "people", "recipient_check": "people", "data_minimise": "people",
    "data_rules": "people", "key_tasks": "people",
    "payment_provider": "outside", "site_updates": "outside", "site_checks": "outside", "contract_outage": "outside",
    "exit_plan": "outside", "physical": "outside", "fire_safety": "outside", "surge_flood": "outside", "insurance": "outside",
}


def group_of(measure_id):
    return MEASURE_GROUP.get(measure_id, "people")


def group_title(key, lang):
    return GROUP_TITLE[_lang(lang)][key]
