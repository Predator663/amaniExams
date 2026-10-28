"""The badge catalogue (SRS 5.4). Pure data, English and Swahili.

Every badge has three tiers (bronze, silver, gold). The BRONZE target is the SRS rule itself
(for example "Complete 50 practice quizzes"); silver and gold are higher targets. Admins can change
the three targets of any badge in settings (ADM-09). `metric` names a number that
`services.compute_metrics` works out from the student's published results and activity.

Swahili wording should be checked by a Kiswahili teacher before go-live."""

TIER_LABELS = {
    "bronze": ("Bronze", "Shaba"),
    "silver": ("Silver", "Fedha"),
    "gold": ("Gold", "Dhahabu"),
}

BADGES = [
    {"code": "first_steps", "metric": "exams_completed", "tiers": [1, 5, 15],
     "name": ("First Steps", "Hatua za Kwanza"),
     "desc": ("Complete your first exam.", "Maliza mtihani wako wa kwanza."),
     "unit": ("exams", "mitihani")},
    {"code": "perfect_score", "metric": "perfect_scores", "tiers": [1, 3, 10],
     "name": ("Perfect Score", "Alama Kamili"),
     "desc": ("Score 100 percent in any exam.", "Pata asilimia 100 katika mtihani wowote."),
     "unit": ("perfect scores", "alama kamili")},
    {"code": "comeback_kid", "metric": "comebacks", "tiers": [1, 3, 6],
     "name": ("Comeback Kid", "Kurudi kwa Nguvu"),
     "desc": ("Improve by 15 percentage points or more compared with your previous exam in the same subject.",
              "Boresha alama zako kwa pointi 15 za asilimia au zaidi ukilinganisha na mtihani wako wa awali wa somo hilo hilo."),
     "unit": ("big improvements", "maboresho makubwa")},
    {"code": "on_fire", "metric": "best_streak", "tiers": [7, 14, 30],
     "name": ("On Fire", "Moto wa Kuwaka"),
     "tier_names": {3: ("Unstoppable", "Hazuiliki")},  # the gold tier is the 30-day "Unstoppable" badge
     "desc": ("Reach a 7-day learning streak. Reach 30 days to become Unstoppable.",
              "Fikia mfululizo wa siku 7 za kujifunza. Fikia siku 30 uwe Hazuiliki."),
     "unit": ("days in a row", "siku mfululizo")},
    {"code": "subject_star", "metric": "top_grades_by_subject", "tiers": [1, 3, 5], "per_subject": True,
     "name": ("Subject Star", "Nyota ya Somo"),
     "desc": ("Earn the top grade in an exam of that subject.", "Pata daraja la juu kabisa katika mtihani wa somo hilo."),
     "unit": ("top grades", "madaraja ya juu")},
    {"code": "all_rounder", "metric": "all_rounder_terms", "tiers": [1, 2, 4],
     "name": ("All-Rounder", "Hodari wa Yote"),
     "desc": ("Earn grade B or better in every subject in a term.",
              "Pata daraja B au bora zaidi katika kila somo ndani ya muhula."),
     "unit": ("terms", "mihula")},
    {"code": "steady_pace", "metric": "steady_exams", "tiers": [1, 5, 15],
     "name": ("Steady Pace", "Mwendo Thabiti"),
     "desc": ("Finish before time runs out with a score of 70 percent or more.",
              "Maliza kabla ya muda kuisha ukiwa na alama ya asilimia 70 au zaidi."),
     "unit": ("exams", "mitihani")},
    {"code": "mistake_master", "metric": "reviewed_exams", "tiers": [1, 5, 15],
     "name": ("Mistake Master", "Bingwa wa Kurekebisha"),
     "desc": ("Review every wrong answer after results.", "Pitia kila jibu ulilokosea baada ya matokeo kutoka."),
     "unit": ("exams reviewed", "mitihani iliyopitiwa")},
    {"code": "always_on_time", "metric": "early_starts", "tiers": [5, 15, 30],
     "name": ("Always On Time", "Daima kwa Wakati"),
     "desc": ("Start 5 exams within the first 5 minutes of the exam window.",
              "Anza mitihani 5 ndani ya dakika 5 za kwanza za dirisha la mtihani."),
     "unit": ("early starts", "kuanza mapema")},
    {"code": "practice_pro", "metric": "practice_quizzes", "tiers": [50, 100, 250],
     "name": ("Practice Pro", "Bingwa wa Mazoezi"),
     "desc": ("Complete 50 practice quizzes.", "Maliza maswali ya mazoezi 50."),
     "unit": ("practice quizzes", "mazoezi")},
]

BY_CODE = {b["code"]: b for b in BADGES}


def _pick(pair, lang):
    return pair[1] if lang == "sw" else pair[0]


def badge_name(code, lang="en", tier=None):
    """The badge's name. A tier can carry its own name (On Fire becomes Unstoppable at gold)."""
    b = BY_CODE[code]
    if tier and tier in b.get("tier_names", {}):
        return _pick(b["tier_names"][tier], lang)
    return _pick(b["name"], lang)


def badge_desc(code, lang="en"):
    return _pick(BY_CODE[code]["desc"], lang)


def badge_unit(code, lang="en"):
    return _pick(BY_CODE[code]["unit"], lang)


def tier_label(tier_index, lang="en"):
    """tier_index 1..3 -> 'Bronze' / 'Shaba' ..."""
    key = ("bronze", "silver", "gold")[tier_index - 1]
    return _pick(TIER_LABELS[key], lang)


def tier_key(tier_index):
    return ("bronze", "silver", "gold")[tier_index - 1] if tier_index else None
