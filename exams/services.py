"""Exam-day rules in one place. Every function takes `now` so tests can control time, and
every decision uses the SERVER clock only (BR-03)."""
import logging
import random
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from core import grading
from core.i18n import fmt_when, lang_of, t
from core.models import SchoolSettings
from core.tips import finish_tips
from . import marking
from .models import Answer, Attempt, Exam, ExamGrant, ExamQuestion, Result
from .presenters import public_question

ANSWER_GRACE_SECONDS = 5  # network latency allowance for an answer sent right at the deadline
DEFAULT_WARNINGS = [10, 5, 1]


class ExamError(Exception):
    def __init__(self, message, status=400, code="error"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


# ---------------------------------------------------------------- eligibility

def exams_for_student(student):
    q = Q(students=student)
    if student.school_class_id:
        q |= Q(classes=student.school_class_id)
    return Exam.objects.exclude(status=Exam.DRAFT).filter(q).distinct()


def eligible_students(exam):
    q = Q(pk__in=exam.students.values("pk"))
    if exam.classes.exists():
        q |= Q(school_class__in=exam.classes.all())
    return User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False).filter(q).distinct()


# ---------------------------------------------------------------- time rules

def late_entry_minutes(exam):
    return exam.late_entry_minutes if exam.late_entry_minutes is not None else SchoolSettings.load().late_entry_minutes


def release_time(attempt):
    """BR-06: results appear at (exam end, or this student's own deadline if later) + delay."""
    delay = SchoolSettings.load().result_delay_minutes
    return max(attempt.exam.end_at, attempt.deadline_at) + timedelta(minutes=delay)


def result_visible(attempt, now=None):
    now = now or timezone.now()
    return attempt.status != Attempt.IN_PROGRESS and now >= release_time(attempt)


def sync_exam(exam, now=None):
    """Advance the exam's status from the clock and auto-submit overdue attempts. Safe to call often;
    called by the scheduler command AND lazily by every request, so correctness never depends on cron."""
    now = now or timezone.now()
    if exam.status == Exam.DRAFT or not exam.start_at:
        return exam
    for a in exam.attempts.filter(status=Attempt.IN_PROGRESS, deadline_at__lte=now):
        finalize_attempt(a.pk, now, auto=True)
    if exam.status == Exam.PUBLISHED:
        return exam
    if now < exam.start_at:
        target = Exam.SCHEDULED
    elif now <= exam.end_at:
        target = Exam.LIVE
    else:
        target = Exam.CLOSED
        delay = SchoolSettings.load().result_delay_minutes
        if now >= exam.end_at + timedelta(minutes=delay) and not exam.attempts.filter(status=Attempt.IN_PROGRESS).exists():
            target = Exam.PUBLISHED
    if target != exam.status:
        exam.status = target
        exam.save(update_fields=["status"])
        if target == Exam.PUBLISHED:
            try:  # RES-02: a notification problem must never block publishing
                from notifications.services import results_ready

                results_ready(exam)
            except Exception:
                logging.getLogger(__name__).exception("results-ready notification failed for exam %s", exam.pk)
    return exam


# ---------------------------------------------------------------- marking

def compute_result(attempt):
    exam = attempt.exam
    answers = {a.exam_question_id: a for a in attempt.answers.all()}
    score = total = 0.0
    topics, touched = {}, []
    for eq in exam.questions.all():
        if eq.voided:  # EXM-08: a voided question counts for nobody
            continue
        p = eq.payload
        total += p["marks"]
        a = answers.get(eq.pk)
        got = 0.0
        if a and not a.skipped:
            got = marking.marks_for(
                p, a.response, partial=exam.partial_marks, negative=exam.negative_marking,
                negative_fraction=exam.negative_fraction,
            )
        if a:
            a.marks_awarded = got
            touched.append(a)
        score += got
        t = topics.setdefault(p.get("topic") or "General", [0.0, 0.0])
        t[0] += max(got, 0.0)
        t[1] += p["marks"]
    Answer.objects.bulk_update(touched, ["marks_awarded"])

    score, total = max(0.0, round(score, 2)), round(total, 2)
    percent = round(score / total * 100, 2) if total else 0.0
    existing = Result.objects.filter(attempt=attempt).first()
    scale = existing.scale_snapshot if existing else SchoolSettings.load().grade_scale  # GRD-04
    g = grading.grade_for(percent, scale)
    end = attempt.submitted_at or attempt.deadline_at
    result, _ = Result.objects.update_or_create(
        attempt=attempt,
        defaults=dict(
            exam=exam, student=attempt.student, score=score, total=total, percent=percent,
            grade=g["grade"], points=g["points"], passed=percent >= exam.pass_mark_percent,
            scale_snapshot=scale, time_taken_seconds=max(0, int((end - attempt.started_at).total_seconds())),
            topic_stats={k: [round(v[0], 2), round(v[1], 2)] for k, v in topics.items()},
        ),
    )
    return result


