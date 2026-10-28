"""Analytics maths (no Django imports, so it is quick to test). Views feed it plain dicts.

A "row" is one published result:
  result_id, attempt_id, attempt_no, student_id, student_name, class_id, class_label, stream,
  exam_id, exam_title, subject_id, subject, term_id, date, percent, grade, points, passed,
  time_taken, topic_stats {topic: [earned, possible]}, scale
"""
from collections import Counter, defaultdict

from core import grading
from exams import marking

LOW_PERCENT = 30       # latest score below this: needs support
SUPPORT_AVG = 45       # average of the last three below this: needs support
TOP_AVG = 75           # average of the last three at or above this: top performer
DECLINE_POINTS = 10    # three falling scores losing at least this much: needs support
STRONG_TOPIC, WEAK_TOPIC = 70, 50


def _avg(values, digits=1):
    return round(sum(values) / len(values), digits) if values else None


def latest_attempts(rows):
    """A retake (granted by an admin) replaces the first attempt in analytics."""
    best = {}
    for r in rows:
        k = (r["student_id"], r["exam_id"])
        if k not in best or r["attempt_no"] > best[k]["attempt_no"]:
            best[k] = r
    return list(best.values())


def summary(rows):
    n = len(rows)
    percents = [r["percent"] for r in rows]
    return {
        "count": n,
        "average": _avg(percents),
        "highest": max(percents) if percents else None,
        "lowest": min(percents) if percents else None,
        "pass_rate": round(100 * sum(1 for r in rows if r["passed"]) / n, 1) if n else None,
        "grade_distribution": dict(sorted(Counter(r["grade"] for r in rows).items())),
    }


def trend(rows):
    by_exam = defaultdict(list)
    for r in rows:
        by_exam[r["exam_id"]].append(r)
    out = []
    for exam_id, rs in by_exam.items():
        s = summary(rs)
        out.append({"exam_id": exam_id, "title": rs[0]["exam_title"], "date": rs[0]["date"],
                    "participants": s["count"], "average": s["average"], "pass_rate": s["pass_rate"]})
    return sorted(out, key=lambda x: (x["date"] is None, x["date"]))


def by_group(rows, key_fn, label_fn):
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    out = []
    for k, rs in groups.items():
        s = summary(rs)
        out.append({"key": k, "label": label_fn(rs[0]), "count": s["count"], "average": s["average"],
                    "pass_rate": s["pass_rate"]})
    return sorted(out, key=lambda x: str(x["label"]))


def topic_percentages(rows):
    totals = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        for topic, (earned, possible) in (r.get("topic_stats") or {}).items():
            totals[topic][0] += earned
            totals[topic][1] += possible
    out = [{"topic": t, "earned": round(e, 2), "possible": round(p, 2),
            "percent": round(e / p * 100, 1)} for t, (e, p) in totals.items() if p > 0]
    return sorted(out, key=lambda x: x["percent"])


def strengths_and_weaknesses(topics):
    return {
        "strengths": sorted((t for t in topics if t["percent"] >= STRONG_TOPIC), key=lambda t: -t["percent"]),
        "weak_areas": [t for t in topics if t["percent"] < WEAK_TOPIC],  # already weakest first
    }


def heatmap(rows):
    """TCH-06: topics (rows) by class (columns), each cell a percentage or None."""
    cells = defaultdict(lambda: [0.0, 0.0])
    classes, topics = {}, set()
    for r in rows:
        classes[r["class_id"]] = r["class_label"]
        for topic, (earned, possible) in (r.get("topic_stats") or {}).items():
            topics.add(topic)
            c = cells[(topic, r["class_id"])]
            c[0] += earned
            c[1] += possible
    cols = sorted(classes.items(), key=lambda kv: str(kv[1]))
    topics = sorted(topics)
    matrix = []
    for t in topics:
        line = []
        for cid, _ in cols:
            e, p = cells.get((t, cid), (0, 0))
            line.append(round(e / p * 100, 1) if p else None)
        matrix.append(line)
    return {"topics": topics, "classes": [{"id": cid, "label": lbl} for cid, lbl in cols], "cells": matrix}


def history(rows):
    return [{"exam_id": r["exam_id"], "exam": r["exam_title"], "date": r["date"], "percent": r["percent"],
             "grade": r["grade"], "time_taken": r["time_taken"]}
            for r in sorted(rows, key=lambda r: (r["date"] is None, r["date"]))]


