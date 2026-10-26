"""English and Swahili text produced by the server (ACC-08, NFR-10).

Why a plain dictionary and not Django's gettext: gettext needs compiled `.mo` files and the GNU
gettext tools, which are not available everywhere (for example on a phone running Termux). A dictionary
needs nothing, is easy to review, and can be sent to the front end as JSON (`GET /api/i18n/sw/`).

`t(key, lang, **params)` falls back to English, and to the key itself, so a missing translation can
never crash a request. Swahili wording should be checked by a Kiswahili teacher before go-live."""

LANGS = ("en", "sw")

SW_DAYS = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
SW_MONTHS = ["Januari", "Februari", "Machi", "Aprili", "Mei", "Juni", "Julai", "Agosti", "Septemba",
             "Oktoba", "Novemba", "Desemba"]
EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

MESSAGES = {
    "en": {
        # reminders and notices (NOT-01)
        "exam.1d.title": "{subject} exam tomorrow",
        "exam.1d.body": "{title} starts {when}. Get ready and check your phone and data.",
        "exam.1h.title": "{subject} exam in less than an hour",
        "exam.1h.body": "{title} starts at {when}. Charge your phone and find a quiet place.",
        "exam.start.title": "{title} has started",
        "exam.start.body": "Open the app and press START when you are ready.",
        "results.title": "Results ready: {title}",
        "results.body": "Your result and review are ready. Open the app to see how you did.",
        "password.title": "Password changed",
        "password.reset": "An administrator reset your password. Choose a new one when you log in.",
        "password.changed": "Your password was changed. If this was not you, tell your teacher or the school office.",
        # exam day (EDAY-09, EDAY-10)
        "exam.done.ok": "Well done! Your exam is submitted.",
        "exam.done.timeover": "Time is over. Your answers were submitted automatically.",
        "exam.results_note": "Your results will be ready on {when}.",
        # XP ledger labels (SRS 5.1)
        "xp.submit": "Submitted an exam",
        "xp.early": "Finished before time ran out",
        "xp.score": "Score: {percent}%",
        "xp.improve": "Beat your previous score",
        "xp.perfect": "Perfect score!",
        "xp.review": "Reviewed your wrong answers",
        "xp.practice": "Completed a practice quiz",
        "xp.streak": "{n}-day streak",
        # celebrations and streak messages (SRS 5.2, 5.3)
        "level.up.title": "Level up! You are now {name}",
        "level.up.body": "You reached level {level}. Keep learning!",
        "badge.title": "New badge: {name} ({tier})",
        "badge.body": "{desc}",
        "streak.restart": "Start again today, you can do it!",
        "streak.keep": "Learn something today to keep your streak going.",
        # practice mode (SRS 5.5)
        "practice.disabled": "Practice is switched off for this subject.",
        "practice.not_enough": "There are not enough practice questions for this subject yet. Please try again later.",
        "practice.correct": "Correct! Well done.",
        "practice.partly": "Partly correct. Read the explanation.",
        "practice.wrong": "Not quite. Read the explanation and try the next one.",
        "practice.empty": "Please choose or write an answer first.",
        "practice.done": "Practice complete. Nice work!",
        # leaderboard (SRS 5.6)
        "leaderboard.off": "The leaderboard is switched off.",
        "leaderboard.hidden": "You are hidden from the leaderboard. You can change this in your profile.",
        "leaderboard.unranked": "Earn some XP this week to join the leaderboard.",
        # review
        "review.nothing": "You got everything right. There is nothing to review.",
        "review.done": "Well done for reviewing your wrong answers!",
    },
    "sw": {
        "exam.1d.title": "Mtihani wa {subject} kesho",
        "exam.1d.body": "{title} unaanza {when}. Jiandae, na hakikisha simu yako na kifurushi cha intaneti ni vizuri.",
        "exam.1h.title": "Mtihani wa {subject} unaanza ndani ya saa moja",
        "exam.1h.body": "{title} unaanza {when}. Chaji simu yako na utafute mahali tulivu.",
        "exam.start.title": "{title} umeanza",
        "exam.start.body": "Fungua programu na ubonyeze ANZA ukiwa tayari.",
        "results.title": "Matokeo tayari: {title}",
        "results.body": "Matokeo yako na mapitio yako yako tayari. Fungua programu uone ulivyofanya.",
        "password.title": "Nenosiri limebadilishwa",
        "password.reset": "Msimamizi amebadilisha nenosiri lako. Chagua jipya utakapoingia.",
        "password.changed": "Nenosiri lako limebadilishwa. Kama si wewe, mwambie mwalimu wako au ofisi ya shule.",
        "exam.done.ok": "Hongera! Mtihani wako umewasilishwa.",
        "exam.done.timeover": "Muda umekwisha. Majibu yako yamewasilishwa kiotomatiki.",
        "exam.results_note": "Matokeo yako yatakuwa tayari {when}.",
        "xp.submit": "Umewasilisha mtihani",
        "xp.early": "Umemaliza kabla ya muda kuisha",
        "xp.score": "Alama: {percent}%",
        "xp.improve": "Umepita alama yako ya awali",
        "xp.perfect": "Alama kamili!",
        "xp.review": "Umepitia majibu uliyokosea",
        "xp.practice": "Umemaliza zoezi la mazoezi",
        "xp.streak": "Mfululizo wa siku {n}",
        "level.up.title": "Umepanda ngazi! Sasa wewe ni {name}",
        "level.up.body": "Umefika ngazi ya {level}. Endelea kujifunza!",
        "badge.title": "Beji mpya: {name} ({tier})",
        "badge.body": "{desc}",
        "streak.restart": "Anza tena leo, unaweza!",
        "streak.keep": "Jifunze kitu leo ili mfululizo wako uendelee.",
        "practice.disabled": "Mazoezi yamezimwa kwa somo hili.",
        "practice.not_enough": "Bado hakuna maswali ya kutosha ya mazoezi kwa somo hili. Jaribu tena baadaye.",
        "practice.correct": "Sahihi! Hongera.",
        "practice.partly": "Sahihi kwa sehemu. Soma maelezo.",
        "practice.wrong": "Si sahihi kabisa. Soma maelezo kisha endelea na swali linalofuata.",
        "practice.empty": "Tafadhali chagua au andika jibu kwanza.",
        "practice.done": "Zoezi limekamilika. Kazi nzuri!",
        "leaderboard.off": "Ubao wa wanaoongoza umezimwa.",
        "leaderboard.hidden": "Umefichwa kwenye ubao wa wanaoongoza. Unaweza kubadilisha hili kwenye wasifu wako.",
        "leaderboard.unranked": "Pata XP kidogo wiki hii ili uingie kwenye ubao wa wanaoongoza.",
        "review.nothing": "Umejibu kila swali sawasawa. Hakuna cha kupitia.",
        "review.done": "Hongera kwa kupitia majibu uliyokosea!",
    },
}