@transaction.atomic
def finalize_attempt(attempt_id, now=None, auto=False):
    """Submit + mark. Idempotent: a second call does nothing."""
    now = now or timezone.now()
    attempt = Attempt.objects.select_for_update().select_related("exam", "student").get(pk=attempt_id)
    if attempt.status != Attempt.IN_PROGRESS:
        return attempt
    attempt.submitted_at = min(now, attempt.deadline_at) if auto else now
    attempt.status = Attempt.AUTO_SUBMITTED if auto else Attempt.SUBMITTED
    attempt.save(update_fields=["submitted_at", "status"])
    compute_result(attempt)  # marked now, hidden until release_time (RES-01)
    return attempt


def recompute_exam_results(exam):
    for a in exam.attempts.exclude(status=Attempt.IN_PROGRESS).select_related("exam", "student"):
        compute_result(a)


# ---------------------------------------------------------------- starting

def start_attempt(exam, student, now=None):
    now = now or timezone.now()
    sync_exam(exam, now)
    exam.refresh_from_db()
    if exam.status == Exam.DRAFT or not exam.start_at:
        raise ExamError("This exam is not open.", 404, "not_open")

    last = Attempt.objects.filter(exam=exam, student=student).order_by("-attempt_no").first()
    if last and last.status == Attempt.IN_PROGRESS:
        return last  # resume (EDAY-06); an overdue one was already auto-submitted by sync_exam

    retake = None
    if last:
        retake = ExamGrant.objects.filter(exam=exam, student=student, kind=ExamGrant.RETAKE, used=False).order_by("created_at").first()
        if not retake:
            raise ExamError("You have already taken this exam. Only an administrator can allow a retake.", 409, "already_taken")
    else:
        if now < exam.start_at:
            raise ExamError("This exam has not started yet.", 403, "too_early")
        if now > exam.start_at + timedelta(minutes=late_entry_minutes(exam)):
            raise ExamError("The late-entry period is over, so you can no longer start. Please contact your teacher.", 403, "too_late")

    eqs = list(exam.questions.filter(voided=False))
    if not eqs:
        raise ExamError("This exam has no questions yet.", 409, "empty")

    base = now + timedelta(minutes=exam.duration_minutes)
    if not retake:
        base = min(base, exam.end_at)  # a late starter loses time; none is added (EXM-04)
    extra = list(ExamGrant.objects.filter(exam=exam, student=student, kind=ExamGrant.EXTRA_TIME, used=False))
    deadline = base + timedelta(minutes=sum(g.extra_minutes for g in extra))

    seed = random.SystemRandom().randrange(1, 2**31)
    order = [eq.pk for eq in eqs]
    if exam.shuffle_questions:
        random.Random(seed).shuffle(order)
    try:
        with transaction.atomic():
            attempt = Attempt.objects.create(
                exam=exam, student=student, attempt_no=(last.attempt_no + 1 if last else 1),
                started_at=now, deadline_at=deadline, order=order, seed=seed,
            )
    except IntegrityError:  # double tap on START: return the attempt that won
        return Attempt.objects.filter(exam=exam, student=student).order_by("-attempt_no").first()
    for g in extra + ([retake] if retake else []):
        g.used = True
        g.save(update_fields=["used"])
    return attempt


# ---------------------------------------------------------------- taking

