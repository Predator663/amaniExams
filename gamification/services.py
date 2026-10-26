"""Gamification services: XP, levels, streaks, badges, review tracking, practice mode, leaderboard
(SRS section 5) and the engagement numbers teachers and admins see (TCH-03, ADM-08).

Rules this file never breaks:
- BR-10: rewards never change marks, are given only AFTER results are published, and never reveal
  other students' marks. Exam rewards are processed by `reward_attempt`, which refuses to run
  until the exam is Published and the student's own results are visible.
- Every award is idempotent. XP has a unique `key` per student, and each exam is processed once
  (`ExamRewardMark`), so lazy calls, cron calls and double taps can never pay twice.
- A problem here must never stop a student seeing her results: callers wrap these calls.
- Days follow East Africa Time (`timezone.localdate`).
"""
import logging
import random
from collections import Counter, defaultdict
from datetime import timedelta
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Sum
from django.utils import timezone

from academics.models import SchoolClass, Subject, Term
from accounts.models import User
from core import grading
from core.i18n import lang_of, t
from core.models import SchoolSettings
from exams import marking, services as exam_services
from exams.models import Attempt, Exam, ExamQuestion, Result
from exams.presenters import public_question
from notifications.services import notify
from questions.models import Question
from . import catalog, rules
from .models import (AVATARS, ActivityDay, BadgeAward, ExamRewardMark, GamificationSettings, PracticeSession, Profile,
                     ReviewProgress, XPEvent)

log = logging.getLogger(__name__)

PRACTICE_MIN, PRACTICE_MAX, PRACTICE_DEFAULT = 5, 20, 10  # SRS 5.3: a streak needs a quiz of at least 5 questions
PRACTICE_STALE_HOURS = 12  # an unfinished quiz older than this is abandoned when a new one starts