def lang_of(user):
    """The language a user chose (English by default)."""
    lang = getattr(user, "language", "en")
    return lang if lang in LANGS else "en"


def t(key, lang="en", **params):
    """Translate `key` into `lang`, filling {placeholders}. Never raises."""
    table = MESSAGES.get(lang) or MESSAGES["en"]
    text = table.get(key) or MESSAGES["en"].get(key) or key
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text


def fmt_when(local_dt, lang="en"):
    """A date and time for a message. `local_dt` must already be in East Africa Time.
    English keeps the format Phase 2 used ('Mon 26 Oct, 09:00')."""
    if lang == "sw":
        return f"{SW_DAYS[local_dt.weekday()]} {local_dt.day} {SW_MONTHS[local_dt.month - 1]}, {local_dt:%H:%M}"
    return f"{EN_DAYS[local_dt.weekday()]} {local_dt.day:02d} {EN_MONTHS[local_dt.month - 1]}, {local_dt:%H:%M}"


def catalog_for(lang):
    """Everything the front end can ask for in one language: server messages plus the badge, tier and level names."""
    from gamification import catalog, rules  # imported here so this module stays free of other imports

    lang = lang if lang in LANGS else "en"
    return {
        "lang": lang,
        "messages": {**MESSAGES["en"], **MESSAGES[lang]},
        "badges": {b["code"]: {"name": catalog.badge_name(b["code"], lang), "description": catalog.badge_desc(b["code"], lang),
                               "unit": catalog.badge_unit(b["code"], lang)} for b in catalog.BADGES},
        "tiers": {k: catalog.tier_label(i, lang) for i, k in enumerate(("bronze", "silver", "gold"), start=1)},
        "levels": {lv["level"]: (lv["name_sw"] if lang == "sw" else lv["name"]) for lv in rules.DEFAULT_LEVELS},
    }
