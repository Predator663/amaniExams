import logging
import random
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from academics.models import TeacherAssignment
from accounts.models import User
from accounts.permissions import IsAdminRole, IsStaffUser, IsStudent
from core.models import SchoolSettings, audit
from core.views import online_ids
from questions.models import Question
from . import services
from .models import Answer, Attempt, AttemptEvent, Exam, ExamGrant, ExamQuestion, Result
from .services import ExamError


def _err(e):
    return Response({"detail": e.message, "code": e.code}, status=e.status)


# =============================================================== student side
# Every query below is filtered by request.user. A student can never reach another
# student's attempt or result, whatever id she types (BR-07, RES-08).

def _exam_card(exam, student, now):
    last = exam.attempts.filter(student=student).order_by("-attempt_no").first()
    if last and last.status == Attempt.IN_PROGRESS:
        state = "in_progress"
    elif last:
        state = "done"
    elif now < exam.start_at:
        state = "upcoming"
    elif now <= exam.start_at + timedelta(minutes=services.late_entry_minutes(exam)):
        state = "open"
    else:
        state = "missed"
    return {
        "id": exam.pk, "title": exam.title, "subject": exam.subject.name, "start_at": exam.start_at,
        "end_at": exam.end_at, "duration_minutes": exam.duration_minutes,
        "question_count": exam.questions.filter(voided=False).count(), "total_marks": exam.total_marks,
        "rules_text": exam.rules_text, "state": state,
        "attempt_id": last.pk if last else None, "server_time": now,
    }


@api_view(["GET"])
@permission_classes([IsStudent])
def student_exams(request):
    """HOME-01/02: upcoming (and today's) exams for the banner, ordered by date."""
    now = timezone.now()
    exams = list(services.exams_for_student(request.user).select_related("subject"))
    for e in exams:
        if e.status != Exam.PUBLISHED:
            services.sync_exam(e, now)
    exams = [e for e in exams if e.end_at and e.end_at > now - timedelta(days=1)]
    exams.sort(key=lambda e: e.start_at)
    return Response([_exam_card(e, request.user, now) for e in exams])


@api_view(["POST"])
@permission_classes([IsStudent])
def student_start(request, exam_id):
    exam = get_object_or_404(services.exams_for_student(request.user), pk=exam_id)
    if not request.data.get("agree_rules"):  # EDAY-02
        return Response({"detail": "Please tick that you have read and agree to the rules.", "code": "rules"}, status=400)
    try:
        attempt = services.start_attempt(exam, request.user)
    except ExamError as e:
        return _err(e)
    return Response(services.attempt_state(attempt), status=201)


def _own_attempt(request, attempt_id):
    return get_object_or_404(Attempt.objects.select_related("exam", "student"), pk=attempt_id, student=request.user)


@api_view(["GET"])
@permission_classes([IsStudent])
def attempt_current(request, attempt_id):
    """Resume point after refresh / reconnect / phone restart (EDAY-06). Time comes from the server."""
    return Response(services.attempt_state(_own_attempt(request, attempt_id)))


