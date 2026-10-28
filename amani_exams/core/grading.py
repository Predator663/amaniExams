"""NECTA O-Level grading (SRS 4.11). The scale is data, stored in SchoolSettings and
snapshotted onto every result, so editing it later never changes old results (GRD-04)."""
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_SCALE = {
    "grades": [
        {"grade": "A", "min": 75, "max": 100, "meaning": "Excellent", "points": 1},
        {"grade": "B", "min": 65, "max": 74, "meaning": "Very good", "points": 2},
        {"grade": "C", "min": 45, "max": 64, "meaning": "Good", "points": 3},
        {"grade": "D", "min": 30, "max": 44, "meaning": "Satisfactory (pass)", "points": 4},
        {"grade": "F", "min": 0, "max": 29, "meaning": "Fail", "points": 5},
    ],
    "divisions": [
        {"division": "I", "min": 7, "max": 17, "meaning": "Excellent"},
        {"division": "II", "min": 18, "max": 21, "meaning": "Very good"},
        {"division": "III", "min": 22, "max": 25, "meaning": "Good"},
        {"division": "IV", "min": 26, "max": 33, "meaning": "Pass"},
        {"division": "0", "min": 34, "max": 999, "meaning": "Fail"},
    ],
    "subjects_counted": 7,
}


def whole_mark(percent):
    return int(Decimal(str(round(percent, 4))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def grade_for(percent, scale=None):
    scale = scale or DEFAULT_SCALE
    mark = max(0, min(100, whole_mark(percent)))
    for g in scale["grades"]:
        if g["min"] <= mark <= g["max"]:
            return g
    return scale["grades"][-1]


def division_for(points, scale=None):
    """Sum of the best N subjects' points (lower is better). None if too few subjects."""
    scale = scale or DEFAULT_SCALE
    n = scale.get("subjects_counted", 7)
    if len(points) < n:
        return None
    total = sum(sorted(points)[:n])
    for d in scale["divisions"]:
        if d["min"] <= total <= d["max"]:
            return {"total_points": total, **d}
    return None


def validate_scale(scale):
    """Return a list of plain-language problems with an admin-edited scale (empty list = fine)."""
    if not isinstance(scale, dict):
        return ["The grading scale must contain grades and divisions."]
    problems = []

    def spans(items, label, name_key, extra_keys):
        out = []
        if not isinstance(items, list) or not items:
            problems.append(f"Add at least one {label}.")
            return out
        for it in items:
            try:
                lo, hi = int(it["min"]), int(it["max"])
                name = str(it[name_key]).strip()
                for k in extra_keys:
                    int(it[k])
            except (KeyError, TypeError, ValueError):
                problems.append(f"Every {label} needs min, max, {name_key}" + "".join(f", {k}" for k in extra_keys) + ".")
                return []
            if not name or lo > hi:
                problems.append(f"The {label} '{name}' has no name or its minimum is above its maximum.")
                return []
            out.append((lo, hi, name))
        return sorted(out)

    expected = 0
    for lo, hi, name in spans(scale.get("grades"), "grade", "grade", ("points",)):
        if lo != expected:
            problems.append(f"Grade ranges must run from 0 to 100 with no gaps or overlaps (check grade {name}).")
            expected = None
            break
        expected = hi + 1
    if expected is not None and expected != 101 and not any("Add at least one grade" in p or "Every grade" in p for p in problems):
        problems.append("Grade ranges must end at 100.")

    prev = None
    for lo, hi, name in spans(scale.get("divisions"), "division", "division", ()):
        if prev is not None and lo != prev + 1:
            problems.append(f"Division bands must follow each other with no gaps or overlaps (check division {name}).")
            break
        prev = hi
    try:
        n = int(scale.get("subjects_counted", 7))
        if not 1 <= n <= 12:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("Subjects counted for the division must be a number from 1 to 12.")
    return problems


def normalize_scale(scale):
    """Coerce a validated scale to clean ints/strings so grading code can trust it."""
    return {
        "grades": [{"grade": str(g["grade"]).strip(), "min": int(g["min"]), "max": int(g["max"]),
                    "meaning": str(g.get("meaning", "")), "points": int(g["points"])} for g in scale["grades"]],
        "divisions": [{"division": str(d["division"]).strip(), "min": int(d["min"]), "max": int(d["max"]),
                       "meaning": str(d.get("meaning", ""))} for d in scale["divisions"]],
        "subjects_counted": int(scale.get("subjects_counted", 7)),
    }
