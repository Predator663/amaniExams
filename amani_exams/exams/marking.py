"""Automatic marking (BR-01). Pure functions: easy to test, no database access."""


def _norm(s):
    return " ".join(str(s).lower().split())


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fraction_correct(payload, response, partial=False):
    """Return a value from 0.0 to 1.0 for how correct `response` is."""
    qtype, ans = payload["qtype"], payload["answer"]

    if response is None:
        return 0.0

    if qtype == "mcq_single":
        return 1.0 if response == ans["correct"] else 0.0

    if qtype == "mcq_multi":
        if not isinstance(response, list):
            return 0.0
        chosen, correct = set(response), set(ans["correct"])
        if chosen == correct:
            return 1.0
        if partial:  # right picks minus wrong picks, never below zero
            return max(0.0, (len(chosen & correct) - len(chosen - correct)) / len(correct))
        return 0.0

    if qtype == "true_false":
        if isinstance(response, str):
            response = {"true": True, "false": False}.get(response.strip().lower())
        return 1.0 if response is ans["correct"] else 0.0

    if qtype == "matching":
        if not isinstance(response, dict):
            return 0.0
        right = sum(1 for k, v in ans["pairs"].items() if response.get(k) == v)
        if right == len(ans["pairs"]):
            return 1.0
        return right / len(ans["pairs"]) if partial else 0.0

    if qtype == "fill_blank":
        text = _norm(response)
        if any(text == _norm(a) for a in ans.get("accepted", [])):
            return 1.0
        n = ans.get("numeric")
        value = _num(response)
        if n and value is not None and abs(value - n["value"]) <= n["tolerance"] + 1e-9:
            return 1.0
        return 0.0

    if qtype == "ordering":
        if not isinstance(response, list):
            return 0.0
        correct = ans["order"]
        if response == correct:
            return 1.0
        if partial:
            same = sum(1 for a, b in zip(response, correct) if a == b)
            return same / len(correct)
        return 0.0

    return 0.0


def marks_for(payload, response, *, partial, negative, negative_fraction):
    """Marks awarded for one answer. Unanswered/skipped is always 0 (never negative)."""
    base = payload["marks"]
    if response is None:
        return 0.0
    f = fraction_correct(payload, response, partial)
    if f > 0:
        return round(base * f, 2)
    if negative:
        return round(-base * negative_fraction, 2)
    return 0.0