def flag_for(percents):
    """percents in date order. Returns (flag, reason); flag is None, needs_support or top_performer (TCH-04)."""
    if not percents:
        return None, ""
    last3 = percents[-3:]
    avg3 = sum(last3) / len(last3)
    if percents[-1] < LOW_PERCENT:
        return "needs_support", "Latest score is below the pass level."
    if len(last3) == 3 and last3[0] > last3[1] > last3[2] and last3[0] - last3[2] >= DECLINE_POINTS:
        return "needs_support", "Scores have fallen in the last three exams."
    if avg3 < SUPPORT_AVG:
        return "needs_support", "Recent average is low."
    if avg3 >= TOP_AVG:
        return "top_performer", "Recent average is excellent."
    return None, ""


def student_overview(rows):
    """One line per student for the teacher's list (TCH-03)."""
    by_student = defaultdict(list)
    for r in rows:
        by_student[r["student_id"]].append(r)
    out = {}
    for sid, rs in by_student.items():
        h = history(rs)
        flag, reason = flag_for([x["percent"] for x in h])
        out[sid] = {"exams_taken": len(h), "average": _avg([x["percent"] for x in h]),
                    "latest": h[-1]["percent"], "history": h, "flag": flag, "flag_reason": reason}
    return out


def _tf(v):
    if isinstance(v, str):
        return {"true": True, "false": False}.get(v.strip().lower())
    return v if isinstance(v, bool) else None


def _option_text(payload, option_id):
    for o in (payload.get("content") or {}).get("options", []):
        if o["id"] == option_id:
            return o.get("text", "")
    return ""


def observed_difficulty(percent_correct):
    if percent_correct is None:
        return None
    return "easy" if percent_correct >= 70 else "medium" if percent_correct >= 40 else "hard"


def question_stats(questions, answers, n_attempts):
    """TCH-05. questions: [{id, position, voided, payload}]; answers: [{exam_question_id, response, skipped}]."""
    by_q = defaultdict(list)
    for a in answers:
        by_q[a["exam_question_id"]].append(a)
    out = []
    for q in sorted(questions, key=lambda q: q["position"]):
        p, given = q["payload"], [a for a in by_q[q["id"]] if not a["skipped"] and a["response"] is not None]
        correct = sum(1 for a in given if marking.fraction_correct(p, a["response"], partial=False) == 1.0)
        pct = round(correct / n_attempts * 100, 1) if n_attempts else None
        wrong = Counter()
        qt = p["qtype"]
        for a in given:
            r = a["response"]
            if marking.fraction_correct(p, r, partial=False) == 1.0:
                continue
            if qt == "mcq_single":
                wrong[str(r)] += 1
            elif qt == "mcq_multi" and isinstance(r, list):
                for o in set(r) - set(p["answer"]["correct"]):
                    wrong[str(o)] += 1
            elif qt == "true_false" and _tf(r) is not None:
                wrong["True" if _tf(r) else "False"] += 1
            elif qt == "fill_blank":
                wrong[" ".join(str(r).lower().split())] += 1
        top = None
        if wrong:
            key, count = wrong.most_common(1)[0]
            text = _option_text(p, key) if qt in ("mcq_single", "mcq_multi") else key
            top = {"id": key, "text": text, "count": count,
                   "share": round(count / n_attempts * 100, 1) if n_attempts else None}
        out.append({"exam_question_id": q["id"], "number": q["position"], "voided": q["voided"],
                    "prompt": p["prompt"], "topic": p.get("topic", ""), "type": qt, "marked_difficulty": p.get("difficulty"),
                    "answered": len(given), "percent_correct": pct, "observed_difficulty": observed_difficulty(pct),
                    "most_chosen_wrong": top})
    return out


def report_card(subject_averages, scale):
    """GRD-02 / GRD-03: grade each subject from its average, then add the best N subjects' points."""
    rows = []
    for name, avg in subject_averages.items():
        g = grading.grade_for(avg, scale)
        rows.append({"subject": name, "average": round(avg, 1), "grade": g["grade"], "points": g["points"]})
    rows.sort(key=lambda r: (r["points"], -r["average"], r["subject"]))
    n = scale.get("subjects_counted", 7)
    for i, r in enumerate(rows):
        r["counted"] = i < n
    div = grading.division_for([r["points"] for r in rows], scale)
    return {"subjects": rows, "subjects_needed": n, "subjects_taken": len(rows),
            "total_points": div["total_points"] if div else None,
            "division": div["division"] if div else None, "meaning": div["meaning"] if div else None}