class GamificationError(Exception):
    def __init__(self, message, status=400, code="error"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


# ---------------------------------------------------------------- configuration

def config():
    """The effective settings: SRS defaults with the admin's changes on top."""
    s = GamificationSettings.load()
    xp = dict(rules.DEFAULT_XP)
    xp.update({k: v for k, v in (s.xp_values or {}).items() if k in rules.DEFAULT_XP})
    tiers = {b["code"]: list(b["tiers"]) for b in catalog.BADGES}
    tiers.update({k: list(v) for k, v in (s.badge_tiers or {}).items() if k in tiers})
    return {"xp": xp, "levels": s.levels or rules.DEFAULT_LEVELS, "tiers": tiers,
            "freezes": s.freezes_per_month, "practice_cap": s.practice_daily_xp_quizzes}


def get_profile(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def display_name(user, profile=None):
    """What classmates see (SRS 5.6): the name she chose, else 'Amina K.' (first name and last initial)."""
    if profile is not None and profile.display_name.strip():
        return profile.display_name.strip()
    first, last = (user.first_name or "").strip(), (user.last_name or "").strip()
    if first and last:
        return f"{first} {last[0].upper()}."
    return first or user.username


# ---------------------------------------------------------------- XP and levels

def total_xp(user):
    return XPEvent.objects.filter(user=user).aggregate(s=Sum("points"))["s"] or 0


def level_table(cfg):
    """All levels, sorted, each with a Swahili name (falls back to the English one if an admin gave none)."""
    return [{"level": lv["level"], "name": lv["name"], "name_sw": lv.get("name_sw") or lv["name"], "xp": lv["xp"]}
            for lv in sorted(cfg["levels"], key=lambda lv: lv["xp"])]


def level_payload(xp, cfg, lang="en"):
    lvl = rules.level_for(xp, cfg["levels"])
    sw = lang == "sw"
    return {**lvl, "name": lvl["name_sw"] if sw else lvl["name"],
            "next_name": (lvl["next_name_sw"] if sw else lvl["next_name"])}


def award_xp(user, kind, points, key, exam_id=None, **detail):
    """Give XP once per `key`. Returns the new XPEvent, or None if it was zero or already given."""
    if points <= 0:
        return None
    ev, created = XPEvent.objects.get_or_create(
        user=user, key=key, defaults={"kind": kind, "points": points, "exam_id": exam_id, "detail": detail})
    return ev if created else None


def xp_label(event, lang="en"):
    key = {"submit": "xp.submit", "early": "xp.early", "score": "xp.score", "improve": "xp.improve",
           "perfect": "xp.perfect", "review": "xp.review", "practice": "xp.practice", "streak": "xp.streak"}.get(event.kind)
    return t(key, lang, **(event.detail or {})) if key else event.kind


def check_level(user, cfg):
    """Tell the student when she reaches a new level (once per level)."""
    lvl = level_payload(total_xp(user), cfg, lang_of(user))
    if lvl["level"] > 1:
        lang = lang_of(user)
        notify([user], "level_up", t("level.up.title", lang, name=lvl["name"]),
               t("level.up.body", lang, level=lvl["level"]), key=f"level:{lvl['level']}",
               data={"level": lvl["level"]}, push=False)
    return lvl


# ---------------------------------------------------------------- streaks

def activity_days(user):
    return list(ActivityDay.objects.filter(user=user).values_list("day", flat=True))


def sync_streak(user, cfg):
    """Work the streaks out again from all learning days and pay any milestone not yet paid (3, 7, 14, 30 days)."""
    runs, _ = rules.compute_runs(activity_days(user), cfg["freezes"])
    for run in runs:
        for n in rules.STREAK_MILESTONES:
            if run["length"] >= n:
                award_xp(user, "streak", cfg["xp"][f"streak_{n}"], f"streak:{n}:{run['start'].isoformat()}", n=n)
    return runs


def record_activity(user, day, source, cfg):
    """Count `day` as a learning day (a practice quiz of 5+ questions, an exam, or a review of results)."""
    ActivityDay.objects.get_or_create(user=user, day=day, defaults={"source": source})
    return sync_streak(user, cfg)


def exam_streak(student):
    """Exam participation streak: consecutive scheduled exams (with published results) she sat."""
    exam_ids = list(Exam.objects.filter(pk__in=exam_services.exams_for_student(student).values("pk"), status=Exam.PUBLISHED)
                    .order_by("start_at").values_list("pk", flat=True))
    took = set(Attempt.objects.filter(student=student, exam_id__in=exam_ids).values_list("exam_id", flat=True))
    return rules.exam_streak([pk in took for pk in exam_ids])


# ---------------------------------------------------------------- badges

def compute_metrics(student, cfg, today=None):
    """Every number the badges are earned from, worked out from her processed results and activity.
    Only exams whose rewards were processed (hence published and visible to her) are counted."""
    today = today or timezone.localdate()
    marked = list(ExamRewardMark.objects.filter(user=student).values_list("exam_id", flat=True))
    rows = list(Result.objects.filter(student=student, exam_id__in=marked, attempt__attempt_no=1)
                .select_related("exam", "attempt"))
    m = {"exams_completed": 0, "perfect_scores": 0, "steady_exams": 0, "early_starts": 0}
    by_subject = defaultdict(list)
    top = Counter()
    by_term = defaultdict(lambda: defaultdict(list))
    for r in rows:
        e, a = r.exam, r.attempt
        m["exams_completed"] += 1
        if r.percent >= 100 - 1e-9:
            m["perfect_scores"] += 1
        if a.status == Attempt.SUBMITTED and r.percent >= rules.STEADY_PACE_PERCENT:
            m["steady_exams"] += 1
        if e.start_at and a.started_at <= e.start_at + timedelta(minutes=rules.EARLY_START_MINUTES):
            m["early_starts"] += 1
        start = e.start_at or a.started_at
        by_subject[e.subject_id].append((start, r.percent))
        if rules.is_top_grade(r.points, r.scale_snapshot):
            top[e.subject_id] += 1
        if e.term_id:
            by_term[e.term_id][e.subject_id].append((start, r.percent, r.scale_snapshot))
    m["comebacks"] = sum(rules.count_comebacks([p for _, p in sorted(items, key=lambda x: x[0])])
                         for items in by_subject.values())
    m["top_grades_by_subject"] = dict(top)

    rounder = 0  # All-Rounder: grade B or better in every subject, for a term that has ended
    ends = dict(Term.objects.filter(pk__in=list(by_term)).values_list("pk", "end_date"))
    for term_id, subjects in by_term.items():
        if len(subjects) < rules.ALL_ROUNDER_MIN_SUBJECTS or not (ends.get(term_id) and ends[term_id] < today):
            continue
        ok = True
        for items in subjects.values():
            scale = sorted(items, key=lambda x: x[0])[-1][2]
            avg = sum(p for _, p, _ in items) / len(items)
            if grading.grade_for(avg, scale)["points"] > rules.second_best_points(scale):
                ok = False
                break
        rounder += 1 if ok else 0
    m["all_rounder_terms"] = rounder

    m["best_streak"] = rules.streak_status(activity_days(student), today, cfg["freezes"])["best"]
    m["reviewed_exams"] = ReviewProgress.objects.filter(attempt__student=student, completed=True).count()
    m["practice_quizzes"] = PracticeSession.objects.filter(user=student, status=PracticeSession.COMPLETED).count()
    return m


def _subject_name(scope):
    if not scope:
        return None
    return Subject.objects.filter(pk=int(scope)).values_list("name", flat=True).first()


def badge_brief(code, scope, tier, lang="en"):
    """A badge as the app shows it right after it is earned."""
    return {"code": code, "scope": scope, "subject": _subject_name(scope), "tier": catalog.tier_key(tier), "tier_index": tier,
            "name": catalog.badge_name(code, lang, tier), "tier_label": catalog.tier_label(tier, lang),
            "description": catalog.badge_desc(code, lang)}


def evaluate_badges(student, cfg, metrics=None):
    """Give any badge or tier the student has now earned. Returns the new ones as [{"code", "scope", "tier"}]."""
    metrics = metrics if metrics is not None else compute_metrics(student, cfg)
    existing = {(b.code, b.scope): b for b in BadgeAward.objects.filter(user=student)}
    lang = lang_of(student)
    new = []
    for b in catalog.BADGES:
        thresholds = cfg["tiers"][b["code"]]
        if b.get("per_subject"):
            values = {str(sid): n for sid, n in metrics.get(b["metric"], {}).items()}
        else:
            values = {"": metrics.get(b["metric"], 0)}
        for scope, value in values.items():
            tier = rules.tier_for(value, thresholds)
            if tier == 0:
                continue
            cur = existing.get((b["code"], scope))
            if cur is None:
                try:
                    with transaction.atomic():
                        BadgeAward.objects.create(user=student, code=b["code"], scope=scope, tier=tier)
                except IntegrityError:
                    continue  # another request just gave it
            elif tier > cur.tier:
                cur.tier, cur.seen = tier, False
                cur.save(update_fields=["tier", "seen", "updated_at"])
            else:
                continue
            new.append({"code": b["code"], "scope": scope, "tier": tier})
            brief = badge_brief(b["code"], scope, tier, lang)
            title_name = brief["name"] + (f" - {brief['subject']}" if brief["subject"] else "")
            notify([student], "badge", t("badge.title", lang, name=title_name, tier=brief["tier_label"]),
                   t("badge.body", lang, desc=brief["description"]), key=f"badge:{b['code']}:{scope}:{tier}",
                   data={"code": b["code"], "scope": scope, "tier": tier}, push=False)
    return new


def badge_cabinet(student, cfg, lang="en"):
    """The badge cabinet (SRS 5.4): every badge with her tier, progress and next target."""
    metrics = compute_metrics(student, cfg)
    awards = {(b.code, b.scope): b for b in BadgeAward.objects.filter(user=student)}
    subjects = {str(s.pk): s.name for s in Subject.objects.all()}
    out = []
    for b in catalog.BADGES:
        thresholds = cfg["tiers"][b["code"]]
        if b.get("per_subject"):
            progress = {str(sid): n for sid, n in metrics.get(b["metric"], {}).items()}
            for (code, scope) in awards:
                if code == b["code"]:
                    progress.setdefault(scope, 0)
            scopes = sorted(progress) or [""]
            values = {s: progress.get(s, 0) for s in scopes}
        else:
            values = {"": metrics.get(b["metric"], 0)}
        for scope, value in values.items():
            award = awards.get((b["code"], scope))
            tier = max(award.tier if award else 0, rules.tier_for(value, thresholds))
            out.append({
                "code": b["code"], "scope": scope, "subject": subjects.get(scope) if scope else None,
                "name": catalog.badge_name(b["code"], lang, tier or None), "description": catalog.badge_desc(b["code"], lang),
                "unit": catalog.badge_unit(b["code"], lang), "earned": tier > 0, "tier": catalog.tier_key(tier), "tier_index": tier,
                "tier_label": catalog.tier_label(tier, lang) if tier else None,
                "progress": value, "next_target": rules.next_target(value, thresholds) if tier < 3 else None,
                "tiers": [{"tier": key, "label": catalog.tier_label(i, lang), "target": th, "reached": tier >= i}
                          for i, (key, th) in enumerate(zip(rules.TIER_NAMES, thresholds), start=1)],
                "new": bool(award and not award.seen),
                "earned_at": award.updated_at if award else None,
            })
    return out


# ---------------------------------------------------------------- exam rewards (BR-10)

def previous_percent(student, exam):
    """Her percentage in the closest earlier exam of the same subject (for 'beat your previous score')."""
    return (Result.objects.filter(student=student, exam__subject_id=exam.subject_id, exam__status=Exam.PUBLISHED,
                                  exam__start_at__lt=exam.start_at, attempt__attempt_no=1)
            .order_by("-exam__start_at").values_list("percent", flat=True).first())


def reward_attempt(attempt, now=None):
    """Hand out the XP, streak credit and badges for one exam, exactly once, and only after her results
    are published and visible (BR-10). Returns True if it rewarded now, False if not due or already done.

    Only the first attempt is rewarded: a retake is a special admin arrangement (for example after a
    power cut) and must not let anyone collect the same XP twice."""
    now = now or timezone.now()
    if attempt.attempt_no != 1 or attempt.status == Attempt.IN_PROGRESS:
        return False
    exam, student = attempt.exam, attempt.student
    exam_services.sync_exam(exam, now)
    if exam.status != Exam.PUBLISHED or not exam_services.result_visible(attempt, now):
        return False
    result = Result.objects.filter(attempt=attempt).first()
    if result is None or ExamRewardMark.objects.filter(user=student, exam_id=exam.pk).exists():
        return False
    cfg = config()
    xp = cfg["xp"]
    try:
        with transaction.atomic():
            mark = ExamRewardMark.objects.create(user=student, exam_id=exam.pk)
            award_xp(student, "submit", xp["submit_exam"], f"submit:{exam.pk}", exam.pk)
            if attempt.status == Attempt.SUBMITTED:
                award_xp(student, "early", xp["finish_early"], f"early:{exam.pk}", exam.pk)
            award_xp(student, "score", rules.score_xp(result.percent, xp["score_per_percent"], xp["score_max"]),
                     f"score:{exam.pk}", exam.pk, percent=int(result.percent + 0.5))
            prev = previous_percent(student, exam)
            if prev is not None and result.percent > prev + 1e-9:
                award_xp(student, "improve", xp["improvement"], f"improve:{exam.pk}", exam.pk)
            if result.percent >= 100 - 1e-9:
                award_xp(student, "perfect", xp["perfect_score"], f"perfect:{exam.pk}", exam.pk)
            record_activity(student, timezone.localtime(attempt.started_at).date(), "exam", cfg)
            mark.badges = evaluate_badges(student, cfg)
            mark.save(update_fields=["badges"])
            check_level(student, cfg)
    except IntegrityError:
        return False  # a second request processed the same exam at the same moment
    return True


def reward_pending_for(student, now=None):
    """Process any published exam this student has not been rewarded for yet. Called when she opens her
    home page or results, so correctness never depends on the cron job."""
    now = now or timezone.now()
    done = set(ExamRewardMark.objects.filter(user=student).values_list("exam_id", flat=True))
    attempts = (Attempt.objects.filter(student=student, attempt_no=1).exclude(status=Attempt.IN_PROGRESS)
                .exclude(exam_id__in=done).select_related("exam", "student", "exam__subject"))
    return sum(1 for a in attempts if reward_attempt(a, now))


def reward_pending(now=None, limit=2000):
    """Scheduler entry point: reward every published exam attempt not yet processed. Returns how many."""
    now = now or timezone.now()
    marked = ExamRewardMark.objects.filter(user=OuterRef("student"), exam_id=OuterRef("exam_id"))
    attempts = (Attempt.objects.filter(attempt_no=1, exam__status=Exam.PUBLISHED, exam__end_at__gte=now - timedelta(days=90))
                .exclude(status=Attempt.IN_PROGRESS).annotate(done=Exists(marked)).filter(done=False)
                .select_related("exam", "student", "exam__subject").order_by("exam_id")[:limit])
    count = 0
    for a in attempts:
        try:
            count += 1 if reward_attempt(a, now) else 0
        except Exception:  # one bad row must not stop the others
            log.exception("could not reward attempt %s", a.pk)
    return count


def rewards_for_attempt(attempt, lang=None):
    """What this exam earned her (RES-03): XP lines and badges."""
    lang = lang or lang_of(attempt.student)
    events = XPEvent.objects.filter(user=attempt.student, exam_id=attempt.exam_id).order_by("id")
    items = [{"kind": e.kind, "points": e.points, "label": xp_label(e, lang)} for e in events]
    mark = ExamRewardMark.objects.filter(user=attempt.student, exam_id=attempt.exam_id).first()
    badges = [badge_brief(b["code"], b["scope"], b["tier"], lang) for b in (mark.badges if mark else [])]
    return {"xp_total": sum(i["points"] for i in items), "xp": items, "badges": badges}


# ---------------------------------------------------------------- review mode (Mistake Master)

def wrong_numbers(attempt):
    """Question numbers she did not get full marks for (unanswered counts). Voided questions are left out."""
    answers = {a.exam_question_id: a for a in attempt.answers.all()}
    out = []
    for eq in attempt.exam.questions.all():
        if eq.voided:
            continue
        a = answers.get(eq.pk)
        got = a.marks_awarded if (a is not None and a.marks_awarded is not None) else 0.0
        if got < eq.payload["marks"] - 1e-9:
            out.append(eq.position)
    return out


def review_progress(attempt, lang="en"):
    prog = ReviewProgress.objects.filter(attempt=attempt).first()
    wrong = wrong_numbers(attempt)
    return {"wrong": wrong, "seen": prog.seen if prog else [], "completed": bool(prog and prog.completed),
            "all_correct": not wrong,
            "message": t("review.nothing", lang) if not wrong else (t("review.done", lang) if prog and prog.completed else "")}


def mark_reviewed(attempt, numbers, now=None):
    """The student viewed these question numbers in review mode. When she has seen every wrong answer
    she earns the review XP once and a learning day for her streak."""
    now = now or timezone.now()
    student, lang = attempt.student, lang_of(attempt.student)
    valid = set(attempt.exam.questions.values_list("position", flat=True))
    wrong = wrong_numbers(attempt)
    prog, _ = ReviewProgress.objects.get_or_create(attempt=attempt)
    prog.seen = sorted(set(prog.seen) | {n for n in numbers if isinstance(n, int) and n in valid})
    newly = bool(wrong) and not prog.completed and set(wrong) <= set(prog.seen)
    if newly:
        prog.completed, prog.completed_at = True, now
    prog.save()
    xp_awarded = 0
    if newly:
        cfg = config()
        ev = award_xp(student, "review", cfg["xp"]["review_wrong"], f"review:{attempt.exam_id}", attempt.exam_id)
        xp_awarded = ev.points if ev else 0
        record_activity(student, timezone.localdate(now), "review", cfg)
        evaluate_badges(student, cfg)
        check_level(student, cfg)
    return {"wrong": wrong, "seen": prog.seen, "completed": prog.completed, "all_correct": not wrong,
            "xp_awarded": xp_awarded,
            "message": t("review.nothing", lang) if not wrong else (t("review.done", lang) if prog.completed else "")}


# ---------------------------------------------------------------- practice mode (SRS 5.5)

def practice_pool(student, subject, topic=None, difficulty=None):
    """Questions a student may practise: approved, marked 'practice eligible' by a teacher, matching her form,
    and NEVER a question that sits in an exam whose results are not published yet (so no exam is spoiled)."""
    reserved = (ExamQuestion.objects.exclude(exam__status=Exam.PUBLISHED).filter(source__isnull=False)
                .values("source_id"))
    qs = Question.objects.filter(subject=subject, status=Question.APPROVED, practice_eligible=True).exclude(pk__in=reserved)
    if student.school_class_id:
        qs = qs.filter(form_level=student.school_class.form_level)
    if topic:
        qs = qs.filter(topic__iexact=topic)
    if difficulty in ("easy", "medium", "hard"):
        qs = qs.filter(difficulty=difficulty)
    return qs


def practice_subjects(student):
    out = []
    for s in Subject.objects.filter(practice_enabled=True):
        n = practice_pool(student, s).count()
        out.append({"id": s.pk, "name": s.name, "available_questions": n, "can_start": n >= PRACTICE_MIN})
    return out


def _practice_payload(q):
    return {"qtype": q.qtype, "prompt": q.prompt, "content": q.content, "answer": q.answer, "marks": q.marks,
            "explanation": q.explanation, "topic": q.topic, "subtopic": q.subtopic, "difficulty": q.difficulty,
            "language": q.language}


def start_practice(student, subject_id, count=PRACTICE_DEFAULT, topic=None, difficulty=None, restart=False, now=None):
    """Start a practice quiz, or return the one she is already in the middle of."""
    now = now or timezone.now()
    lang = lang_of(student)
    subject = Subject.objects.filter(pk=subject_id).first()
    if subject is None:
        raise GamificationError("That subject does not exist.", 404, "not_found")
    if not subject.practice_enabled:
        raise GamificationError(t("practice.disabled", lang), 403, "practice_off")
    stale = now - timedelta(hours=PRACTICE_STALE_HOURS)
    PracticeSession.objects.filter(user=student, status=PracticeSession.IN_PROGRESS, started_at__lt=stale) \
        .update(status=PracticeSession.ABANDONED)
    current = PracticeSession.objects.filter(user=student, status=PracticeSession.IN_PROGRESS, subject=subject).first()
    if current and not restart:
        return current
    if current:
        current.status = PracticeSession.ABANDONED
        current.save(update_fields=["status"])
    try:
        count = max(PRACTICE_MIN, min(PRACTICE_MAX, int(count)))
    except (TypeError, ValueError):
        count = PRACTICE_DEFAULT
    pool = list(practice_pool(student, subject, topic, difficulty))
    if len(pool) < PRACTICE_MIN:
        raise GamificationError(t("practice.not_enough", lang), 409, "not_enough")
    seed = random.SystemRandom().randrange(1, 2**31)
    picks = random.Random(seed).sample(pool, min(count, len(pool)))
    return PracticeSession.objects.create(
        user=student, subject=subject, seed=seed, question_count=len(picks),
        items=[{"qid": q.pk, "payload": _practice_payload(q)} for q in picks])


def practice_state(session):
    """What the phone shows: the current question (never its answer) or the finished summary."""
    n, done = len(session.items), len(session.answers)
    state = {"session_id": session.pk, "subject": session.subject.name, "total": n, "answered": done,
             "status": session.status}
    if session.status != PracticeSession.IN_PROGRESS or done >= n:
        state.update(finished=True, summary=practice_summary(session))
        return state
    item = session.items[done]
    state.update(finished=False, index=done + 1,
                 question=public_question(SimpleNamespace(pk=item["qid"], payload=item["payload"]), session.seed, True))
    return state


def practice_summary(session):
    n = len(session.items) or 1
    fully = sum(1 for a in session.answers if a["fraction"] >= 0.9999)
    return {"questions": len(session.items), "fully_correct": fully, "score_percent": round(session.correct_score / n * 100),
            "xp_earned": session.xp_awarded}


def _practice_feedback(session, index, lang):
    ans, item = session.answers[index], session.items[index]
    f = ans["fraction"]
    return {"question_id": ans["qid"], "fraction": f, "correct": f >= 0.9999, "your_response": ans["response"],
            "correct_answer": item["payload"]["answer"], "explanation": item["payload"].get("explanation", ""),
            "message": t("practice.correct" if f >= 0.9999 else ("practice.partly" if f > 0 else "practice.wrong"), lang)}


def answer_practice(session_id, student, question_id, response, now=None):
    """Mark one practice answer immediately and return instant feedback plus the next question (SRS 5.5)."""
    now = now or timezone.now()
    lang = lang_of(student)
    just_finished = False
    with transaction.atomic():
        s = PracticeSession.objects.select_for_update().select_related("subject").get(pk=session_id, user=student)
        if s.status != PracticeSession.IN_PROGRESS:
            raise GamificationError("This practice quiz is already finished.", 409, "finished")
        idx = len(s.answers)
        if question_id != s.items[idx]["qid"]:
            for i, a in enumerate(s.answers):  # a repeated send of an answer already marked: give the same feedback
                if a["qid"] == question_id:
                    return {"feedback": _practice_feedback(s, i, lang), "next": practice_state(s)}
            raise GamificationError("That is not the current question.", 409, "out_of_order")
        if response in (None, "", [], {}):
            raise GamificationError(t("practice.empty", lang), 400, "empty_answer")
        if len(str(response)) > 5000:
            raise GamificationError("That answer is too long.", 400, "too_long")
        fraction = marking.fraction_correct(s.items[idx]["payload"], response, partial=True)  # instant, automatic
        s.answers = s.answers + [{"qid": question_id, "response": response, "fraction": round(fraction, 4)}]
        s.correct_score = round(sum(a["fraction"] for a in s.answers), 4)
        if len(s.answers) >= len(s.items):
            s.status, s.completed_at, just_finished = PracticeSession.COMPLETED, now, True
        s.save()
    if just_finished:
        _finish_practice(s, student, now)
    return {"feedback": _practice_feedback(s, len(s.answers) - 1, lang), "next": practice_state(s)}


def _finish_practice(session, student, now):
    """XP (up to the daily limit), a learning day for the streak, and badge checks."""
    cfg = config()
    today = timezone.localdate(now)
    earned_today = XPEvent.objects.filter(user=student, kind="practice", created_at__date=today).count()
    if earned_today < cfg["practice_cap"]:
        ev = award_xp(student, "practice", cfg["xp"]["practice_quiz"], f"practice:{session.pk}")
        if ev:
            session.xp_awarded = ev.points
            session.save(update_fields=["xp_awarded"])
    record_activity(student, today, "practice", cfg)  # a quiz is at least PRACTICE_MIN questions, so it counts
    evaluate_badges(student, cfg)
    check_level(student, cfg)


# ---------------------------------------------------------------- leaderboard (SRS 5.6)

def week_start(now=None):
    local = timezone.localtime(now or timezone.now())
    return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def leaderboard(student, period="weekly", now=None, limit=10):
    """Class-level ranking by XP, never by exam marks. Shows display names to classmates only, leaves out
    students who chose to hide, and shows nobody with zero XP (nobody is shamed)."""
    now = now or timezone.now()
    lang = lang_of(student)
    if not SchoolSettings.load().leaderboard_enabled:
        return {"enabled": False, "message": t("leaderboard.off", lang)}
    period = "all" if period == "all" else "weekly"
    cfg = config()
    mates = list(User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False,
                                     school_class_id=student.school_class_id)) if student.school_class_id else []
    ids = [u.pk for u in mates]
    profiles = {p.user_id: p for p in Profile.objects.filter(user_id__in=ids)}
    hidden = {uid for uid, p in profiles.items() if p.hide_from_leaderboard}
    alltime = dict(XPEvent.objects.filter(user_id__in=ids).order_by().values_list("user_id").annotate(s=Sum("points")))
    if period == "weekly":
        totals = dict(XPEvent.objects.filter(user_id__in=ids, created_at__gte=week_start(now))
                      .order_by().values_list("user_id").annotate(s=Sum("points")))
    else:
        totals = alltime
    shown = [u for u in mates if u.pk not in hidden and totals.get(u.pk, 0) > 0]
    shown.sort(key=lambda u: (-totals[u.pk], display_name(u, profiles.get(u.pk)).lower()))
    ranked, last_xp, last_rank = [], None, 0
    for i, u in enumerate(shown, start=1):
        xp = totals[u.pk]
        rank = last_rank if xp == last_xp else i  # equal XP shares a rank
        last_xp, last_rank = xp, rank
        ranked.append((rank, u, xp))
    mine = next((r for r in ranked if r[1].pk == student.pk), None)
    my_xp = totals.get(student.pk, 0)
    you = {"hidden": student.pk in hidden, "xp": my_xp, "rank": mine[0] if mine else None, "message": ""}
    if you["hidden"]:
        you["message"] = t("leaderboard.hidden", lang)
    elif not mine:
        you["message"] = t("leaderboard.unranked", lang)
    entries = []
    for rank, u, xp in ranked[:limit]:
        p = profiles.get(u.pk)
        entries.append({"rank": rank, "name": display_name(u, p), "xp": xp, "avatar": p.avatar if p else AVATARS[0],
                        "level": level_payload(alltime.get(u.pk, 0), cfg, lang)["level"], "is_me": u.pk == student.pk})
    return {"enabled": True, "scope": "class", "period": period,
            "week_start": week_start(now) if period == "weekly" else None,
            "class_name": str(student.school_class) if student.school_class_id else None,
            "you": you, "entries": entries}


# ---------------------------------------------------------------- the student's home summary (HOME-03)

def student_summary(student, now=None):
    now = now or timezone.now()
    cfg, lang, today = config(), lang_of(student), timezone.localdate(now)
    profile = get_profile(student)
    xp = total_xp(student)
    lvl = level_payload(xp, cfg, lang)
    streak = rules.streak_status(activity_days(student), today, cfg["freezes"])
    exam_cur, exam_best = exam_streak(student)
    recent = [badge_brief(b.code, b.scope, b.tier, lang) | {"new": not b.seen} for b in BadgeAward.objects.filter(user=student)[:3]]
    cabinet = badge_cabinet(student, cfg, lang)
    goals = sorted((c for c in cabinet if c["next_target"]), key=lambda c: -(c["progress"] / c["next_target"]))[:3]
    message = ""
    if streak["current"] == 0 and streak["best"] > 0:
        message = t("streak.restart", lang)
    elif streak["at_risk"]:
        message = t("streak.keep", lang)
    return {
        "xp": xp, "level": lvl,
        "level_up": ({"from": profile.last_seen_level, "to": lvl["level"], "name": lvl["name"]}
                     if lvl["level"] > profile.last_seen_level else None),
        "streak": {**streak, "message": message},
        "exam_streak": {"current": exam_cur, "best": exam_best},
        "recent_badges": recent, "new_badges": BadgeAward.objects.filter(user=student, seen=False).count(),
        "next_goals": [{"code": g["code"], "name": g["name"], "subject": g["subject"], "progress": g["progress"],
                        "target": g["next_target"], "unit": g["unit"]} for g in goals],
        "leaderboard_enabled": SchoolSettings.load().leaderboard_enabled,
        "profile": profile_payload(profile),
    }


def profile_payload(profile):
    return {"avatar": profile.avatar, "display_name": profile.display_name, "hide_from_leaderboard": profile.hide_from_leaderboard,
            "avatars": AVATARS}


def acknowledge(student):
    """The student has seen her celebrations (new badges and the level-up)."""
    cfg = config()
    BadgeAward.objects.filter(user=student, seen=False).update(seen=True)
    profile = get_profile(student)
    profile.last_seen_level = rules.level_for(total_xp(student), cfg["levels"])["level"]
    profile.save(update_fields=["last_seen_level"])


def xp_history(student, limit=50, offset=0):
    lang = lang_of(student)
    qs = XPEvent.objects.filter(user=student)
    return {"total": total_xp(student), "count": qs.count(),
            "results": [{"at": e.created_at, "points": e.points, "kind": e.kind, "label": xp_label(e, lang)}
                        for e in qs[offset:offset + limit]]}


# ---------------------------------------------------------------- staff views of engagement (TCH-03, ADM-08)

def engagement_for(student_ids, subject_id=None, now=None):
    """Streak, XP and practice activity for some students: {student_id: {...}}. For teachers, pass the
    subject so only practice in that subject is shown. Contains no marks."""
    now = now or timezone.now()
    today, cfg = timezone.localdate(now), config()
    ids = list(student_ids)
    days = defaultdict(list)
    for uid, d in ActivityDay.objects.filter(user_id__in=ids).values_list("user_id", "day"):
        days[uid].append(d)
    xp = dict(XPEvent.objects.filter(user_id__in=ids).order_by().values_list("user_id").annotate(s=Sum("points")))
    sessions = PracticeSession.objects.filter(user_id__in=ids, status=PracticeSession.COMPLETED)
    if subject_id:
        sessions = sessions.filter(subject_id=subject_id)
    total, recent, score, count, last = Counter(), Counter(), defaultdict(float), Counter(), {}
    for uid, done, scored, n in sessions.values_list("user_id", "completed_at", "correct_score", "question_count"):
        total[uid] += 1
        recent[uid] += 1 if done and done >= now - timedelta(days=30) else 0
        if n:
            score[uid] += scored / n * 100
            count[uid] += 1
        if done and (uid not in last or done > last[uid]):
            last[uid] = done
    out = {}
    for uid in ids:
        st = rules.streak_status(days.get(uid, []), today, cfg["freezes"])
        out[uid] = {
            "current_streak": st["current"], "best_streak": st["best"],
            "active_days_last_30": sum(1 for d in days.get(uid, []) if d >= today - timedelta(days=29)),
            "total_xp": xp.get(uid, 0),
            "practice_sessions": total[uid], "practice_sessions_last_30_days": recent[uid],
            "practice_average_percent": round(score[uid] / count[uid]) if count[uid] else None,
            "last_practice_at": last.get(uid),
        }
    return out


def school_engagement(now=None):
    """ADM-08: engagement across the school (streaks, XP, practice). Numbers only, no marks."""
    now = now or timezone.now()
    today, cfg = timezone.localdate(now), config()
    base = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False)
    students = list(base.values_list("pk", "school_class_id"))
    days = defaultdict(list)
    for uid, d in ActivityDay.objects.filter(user__in=base).values_list("user_id", "day"):
        days[uid].append(d)
    xp = dict(XPEvent.objects.filter(user__in=base).order_by().values_list("user_id").annotate(s=Sum("points")))
    week_ago = today - timedelta(days=6)
    labels = {c.pk: str(c) for c in SchoolClass.objects.all()}
    per_class = defaultdict(lambda: {"students": 0, "xp": 0, "streaks": 0, "active7": 0})
    streak7 = total_streak = active7 = 0
    for uid, class_id in students:
        st = rules.streak_status(days.get(uid, []), today, cfg["freezes"])
        row = per_class[class_id]
        row["students"] += 1
        row["xp"] += xp.get(uid, 0)
        row["streaks"] += st["current"]
        total_streak += st["current"]
        streak7 += 1 if st["current"] >= 7 else 0
        if any(d >= week_ago for d in days.get(uid, [])):
            row["active7"] += 1
            active7 += 1
    by_class = [{"class": labels.get(cid, "(no class)"), "students": r["students"], "total_xp": r["xp"],
                 "average_xp": round(r["xp"] / r["students"]) if r["students"] else 0,
                 "average_current_streak": round(r["streaks"] / r["students"], 1) if r["students"] else 0,
                 "active_last_7_days": r["active7"]} for cid, r in sorted(per_class.items(), key=lambda kv: labels.get(kv[0], ""))]
    practice = (PracticeSession.objects.filter(status=PracticeSession.COMPLETED, completed_at__gte=now - timedelta(days=30))
                .order_by().values("subject__name").annotate(n=Count("id")))
    n = len(students)
    return {
        "available": True, "students": n, "active_last_7_days": active7,
        "active_rate_last_7_days": round(active7 / n * 100, 1) if n else None,
        "average_current_streak": round(total_streak / n, 1) if n else 0, "students_with_7_day_streak": streak7,
        "total_xp": sum(xp.values()), "by_class": by_class,
        "practice_sessions_last_30_days": sum(p["n"] for p in practice),
        "practice_by_subject": sorted(({"subject": p["subject__name"], "sessions": p["n"]} for p in practice),
                                      key=lambda x: -x["sessions"]),
    }