def attempt_state(attempt, now=None):
    now = now or timezone.now()
    if attempt.status == Attempt.IN_PROGRESS and now >= attempt.deadline_at:
        attempt = finalize_attempt(attempt.pk, now, auto=True)
    exam = attempt.exam
    state = {
        "attempt_id": attempt.pk, "exam_id": exam.pk, "title": exam.title, "server_time": now,
        "deadline_at": attempt.deadline_at, "total_questions": len(attempt.order),
        "warnings": exam.time_warnings or DEFAULT_WARNINGS, "status": attempt.status,
    }
    if attempt.status != Attempt.IN_PROGRESS:
        lang = lang_of(attempt.student)  # English or Swahili, as the student chose (ACC-08)
        over = attempt.status == Attempt.AUTO_SUBMITTED
        results_at = release_time(attempt)
        state.update(
            finished=True, time_over=over, results_at=results_at,
            message=t("exam.done.timeover" if over else "exam.done.ok", lang),
            results_note=t("exam.results_note", lang, when=fmt_when(timezone.localtime(results_at), lang)),
            tips=finish_tips(exam.subject.name, lang, attempt.pk),  # EDAY-09: rotating, subject-specific, motivational
        )
        return state
    idx = attempt.current_index
    if idx >= len(attempt.order):
        return attempt_state(finalize_attempt(attempt.pk, now), now)
    from proctoring import services as proctoring  # local import: proctoring imports exams.models
    reason = proctoring.lock_reason(exam.pk, attempt.student_id)  # close | leaves | manual: screen locked until an admin unlocks
    state["locked"], state["lock_reason"] = reason is not None, reason or ""
    state.update(
        finished=False, remaining_seconds=max(0, int((attempt.deadline_at - now).total_seconds())),
        index=idx + 1, can_skip=exam.allow_skip,
    )
    if reason is not None:
        # SECURITY: a locked student must not be able to read the question in the network tab / devtools. The text is
        # sent again by the next GET once an administrator unlocks her.
        state["question"] = None
        return state
    eq = ExamQuestion.objects.get(pk=attempt.order[idx], exam=exam)
    state["question"] = public_question(eq, attempt.seed, exam.shuffle_options)
    return state


@transaction.atomic
def submit_answer(attempt_id, student, question_id, response, skip=False, now=None):
    now = now or timezone.now()
    attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id, student=student)
    if attempt.status != Attempt.IN_PROGRESS:
        raise ExamError("This exam has already been submitted.", 409, "submitted")
    if now >= attempt.deadline_at + timedelta(seconds=ANSWER_GRACE_SECONDS):
        raise ExamError("Time is over.", 409, "time_over")
    idx = attempt.current_index
    if idx >= len(attempt.order):
        return attempt
    from proctoring import services as proctoring
    reason = proctoring.lock_reason(attempt.exam_id, student.pk)
    if reason:  # the clock keeps running; the app keeps the answer and re-sends after the unlock
        why = {"leaves": "you left the exam screen too many times", "manual": "an administrator locked it"}.get(reason, "you are sitting too close to another student")
        raise ExamError(f"Your exam is locked because {why}. Wait for the invigilator to unlock it.", 423, "locked")
    if question_id != attempt.order[idx]:
        if question_id in attempt.order[:idx]:
            return attempt  # a repeated send from the offline queue: already saved, ignore (BR-05)
        raise ExamError("That is not the current question.", 409, "out_of_order")
    if skip:
        if not attempt.exam.allow_skip:
            raise ExamError("Skipping is not allowed in this exam.", 400, "no_skip")
        Answer.objects.create(attempt=attempt, exam_question_id=question_id, skipped=True)
    else:
        if response in (None, "", [], {}):
            raise ExamError("Please choose or write an answer first.", 400, "empty_answer")
        if len(str(response)) > 5000:
            raise ExamError("That answer is too long.", 400, "too_long")
        Answer.objects.create(attempt=attempt, exam_question_id=question_id, response=response)
    attempt.current_index = idx + 1
    attempt.save(update_fields=["current_index"])
    if attempt.current_index >= len(attempt.order):
        finalize_attempt(attempt.pk, now)
    return attempt
