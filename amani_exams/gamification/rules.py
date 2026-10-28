"""Pure gamification rules (SRS section 5). No Django, no database: everything here takes plain
values and returns plain values, so it is fast to test (`python -m unittest gamification.test_rules`).

Principles that every function here respects:
- Rewards never change exam marks (BR-10). Nothing in this file touches a mark.
- Days follow East Africa Time. Callers pass already-localised `date` objects.
"""
from collections import Counter
from datetime import timedelta

# ---------------------------------------------------------------- XP (SRS 5.1)

DEFAULT_XP = {
    "submit_exam": 50,        # Submit an exam
    "finish_early": 10,       # Finish before time runs out
    "score_per_percent": 1,   # 1 XP for every 1 percent scored ...
    "score_max": 100,         # ... up to 100
    "improvement": 30,        # Beat your previous score in the same subject
    "perfect_score": 100,     # Perfect score (100 percent)
    "review_wrong": 10,       # Review your wrong answers after results (per exam)
    "practice_quiz": 20,      # Complete a practice quiz
    "streak_3": 15, "streak_7": 50, "streak_14": 100, "streak_30": 250,  # streak milestones
}

# SRS 5.2. "name_sw" is the Swahili name shown to students who chose Swahili.
DEFAULT_LEVELS = [
    {"level": 1, "name": "Beginner", "name_sw": "Mwanzo", "xp": 0},
    {"level": 2, "name": "Learner", "name_sw": "Mwanafunzi", "xp": 200},
    {"level": 3, "name": "Achiever", "name_sw": "Mfanikivu", "xp": 500},
    {"level": 4, "name": "Scholar", "name_sw": "Msomi", "xp": 1000},
    {"level": 5, "name": "Star", "name_sw": "Nyota", "xp": 2000},
    {"level": 6, "name": "Champion", "name_sw": "Bingwa", "xp": 3500},
    {"level": 7, "name": "Genius", "name_sw": "Kipanga", "xp": 5000},
]

STREAK_MILESTONES = (3, 7, 14, 30)
TIER_NAMES = ("bronze", "silver", "gold")
COMEBACK_POINTS = 15          # Comeback Kid: improve by 15 percentage points or more
STEADY_PACE_PERCENT = 70      # Steady Pace: finish in time with 70 percent or more
EARLY_START_MINUTES = 5       # Always On Time: start within the first 5 minutes
ALL_ROUNDER_MIN_SUBJECTS = 3  # All-Rounder needs results in at least this many subjects in the term
MAX_BRIDGE_DAYS = 62          # a gap longer than this can never be bridged by freezes


def score_xp(percent, per_percent=1, cap=100):
    """1 XP per percent scored, up to the cap. Half a percent rounds up, like a whole mark."""
    return max(0, min(int(cap), int(float(percent) * per_percent + 0.5)))


# ---------------------------------------------------------------- levels (SRS 5.2)

def level_for(xp, levels=None):
    """Return the student's level and progress towards the next one."""
    levels = sorted(levels or DEFAULT_LEVELS, key=lambda lv: lv["xp"])
    xp = max(0, int(xp))
    current = levels[0]
    for lv in levels:
        if xp >= lv["xp"]:
            current = lv
    nxt = next((lv for lv in levels if lv["xp"] > xp), None)
    if nxt:
        span = nxt["xp"] - current["xp"]
        progress = round((xp - current["xp"]) / span * 100, 1) if span else 100.0
    else:
        progress = 100.0
    return {
        "level": current["level"], "name": current["name"], "name_sw": current.get("name_sw") or current["name"],
        "xp": xp, "level_xp": current["xp"],
        "next_level": nxt["level"] if nxt else None,
        "next_name": nxt["name"] if nxt else None,
        "next_name_sw": (nxt.get("name_sw") or nxt["name"]) if nxt else None,
        "next_xp": nxt["xp"] if nxt else None,
        "xp_to_next": nxt["xp"] - xp if nxt else 0,
        "progress_percent": progress,
    }


# ---------------------------------------------------------------- streaks (SRS 5.3)

def _month(d):
    return (d.year, d.month)


def compute_runs(days, free_per_month=2):
    """Group learning days into streak runs. Returns (runs, freezes_used_by_month).

    A run continues over a missed day only if that day can be covered by a freeze: each student
    has `free_per_month` freezes per calendar month. A gap is covered completely or not at all.
    Each run is {"start", "end", "length", "frozen"}; `length` counts days she actually learned.
    The result depends only on the SET of days, so a late-recorded day can never corrupt a streak."""
    days = sorted(set(days))
    used = Counter()
    runs = []
    for d in days:
        if not runs:
            runs.append({"start": d, "end": d, "length": 1, "frozen": []})
            continue
        run = runs[-1]
        gap = (d - run["end"]).days - 1
        if gap <= 0:
            run["end"], run["length"] = d, run["length"] + 1
            continue
        if gap <= MAX_BRIDGE_DAYS:
            missed = [run["end"] + timedelta(days=i) for i in range(1, gap + 1)]
            need = Counter(_month(m) for m in missed)
            if all(used[mo] + n <= free_per_month for mo, n in need.items()):
                used.update(need)
                run["frozen"].extend(missed)
                run["end"], run["length"] = d, run["length"] + 1
                continue
        runs.append({"start": d, "end": d, "length": 1, "frozen": []})
    return runs, used