@api_view(["POST"])
@permission_classes([IsStudent])
def attempt_answer(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    try:
        services.submit_answer(
            attempt.pk, request.user, request.data.get("question_id"), request.data.get("response"),
            skip=bool(request.data.get("skip")),
        )
    except ExamError as e:
        if e.code == "time_over":
            return Response({**services.attempt_state(attempt), "detail": e.message, "code": e.code}, status=409)
        return _err(e)
    return Response(services.attempt_state(Attempt.objects.select_related("exam").get(pk=attempt.pk)))


@api_view(["POST"])
@permission_classes([IsStudent])
def attempt_finish(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    services.finalize_attempt(attempt.pk)  # idempotent
    return Response(services.attempt_state(Attempt.objects.select_related("exam").get(pk=attempt.pk)))


@api_view(["POST"])
@permission_classes([IsStudent])
def attempt_event(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    kind = request.data.get("kind")
    if attempt.status == Attempt.IN_PROGRESS and kind in ("left_screen", "returned"):
        AttemptEvent.objects.create(attempt=attempt, kind=kind)
    return Response({"ok": True})


def _visible_result_or_404(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    services.sync_exam(attempt.exam)
    if not services.result_visible(attempt):
        # Same answer as "does not exist": nothing leaks before publish time (BR-05, BR-06).
        return None, Response({"detail": "Your results are not ready yet.", "code": "not_ready",
                               "results_at": services.release_time(attempt)}, status=404)
    return attempt, None


def _result_payload(attempt, result):
    s = SchoolSettings.load()
    others = Result.objects.filter(exam=attempt.exam)
    out = {
        "attempt_id": attempt.pk, "exam": attempt.exam.title, "subject": attempt.exam.subject.name,
        "score": result.score, "total": result.total, "percent": result.percent, "grade": result.grade,
        "points": result.points, "passed": result.passed, "time_taken_seconds": result.time_taken_seconds,
        "class_average_percent": round(others.aggregate(a=Avg("percent"))["a"] or 0, 1),  # anonymous (RES-03)
        "topics": [{"topic": t, "earned": v[0], "possible": v[1],
                    "percent": round(v[0] / v[1] * 100, 1) if v[1] else 0} for t, v in result.topic_stats.items()],
    }
    out["revise"] = [t["topic"] for t in sorted(out["topics"], key=lambda t: t["percent"]) if t["percent"] < 60][:3]  # RES-04
    if s.show_class_position and attempt.student.school_class_id:
        mine = others.filter(student__school_class_id=attempt.student.school_class_id)
        out["class_position"] = mine.filter(score__gt=result.score).count() + 1
        out["class_size"] = mine.count()
    return out


@api_view(["GET"])
@permission_classes([IsStudent])
def my_results(request):
    now = timezone.now()
    rows = []
    for r in Result.objects.filter(student=request.user).select_related("attempt__exam__subject"):
        if services.result_visible(r.attempt, now):
            rows.append({"attempt_id": r.attempt_id, "exam": r.exam.title, "subject": r.exam.subject.name,
                         "percent": r.percent, "grade": r.grade, "date": r.exam.start_at})
    return Response(sorted(rows, key=lambda x: x["date"], reverse=True))


@api_view(["GET"])
@permission_classes([IsStudent])
def result_detail(request, attempt_id):
    attempt, err = _visible_result_or_404(request, attempt_id)
    if err:
        return err
    data = _result_payload(attempt, attempt.result)
    data["rewards"] = _rewards_for(attempt)  # RES-03: XP and badges earned from this exam
    return Response(data)


def _rewards_for(attempt):
    """Hand out any rewards that are due for this exam (once only) and report them. A problem in the
    gamification code must never stop a student seeing her result, so errors are logged and ignored."""
    try:
        from gamification import services as gamification

        gamification.reward_attempt(attempt)
        return gamification.rewards_for_attempt(attempt)
    except Exception:
        logging.getLogger(__name__).exception("rewards failed for attempt %s", attempt.pk)
        return None


@api_view(["GET"])
@permission_classes([IsStudent])
def result_review(request, attempt_id):
    """RES-05: read-only review, only after publish. Correct answers appear here and nowhere earlier."""
    attempt, err = _visible_result_or_404(request, attempt_id)
    if err:
        return err
    answers = {a.exam_question_id: a for a in attempt.answers.all()}
    out = []
    for eq in attempt.exam.questions.all():
        a, p = answers.get(eq.pk), eq.payload
        out.append({
            "number": eq.position, "voided": eq.voided, "type": p["qtype"], "prompt": p["prompt"], "content": p["content"],
            "marks": p["marks"], "your_response": a.response if a else None, "skipped": bool(a and a.skipped),
            "marks_awarded": a.marks_awarded if a else 0, "correct_answer": p["answer"], "explanation": p.get("explanation", ""),
        })
    return Response(out)


# =============================================================== staff side

class ExamSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    total_marks = serializers.ReadOnlyField()

    class Meta:
        model = Exam
        fields = ["id", "title", "subject", "term", "classes", "students", "start_at", "end_at", "duration_minutes",
                  "pass_mark_percent", "rules_text", "shuffle_questions", "shuffle_options", "allow_skip",
                  "late_entry_minutes", "time_warnings", "partial_marks", "negative_marking", "negative_fraction",
                  "status", "question_count", "total_marks"]
        read_only_fields = ["status"]

    def get_question_count(self, o):
        return o.questions.filter(voided=False).count()

    def validate(self, d):
        s, e = d.get("start_at", getattr(self.instance, "start_at", None)), d.get("end_at", getattr(self.instance, "end_at", None))
        dur = d.get("duration_minutes", getattr(self.instance, "duration_minutes", 60))
        if s and e:
            if e <= s:
                raise serializers.ValidationError({"end_at": "The end time must be after the start time."})
            if dur > (e - s).total_seconds() / 60:
                raise serializers.ValidationError({"duration_minutes": "The duration is longer than the exam window."})
        return d


ADMIN_ONLY_FIELDS = {"term", "start_at", "end_at", "classes", "students", "pass_mark_percent", "rules_text",
                     "late_entry_minutes", "time_warnings"}  # EXM-02: admins schedule


def _teaches(user, subject_id):
    return user.is_admin_role or TeacherAssignment.objects.filter(teacher=user, subject_id=subject_id).exists()


class ExamViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffUser]
    serializer_class = ExamSerializer

    def get_queryset(self):
        qs = Exam.objects.all()
        u = self.request.user
        if not u.is_admin_role:
            qs = qs.filter(subject__in=TeacherAssignment.objects.filter(teacher=u).values("subject"))
        return qs

    def _editable(self, exam):
        services.sync_exam(exam)
        if exam.status in (Exam.LIVE, Exam.CLOSED, Exam.PUBLISHED):
            raise PermissionDenied("A live or finished exam cannot be edited.")  # EXM-07
        if exam.status != Exam.DRAFT and not self.request.user.is_admin_role:
            raise PermissionDenied("Only an administrator can change a scheduled exam.")

    def perform_create(self, serializer):
        u = self.request.user
        subject = serializer.validated_data["subject"]
        if not _teaches(u, subject.pk):
            raise PermissionDenied("You can only create exams for your assigned subjects.")
        data = dict(serializer.validated_data)
        if not u.is_admin_role:
            for f in ADMIN_ONLY_FIELDS:
                data.pop(f, None)
        classes, students = data.pop("classes", None), data.pop("students", None)
        exam = Exam.objects.create(created_by=u, **data)
        if classes is not None:
            exam.classes.set(classes)
        if students is not None:
            exam.students.set(students)
        serializer.instance = exam

    def perform_update(self, serializer):
        exam = serializer.instance
        self._editable(exam)
        if not _teaches(self.request.user, exam.subject_id):
            raise PermissionDenied()
        if not self.request.user.is_admin_role:
            for f in ADMIN_ONLY_FIELDS:
                serializer.validated_data.pop(f, None)
        serializer.save()
        audit(self.request.user, "exam.edit", exam.pk)

    def perform_destroy(self, exam):
        if exam.status != Exam.DRAFT:
            raise PermissionDenied("Only a draft exam can be deleted.")
        audit(self.request.user, "exam.delete", exam.pk)
        exam.delete()

    @action(detail=True, methods=["get"], url_path="questions")
    def paper_questions(self, request, pk=None):
        """The exam's own copy of its questions (QB-11), for staff: needed to void a faulty question (EXM-08).
        Correct answers are not included here; only students never see them before results, and staff wrote them."""
        exam = self.get_object()
        return Response([
            {"id": q.pk, "source": q.source_id, "position": q.position, "voided": q.voided, "void_reason": q.void_reason,
             "prompt": q.payload.get("prompt", ""), "qtype": q.payload.get("qtype"), "marks": q.payload.get("marks"),
             "topic": q.payload.get("topic", ""), "difficulty": q.payload.get("difficulty", "")}
            for q in exam.questions.order_by("position")])

    # ---- paper: pick questions and/or random rules (EXM-01) --------------------------------
    @action(detail=True, methods=["post"])
    def paper(self, request, pk=None):
        exam = self.get_object()
        self._editable(exam)
        if not _teaches(request.user, exam.subject_id):
            raise PermissionDenied()
        picked = list(Question.objects.filter(pk__in=request.data.get("question_ids", []), subject=exam.subject))
        chosen = {q.pk: q for q in picked}
        rng = random.SystemRandom()
        for rule in request.data.get("rules", []):
            pool = Question.objects.filter(subject=exam.subject, status=Question.APPROVED).exclude(pk__in=chosen)
            for f in ("topic", "difficulty", "form_level"):
                if rule.get(f):
                    pool = pool.filter(**{f: rule[f]})
            pool, n = list(pool), int(rule.get("count", 0))
            if len(pool) < n:
                raise ValidationError({"rules": f"Only {len(pool)} approved question(s) match {rule}; {n} requested."})
            for q in rng.sample(pool, n):
                chosen[q.pk] = q
        not_ok = [q.pk for q in chosen.values() if q.status != Question.APPROVED]
        if not_ok:
            raise ValidationError({"question_ids": f"Only approved questions can be used. Not approved: {not_ok}"})
        if not chosen:
            raise ValidationError({"detail": "Choose at least one question."})
        exam.questions.all().delete()
        for pos, q in enumerate(chosen.values(), start=1):  # a private copy for this exam (QB-11)
            ExamQuestion.objects.create(exam=exam, position=pos, source=q, payload={
                "qtype": q.qtype, "prompt": q.prompt, "content": q.content, "answer": q.answer, "marks": q.marks,
                "explanation": q.explanation, "topic": q.topic, "subtopic": q.subtopic, "difficulty": q.difficulty,
                "language": q.language, "source_version": q.version,
            })
        return Response({"questions": len(chosen), "total_marks": exam.total_marks})

    # ---- admin actions ----------------------------------------------------------------------
    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def schedule(self, request, pk=None):
        exam = self.get_object()
        self._editable(exam)
        problems = []
        if not (exam.start_at and exam.end_at):
            problems.append("Set the date, start time and end time.")
        if not exam.questions.exists():
            problems.append("Add questions to the paper.")
        if not exam.classes.exists() and not exam.students.exists():
            problems.append("Choose which classes or students sit this exam.")
        if exam.end_at and exam.end_at <= timezone.now():
            problems.append("The end time is in the past.")
        if problems:
            raise ValidationError({"detail": problems})
        exam.status = Exam.SCHEDULED
        exam.save(update_fields=["status"])
        audit(request.user, "exam.schedule", exam.pk)
        return Response({"status": exam.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def unschedule(self, request, pk=None):
        """Take a scheduled exam back to Draft (only before it starts)."""
        exam = self.get_object()
        services.sync_exam(exam)
        exam.refresh_from_db()
        if exam.status != Exam.SCHEDULED:
            raise ValidationError({"detail": "Only an exam that has not started yet can be unscheduled."})
        exam.status = Exam.DRAFT
        exam.save(update_fields=["status"])
        audit(request.user, "exam.unschedule", exam.pk)
        return Response({"status": exam.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def close(self, request, pk=None):
        """Emergency close of a live exam. Everyone still writing is submitted and marked now;
        results still publish at the normal time (end + delay). Needs confirm=true and a reason."""
        exam = self.get_object()
        services.sync_exam(exam)
        exam.refresh_from_db()
        reason = (request.data.get("reason") or "").strip()
        if exam.status != Exam.LIVE:
            raise ValidationError({"detail": "Only a live exam can be closed early."})
        if request.data.get("confirm") is not True or not reason:
            raise ValidationError({"detail": "Send confirm=true and a reason to close the exam now."})
        now = timezone.now()
        exam.end_at = now
        exam.save(update_fields=["end_at"])
        for a in exam.attempts.filter(status=Attempt.IN_PROGRESS):
            services.finalize_attempt(a.pk, now, auto=True)
        services.sync_exam(exam, now)
        audit(request.user, "exam.close", exam.pk, reason=reason)
        return Response({"status": Exam.objects.get(pk=exam.pk).status})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole], url_path="void-question")
    def void_question(self, request, pk=None):
        """EXM-08: void a faulty question after the exam; every affected result is recalculated."""
        exam = self.get_object()
        services.sync_exam(exam)
        if exam.status not in (Exam.CLOSED, Exam.PUBLISHED):
            raise ValidationError({"detail": "A question can be voided only after the exam has closed."})
        eq = get_object_or_404(exam.questions, pk=request.data.get("exam_question_id"))
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise ValidationError({"reason": "Please give a reason."})
        eq.voided, eq.void_reason = True, reason[:300]
        eq.save(update_fields=["voided", "void_reason"])
        services.recompute_exam_results(exam)
        audit(request.user, "question.void", eq.pk, exam=exam.pk, reason=reason)
        return Response({"ok": True, "total_marks": exam.total_marks})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def grant(self, request, pk=None):
        """EXM-09 / BR-04: extra time or a retake for ONE student. Always audited with a reason."""
        exam = self.get_object()
        student = get_object_or_404(services.eligible_students(exam), pk=request.data.get("student_id"))
        kind, reason = request.data.get("kind"), (request.data.get("reason") or "").strip()
        if kind not in (ExamGrant.EXTRA_TIME, ExamGrant.RETAKE) or not reason:
            raise ValidationError({"detail": "Choose extra_time or retake, and give a reason."})
        minutes = int(request.data.get("extra_minutes", 0)) if kind == ExamGrant.EXTRA_TIME else 0
        if kind == ExamGrant.EXTRA_TIME and not 1 <= minutes <= 240:
            raise ValidationError({"extra_minutes": "Extra time must be between 1 and 240 minutes."})
        grant = ExamGrant.objects.create(exam=exam, student=student, kind=kind, extra_minutes=minutes,
                                         reason=reason[:300], granted_by=request.user)
        live = exam.attempts.filter(student=student, status=Attempt.IN_PROGRESS).first()
        if kind == ExamGrant.EXTRA_TIME and live:  # power cut mid-exam: extend right now
            live.deadline_at += timedelta(minutes=minutes)
            live.save(update_fields=["deadline_at"])
            grant.used = True
            grant.save(update_fields=["used"])
        audit(request.user, f"exam.grant.{kind}", exam.pk, student=student.pk, minutes=minutes, reason=reason)
        return Response({"ok": True})

    @action(detail=True, methods=["get"])
    def monitor(self, request, pk=None):
        """ADM-06 / TCH-08: admins get names; teachers get numbers only."""
        exam = self.get_object()
        services.sync_exam(exam)
        eligible = services.eligible_students(exam)
        attempts = {a.student_id: a for a in exam.attempts.select_related("student").order_by("attempt_no")}
        in_progress = [a for a in attempts.values() if a.status == Attempt.IN_PROGRESS]
        data = {
            "status": exam.status, "eligible": eligible.count(),
            "not_started": eligible.count() - len(attempts), "in_progress": len(in_progress),
            "submitted": len(attempts) - len(in_progress),
        }
        if request.user.is_admin_role:
            flags = dict(AttemptEvent.objects.filter(attempt__exam=exam, kind="left_screen")
                         .values_list("attempt__student_id").annotate(n=Count("id")))
            data["not_started_students"] = [
                {"id": s.pk, "name": f"{s.first_name} {s.last_name}", "class": str(s.school_class), "index": s.index_number}
                for s in eligible.exclude(pk__in=attempts.keys()).select_related("school_class")]
            data["screen_leave_flags"] = [  # information only (EDAY-11)
                {"student_id": sid, "times_left_screen": n} for sid, n in flags.items()]
            online = online_ids()  # students send a heartbeat to /api/presence/ every ~30 s
            data["online_now"] = sum(1 for a in in_progress if a.student_id in online)
            data["connection_problems"] = [  # writing, but no heartbeat for 90 s (ADM-06)
                {"id": a.student_id, "name": f"{a.student.first_name} {a.student.last_name}"}
                for a in in_progress if a.student_id not in online]
            # Per-student view for the live monitor screen: how far she is, time left, online, left the screen.
            answered = dict(Answer.objects.filter(attempt__in=in_progress).values_list("attempt_id").annotate(n=Count("id")))
            now = timezone.now()
            klass = {s.pk: str(s.school_class) for s in eligible.select_related("school_class")}
            data["total_questions"] = exam.questions.count()
            data["in_progress_students"] = sorted((
                {"id": a.student_id, "name": f"{a.student.first_name} {a.student.last_name}", "class": klass.get(a.student_id, ""), "index": a.student.index_number,
                 "answered": answered.get(a.pk, 0), "seconds_left": max(0, int((a.deadline_at - now).total_seconds())),
                 "online": a.student_id in online, "left_screen": flags.get(a.student_id, 0)}
                for a in in_progress), key=lambda r: r["name"])
            data["submitted_students"] = sorted((
                {"id": a.student_id, "name": f"{a.student.first_name} {a.student.last_name}", "class": klass.get(a.student_id, ""), "index": a.student.index_number,
                 "left_screen": flags.get(a.student_id, 0)}
                for a in attempts.values() if a.status != Attempt.IN_PROGRESS), key=lambda r: r["name"])
            data["server_time"] = now.isoformat()
        return Response(data)