def streak_status(days, today, free_per_month=2):
    """The streak as the student sees it on `today`. Does not change anything.

    A streak is alive if she learned today, or if every day since her last learning day up to
    yesterday can still be covered by a freeze. Today itself is never "missed" yet."""
    days = set(days)
    runs, used = compute_runs(days, free_per_month)
    this_month = _month(today)
    if not runs:
        return {"current": 0, "best": 0, "active_today": False, "at_risk": False, "last_active": None,
                "run_start": None, "freezes_used_this_month": 0, "freezes_left_this_month": free_per_month}
    last = runs[-1]
    best = max(r["length"] for r in runs)
    pending = Counter()
    alive = True
    if last["end"] < today:
        gap = (today - last["end"]).days - 1  # days after her last learning day, up to yesterday
        if gap > MAX_BRIDGE_DAYS:
            alive = False
        elif gap > 0:
            missed = [last["end"] + timedelta(days=i) for i in range(1, gap + 1)]
            need = Counter(_month(m) for m in missed)
            alive = all(used[mo] + n <= free_per_month for mo, n in need.items())
            if alive:
                pending = need
    current = last["length"] if alive else 0
    spent = used[this_month] + pending[this_month]
    return {
        "current": current, "best": max(best, current),
        "active_today": today in days, "at_risk": current > 0 and today not in days,
        "last_active": last["end"], "run_start": last["start"] if alive else None,
        "freezes_used_this_month": spent, "freezes_left_this_month": max(0, free_per_month - spent),
    }


def exam_streak(took_flags):
    """Exam participation streak: consecutive scheduled exams the student took.
    `took_flags` is oldest-first, True where she sat the exam. Returns (current, best)."""
    cur = best = 0
    for took in took_flags:
        cur = cur + 1 if took else 0
        best = max(best, cur)
    return cur, best


# ---------------------------------------------------------------- badges (SRS 5.4)

def tier_for(value, thresholds):
    """0 = not earned, 1 = bronze, 2 = silver, 3 = gold. `thresholds` is [bronze, silver, gold]."""
    return sum(1 for th in thresholds if value >= th)


def next_target(value, thresholds):
    """The next threshold the student has not reached yet, or None when she holds gold."""
    return next((th for th in thresholds if value < th), None)


def count_comebacks(percents, jump=COMEBACK_POINTS):
    """`percents` is one subject's results, oldest first. Counts exams that beat the previous one by `jump`+ points."""
    return sum(1 for a, b in zip(percents, percents[1:]) if b - a >= jump - 1e-9)


def is_top_grade(points, scale):
    """True if `points` is the best (lowest) grade points in the scale in force when the result was marked."""
    best = min(g["points"] for g in scale["grades"])
    return points == best


def second_best_points(scale):
    """Grade points of 'B or better' in this scale (the second-best distinct points value)."""
    pts = sorted({g["points"] for g in scale["grades"]})
    return pts[1] if len(pts) > 1 else pts[0]


# ---------------------------------------------------------------- admin settings validation (ADM-09)

def validate_xp(values):
    """Return (clean, problems) for an admin-edited XP table."""
    problems, clean = [], {}
    if not isinstance(values, dict):
        return {}, ["XP values must be a list of name and number pairs."]
    for k, v in values.items():
        if k not in DEFAULT_XP:
            problems.append(f"'{k}' is not a known XP setting.")
            continue
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1000:
            problems.append(f"'{k}' must be a whole number from 0 to 1000.")
            continue
        clean[k] = v
    if clean.get("score_per_percent", 1) > 10:
        problems.append("'score_per_percent' must be 10 or less.")
    return clean, problems


def validate_levels(levels):
    """Return (clean, problems). Levels must start at 0 XP, count up from 1 and need more XP each time."""
    if not isinstance(levels, list) or len(levels) < 2 or len(levels) > 20:
        return [], ["Give between 2 and 20 levels."]
    clean, problems = [], []
    for i, lv in enumerate(levels, start=1):
        try:
            xp, name = int(lv["xp"]), str(lv["name"]).strip()
        except (KeyError, TypeError, ValueError):
            return [], ["Every level needs a name and the XP needed."]
        if not name or len(name) > 30:
            problems.append(f"Level {i} needs a name of up to 30 characters.")
        if lv.get("level", i) != i:
            problems.append("Levels must be numbered 1, 2, 3 in order.")
        row = {"level": i, "name": name[:30], "xp": xp}
        if str(lv.get("name_sw", "")).strip():
            row["name_sw"] = str(lv["name_sw"]).strip()[:30]
        clean.append(row)
    if clean and clean[0]["xp"] != 0:
        problems.append("Level 1 must need 0 XP.")
    for a, b in zip(clean, clean[1:]):
        if b["xp"] <= a["xp"]:
            problems.append(f"Level {b['level']} must need more XP than level {a['level']}.")
    return clean, problems


def validate_tiers(tiers, known_codes):
    """Return (clean, problems) for {badge code: [bronze, silver, gold]} targets."""
    if not isinstance(tiers, dict):
        return {}, ["Badge targets must be a list of badge codes with three numbers each."]
    clean, problems = {}, []
    for code, th in tiers.items():
        if code not in known_codes:
            problems.append(f"'{code}' is not a known badge.")
            continue
        ok = (isinstance(th, list) and len(th) == 3
              and all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in th)
              and th[0] < th[1] < th[2])
        if not ok:
            problems.append(f"'{code}' needs three whole numbers that go up, for bronze, silver and gold.")
            continue
        clean[code] = th
    return clean, problems
