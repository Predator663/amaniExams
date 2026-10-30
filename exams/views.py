import logging
import random
from datetime import timedelta

from django.db.models import Avg, Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from academics.models import TeacherAssignment
from accounts.models import User
from accounts.permissions import IsAdminRole, IsStaffUser, IsStudent
from core.models import SchoolSettings, audit
from core.pagination import paginate
from core.views import online_ids
from questions.models import Question
from questions.views import QuestionSerializer
from proctoring import services as proctoring
from . import services
from .sections import letters, qtype_rank
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
    fix = None
    if proctoring.enabled():
        # Terms + Privacy policy (which cover location monitoring) must be accepted for every exam, and the phone must
        # prove that location services are on by sending a position.
        if not request.data.get("accept_legal"):
            return Response({"detail": "Please accept the Terms of use and the Privacy policy before you begin.", "code": "legal"}, status=400)
        fix = proctoring.parse_fix(request.data.get("location") or {})
        if not fix:
            return Response({"detail": "Turn on location services (GPS), allow location for this app, then try again. "
                                       "Your location is needed during the exam.", "code": "location_required"}, status=400)
    try:
        attempt = services.start_attempt(exam, request.user)
    except ExamError as e:
        return _err(e)
    if proctoring.enabled():
        proctoring.record_acceptance(request.user, exam)
        proctoring.ingest(attempt, fix, speed=None, heading=None, sensors=request.data.get("sensors"), **proctoring.client_info(request))
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
        if e.code == "locked":
            return Response({"detail": e.message, "code": e.code}, status=423)
        return _err(e)
    return Response(services.attempt_state(Attempt.objects.select_related("exam").get(pk=attempt.pk)))


@api_view(["POST"])
@permission_classes([IsStudent])
def attempt_finish(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    services.finalize_attempt(attempt.pk)  # idempotent
    return Response(services.attempt_state(Attempt.objects.select_related("exam").get(pk=attempt.pk)))


class AttemptEventThrottle(UserRateThrottle):
    """SECURITY: the leave-screen endpoint writes a row per call. A real student leaves the screen a handful of times;
    this stops a script from filling the table. The rate is set here so no settings change is needed."""
    scope = "attempt_event"
    rate = "30/min"


@api_view(["POST"])
@permission_classes([IsStudent])
@throttle_classes([AttemptEventThrottle])
def attempt_event(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    kind = request.data.get("kind")
    if attempt.status != Attempt.IN_PROGRESS or kind not in ("left_screen", "returned"):
        return Response({"ok": True})
    AttemptEvent.objects.create(attempt=attempt, kind=kind)
    if kind == "left_screen":
        locked_now, status = proctoring.note_leave(attempt.pk)  # one more exit; locks her when it goes over the limit
    else:
        locked_now, status = False, proctoring.leave_status(attempt)
    reason = proctoring.lock_reason(attempt.exam_id, request.user.pk)
    return Response({"ok": True, "locked": reason is not None, "lock_reason": reason or "", "locked_now": locked_now,
                     "left": status["used"], "limit": status["limit"], "auto_lock": status["enabled"]})


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
    rows.sort(key=lambda x: x["date"], reverse=True)
    return Response(paginate(request, rows) or rows)


@api_view(["GET"])
@permission_classes([IsStudent])
def my_results_pending(request):
    """Exams I have submitted whose results are not out yet, with the time they will be. Running sync_exam
    here publishes anything that is due (and sends the results-ready notification) without waiting for cron."""
    now = timezone.now()
    rows = []
    for a in Attempt.objects.filter(student=request.user).exclude(status=Attempt.IN_PROGRESS).select_related("exam__subject"):
        services.sync_exam(a.exam, now)
        if not services.result_visible(a, now):
            rows.append({"attempt_id": a.pk, "exam": a.exam.title, "subject": a.exam.subject.name,
                         "results_at": services.release_time(a), "server_time": now})
    return Response(sorted(rows, key=lambda r: r["results_at"]))


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

def _person(u):
    return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else ""


class ExamSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    total_marks = serializers.ReadOnlyField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    submitted_by_name = serializers.SerializerMethodField()
    awaiting_scheduling = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ["id", "title", "subject", "term", "classes", "students", "start_at", "end_at", "duration_minutes",
                  "pass_mark_percent", "rules_text", "shuffle_questions", "shuffle_options", "allow_skip",
                  "late_entry_minutes", "time_warnings", "partial_marks", "negative_marking", "negative_fraction",
                  "status", "question_count", "total_marks", "subject_name", "class_names", "created_at", "created_by",
                  "created_by_name", "submitted_at", "submitted_by", "submitted_by_name", "awaiting_scheduling"]
        read_only_fields = ["status", "created_at", "created_by", "submitted_at", "submitted_by"]

    def get_question_count(self, o):
        return o.questions.filter(voided=False).count()

    def get_class_names(self, o):
        return [str(c) for c in o.classes.all()]

    def get_created_by_name(self, o):
        return _person(o.created_by)

    def get_submitted_by_name(self, o):
        return _person(o.submitted_by)

    def get_awaiting_scheduling(self, o):
        """A teacher's draft that an administrator has not scheduled yet."""
        return o.status == Exam.DRAFT and o.submitted_at is not None

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
        qs = Exam.objects.select_related("subject", "created_by", "submitted_by").prefetch_related("classes")
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
        rows = list(exam.questions.order_by("position"))
        sec = letters(r.payload.get("qtype") for r in rows)
        return Response([
            {"id": q.pk, "source": q.source_id, "position": q.position, "voided": q.voided, "void_reason": q.void_reason,
             "prompt": q.payload.get("prompt", ""), "qtype": q.payload.get("qtype"), "marks": q.payload.get("marks"),
             "topic": q.payload.get("topic", ""), "difficulty": q.payload.get("difficulty", ""),
             "section": sec.get(q.payload.get("qtype"), "")}
            for q in rows])

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """A teacher hands the saved paper to the administrators. Records who and when (shown in the admin console).
        Submitting again after changes simply updates the time."""
        exam = self.get_object()
        services.sync_exam(exam)
        exam.refresh_from_db()
        if not _teaches(request.user, exam.subject_id):
            raise PermissionDenied()
        if exam.status != Exam.DRAFT:
            raise ValidationError({"detail": "Only a draft can be submitted. This exam is already " + exam.status + "."})
        if not exam.questions.filter(voided=False).exists():
            raise ValidationError({"detail": "Save the paper with at least one question before submitting."})
        exam.submitted_at, exam.submitted_by = timezone.now(), request.user
        exam.save(update_fields=["submitted_at", "submitted_by"])
        audit(request.user, "exam.submit", exam.pk, title=exam.title)
        return Response({"submitted_at": exam.submitted_at, "submitted_by_name": _person(request.user)})

    # ---- the question picker: approved questions of this exam's subject, paged and filtered ----
    @action(detail=True, methods=["get"])
    def bank(self, request, pk=None):
        exam = self.get_object()
        p = request.query_params
        base = Question.objects.filter(subject=exam.subject, status=Question.APPROVED)
        topics = sorted(set(base.exclude(topic="").values_list("topic", flat=True)))
        qs = base.annotate(used_count=Count("examquestion", filter=~Q(examquestion__exam=exam), distinct=True),
                           last_used=Max("examquestion__exam__start_at", filter=~Q(examquestion__exam=exam)))
        for f in ("topic", "difficulty", "qtype", "form_level"):
            if p.get(f):
                qs = qs.filter(**{f: p[f]})
        if p.get("q"):
            qs = qs.filter(Q(prompt__icontains=p["q"]) | Q(topic__icontains=p["q"]) | Q(subtopic__icontains=p["q"]))
        if p.get("usage") == "used":
            qs = qs.filter(used_count__gt=0)
        elif p.get("usage") == "unused":
            qs = qs.filter(used_count=0)
        qs = qs.order_by({"oldest": "created_at", "topic": "topic"}.get(p.get("sort"), "-created_at"), "-id")
        try:
            size = min(max(int(p.get("page_size", 10)), 1), 50)
            page = max(int(p.get("page", 1)), 1)
        except ValueError:
            raise ValidationError({"detail": "page and page_size must be numbers."})
        count = qs.count()
        pages = max(1, -(-count // size))
        page = min(page, pages)
        rows = list(qs[(page - 1) * size: page * size])
        data = QuestionSerializer(rows, many=True).data
        for row, q in zip(data, rows):
            row["used_count"], row["last_used"] = q.used_count, q.last_used
        return Response({"count": count, "page": page, "pages": pages, "page_size": size,
                         "topics": topics, "total_approved": base.count(), "results": data})

    @action(detail=True, methods=["post"])
    def pick(self, request, pk=None):
        """Random questions by rule (topic / difficulty / how many) for the builder to add to its selection."""
        exam = self.get_object()
        self._editable(exam)
        exclude = {int(x) for x in request.data.get("exclude", []) if str(x).isdigit()}
        rng, out = random.SystemRandom(), []
        for rule in request.data.get("rules", []):
            pool = Question.objects.filter(subject=exam.subject, status=Question.APPROVED).exclude(pk__in=exclude)
            for f in ("topic", "difficulty", "form_level"):
                if rule.get(f):
                    pool = pool.filter(**{f: rule[f]})
            pool, n = list(pool), int(rule.get("count", 0))
            if len(pool) < n:
                raise ValidationError({"rules": f"Only {len(pool)} unselected approved question(s) match {rule}; {n} requested."})
            for q in rng.sample(pool, n):
                exclude.add(q.pk)
                out.append(q)
        return Response(QuestionSerializer(out, many=True).data)

    # ---- paper: pick questions and/or random rules (EXM-01) --------------------------------
    @action(detail=True, methods=["post"])
    def paper(self, request, pk=None):
        exam = self.get_object()
        self._editable(exam)
        if not _teaches(request.user, exam.subject_id):
            raise PermissionDenied()
        ids = [int(x) for x in request.data.get("question_ids", []) if str(x).isdigit()]
        found = {q.pk: q for q in Question.objects.filter(pk__in=ids, subject=exam.subject)}
        chosen = {i: found[i] for i in ids if i in found}  # keeps the order the teacher picked
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
        # Section A, B, C ... : grouped by type, in the order they were picked inside each section.
        ordered = sorted(chosen.values(), key=lambda q: qtype_rank(q.qtype))  # sorted() is stable
        for pos, q in enumerate(ordered, start=1):  # a private copy for this exam (QB-11)
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
        """ADM-06 / TCH-08: one exam. Admins get names, parent phones and per-student detail;
        teachers get counts and index numbers only."""
        exam = self.get_object()
        services.sync_exam(exam)
        return Response(_monitor_exam(exam, request.user, timezone.now(), online_ids()))

    @action(detail=False, methods=["get"], url_path="monitor-board")
    def monitor_board(self, request):
        """Live monitor, whole school in ONE request: every exam that is live now, plus anything that
        finished or was submitted in the last 24 h (so submitted exams never vanish from the board).
        Counts come from grouped queries, not per-row lookups, so it stays light."""
        now = timezone.now()
        try:
            days = max(1, min(int(request.query_params.get("days", 1)), 400))
        except ValueError:
            days = 1
        since = now - timedelta(days=days)
        exams = list(self.get_queryset().filter(
            Q(status=Exam.LIVE) | Q(end_at__gte=since, start_at__lte=now)
            | Q(status=Exam.SCHEDULED, start_at__gt=now, start_at__lte=now + timedelta(hours=3)))
            .select_related("subject").prefetch_related("classes").distinct().order_by("-start_at")[:60])
        for e in exams:
            services.sync_exam(e, now)
        online = online_ids()
        cache = {}
        board = [_monitor_exam(e, request.user, now, online, cache) for e in exams]
        board.sort(key=lambda d: (d["status"] != Exam.LIVE, d["status"] != Exam.SCHEDULED, -d["start_at_ts"]))
        return Response({"server_time": now.isoformat(), "exams": board,
                         "totals": {"live_exams": sum(1 for d in board if d["status"] == Exam.LIVE),
                                    "writing": sum(d["in_progress"] for d in board),
                                    "submitted": sum(d["submitted"] for d in board)}})


def _ts(obj, *names):
    """First timestamp field that exists on the attempt, as ISO text (the model may name it differently)."""
    for n in names:
        v = getattr(obj, n, None)
        if v:
            return v.isoformat()
    return None


def mask_phone(phone):
    """+255712345678 -> +255•••••678 : enough to recognise a number, not enough to copy it."""
    p = str(phone or "")
    digits = sum(c.isdigit() for c in p)
    if digits <= 6:
        return "•" * len(p)
    keep_head = p[:4] if p.startswith("+") else p[:0]
    return keep_head + "•" * max(3, len(p) - len(keep_head) - 3) + p[-3:]


def _parents(students, cache=None):
    """{student_id: [{id, name, phone (MASKED), relationship}]} from the Parents page (encrypted at rest).
    SECURITY: the live monitor polls every few seconds, so it never carries a full number. An administrator taps
    "Show number", which calls proctoring reveal-phone and is written to the audit log."""
    cache = {} if cache is None else cache
    out = {}
    try:
        from guardians.models import GuardianLink
        ids = [s.pk for s in students]
        for link in GuardianLink.objects.filter(student_id__in=ids).select_related("guardian").order_by("id"):
            g = link.guardian
            if g.pk not in cache:
                cache[g.pk] = {"id": g.pk, "name": g.name, "phone": mask_phone(g.phone), "relationship": g.relationship}
            out.setdefault(link.student_id, []).append(cache[g.pk])
    except Exception:
        logging.getLogger(__name__).exception("parent lookup failed")
    return out


def _monitor_exam(exam, user, now, online, cache=None):
    """Everything the monitor shows for one exam. Fixes: submitted students are always returned
    (all attempts, not only the live ones), and the exam stays visible after it closes."""
    is_admin = user.is_admin_role
    eligible_qs = services.eligible_students(exam).select_related("school_class")
    eligible = list(eligible_qs)
    by_id = {s.pk: s for s in eligible}
    attempts = list(exam.attempts.select_related("student", "student__school_class").order_by("attempt_no"))
    latest = {}
    for a in attempts:  # latest attempt per student decides her state
        latest[a.student_id] = a
        by_id.setdefault(a.student_id, a.student)
    live = [a for a in latest.values() if a.status == Attempt.IN_PROGRESS]
    done = [a for a in latest.values() if a.status != Attempt.IN_PROGRESS]
    data = {
        "exam_id": exam.pk, "title": exam.title, "subject": exam.subject.name, "status": exam.status,
        "classes": [str(c) for c in exam.classes.all()],
        "start_at": exam.start_at.isoformat() if exam.start_at else None,
        "end_at": exam.end_at.isoformat() if exam.end_at else None,
        "start_at_ts": exam.start_at.timestamp() if exam.start_at else 0,
        "duration_minutes": exam.duration_minutes or 0,
        "eligible": len(eligible), "in_progress": len(live), "submitted": len(done),
        "not_started": max(0, len(eligible) - len(latest)),
        "total_questions": exam.questions.filter(voided=False).count(), "server_time": now.isoformat(),
    }
    if not is_admin:
        return data
    data["proximity_alerts"] = exam.proximity_alerts.filter(active=True, acknowledged_at__isnull=True).count()
    flags = dict(AttemptEvent.objects.filter(attempt__exam=exam, kind="left_screen")
                 .values_list("attempt__student_id").annotate(n=Count("id")))
    left_now = dict(AttemptEvent.objects.filter(attempt__exam=exam, attempt__status=Attempt.IN_PROGRESS, kind="left_screen")
                    .values_list("attempt_id").annotate(n=Count("id")))  # exits per running attempt (the lock counts these)
    answered = dict(Answer.objects.filter(attempt__exam=exam, skipped=False).values_list("attempt_id").annotate(n=Count("id")))  # skipped questions do not count as answered
    parents = _parents(by_id.values(), cache)

    def row(a, extra=None):
        st = a.student
        r = {"id": st.pk, "name": f"{st.first_name} {st.last_name}".strip() or st.username,
             "class": str(st.school_class) if st.school_class_id else "", "index": st.index_number,
             "parents": parents.get(st.pk, []), "left_screen": flags.get(st.pk, 0),
             "answered": answered.get(a.pk, 0),
             "started_at": _ts(a, "started_at", "created_at", "start_at"),
             "attempt_no": a.attempt_no}
        r.update(extra or {})
        return r

    leave_cfg = SchoolSettings.load()
    data["leave_lock"] = {"enabled": bool(leave_cfg.leave_lock_enabled), "limit": int(leave_cfg.leave_lock_limit)}
    data["in_progress_students"] = sorted((row(a, {
        "seconds_left": max(0, int((a.deadline_at - now).total_seconds())),
        "online": a.student_id in online,
        "attempt_id": a.pk, "leaves_used": max(0, left_now.get(a.pk, 0) - a.leaves_forgiven),
        "locked": bool(a.screen_lock), "lock_reason": a.screen_lock or ""}) for a in live), key=lambda r: (r["class"], r["name"]))
    data["submitted_students"] = sorted((row(a, {
        "submitted_at": _ts(a, "submitted_at", "finished_at", "ended_at"),
        "auto_submitted": a.status == Attempt.AUTO_SUBMITTED,
        "completion": "full" if data["total_questions"] and answered.get(a.pk, 0) >= data["total_questions"] else "partial"})
        for a in done),
        key=lambda r: (r["class"], r["name"]))
    data["not_started_students"] = sorted((
        {"id": s.pk, "name": f"{s.first_name} {s.last_name}".strip() or s.username,
         "class": str(s.school_class) if s.school_class_id else "", "index": s.index_number,
         "parents": parents.get(s.pk, [])} for s in eligible if s.pk not in latest),
        key=lambda r: (r["class"], r["name"]))
    data["full"] = sum(1 for r in data["submitted_students"] if r["completion"] == "full")
    data["partial"] = len(data["submitted_students"]) - data["full"]
    data["online_now"] = sum(1 for a in live if a.student_id in online)
    data["connection_problems"] = [{"id": r["id"], "name": r["name"]}
                                   for r in data["in_progress_students"] if not r["online"]]
    data["screen_leave_flags"] = [{"student_id": k, "times_left_screen": v} for k, v in flags.items()]
    return data


# =============================================================== staff overview

@api_view(["GET"])
@permission_classes([IsStaffUser])
def staff_overview(request):
    """What is going on right now, in ONE request. Admins see the whole school (plus the audit trail and
    proximity alerts); teachers see only their own subjects and no student names."""
    from core.models import AuditLog

    now = timezone.now()
    u = request.user
    admin = u.is_admin_role
    exams = Exam.objects.all()
    if not admin:
        exams = exams.filter(subject__in=TeacherAssignment.objects.filter(teacher=u).values("subject"))
    exams = exams.select_related("subject", "submitted_by", "created_by").prefetch_related("classes")

    for e in exams.filter(status__in=[Exam.SCHEDULED, Exam.LIVE, Exam.CLOSED], start_at__isnull=False,
                          start_at__lte=now + timedelta(days=1), end_at__gte=now - timedelta(days=2)):
        services.sync_exam(e, now)  # status always follows the clock, even if cron is not running

    def brief(e, **extra):
        d = {"id": e.pk, "title": e.title, "subject": e.subject.name, "classes": [str(c) for c in e.classes.all()],
             "status": e.status, "start_at": e.start_at, "end_at": e.end_at, "duration_minutes": e.duration_minutes}
        d.update(extra)
        return d

    live = list(exams.filter(status=Exam.LIVE).order_by("end_at"))
    counts = {r["exam"]: r for r in Attempt.objects.filter(exam__in=live).values("exam").annotate(
        writing=Count("id", filter=Q(status=Attempt.IN_PROGRESS)), done=Count("id", filter=~Q(status=Attempt.IN_PROGRESS)))}
    live_rows = []
    for e in live:
        c = counts.get(e.pk, {})
        live_rows.append(brief(e, writing=c.get("writing", 0), submitted=c.get("done", 0),
                               eligible=services.eligible_students(e).count(), question_count=e.questions.filter(voided=False).count()))

    upcoming = [brief(e, question_count=e.questions.filter(voided=False).count())
                for e in exams.filter(status=Exam.SCHEDULED, start_at__gte=now).order_by("start_at")[:6]]

    pending_qs = exams.filter(status=Exam.DRAFT, submitted_at__isnull=False).order_by("-submitted_at")
    pending = [brief(e, submitted_at=e.submitted_at, submitted_by=_person(e.submitted_by),
                     question_count=e.questions.filter(voided=False).count()) for e in pending_qs[:8]]

    delay = SchoolSettings.load().result_delay_minutes
    awaiting = [brief(e, results_at=e.end_at + timedelta(minutes=delay) if e.end_at else None)
                for e in exams.filter(status=Exam.CLOSED).order_by("-end_at")[:5]]
    published = [brief(e) for e in exams.filter(status=Exam.PUBLISHED).order_by("-end_at")[:5]]

    attempts = Attempt.objects.filter(exam__in=exams)
    day_ago = now - timedelta(hours=24)
    totals = {
        "live_exams": len(live_rows),
        "writing_now": sum(r["writing"] for r in live_rows),
        "submitted_today": attempts.filter(submitted_at__gte=day_ago).count(),
        "scheduled": exams.filter(status=Exam.SCHEDULED).count(),
        "awaiting_scheduling": pending_qs.count(),
        "awaiting_results": exams.filter(status=Exam.CLOSED).count(),
        "drafts": exams.filter(status=Exam.DRAFT).count(),
    }
    out = {"server_time": now, "role": u.role, "totals": totals, "live": live_rows, "upcoming": upcoming,
           "pending_submissions": pending, "awaiting_results": awaiting, "recently_published": published}

    if admin:
        online = online_ids()
        totals["students_online"] = len(online)
        totals["students_total"] = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False).count()
        totals["teachers_total"] = User.objects.filter(role=User.Role.TEACHER, is_active=True, is_archived=False).count()
        try:
            from proctoring.models import ProximityAlert
            totals["proximity_alerts"] = ProximityAlert.objects.filter(active=True, acknowledged_at__isnull=True).count()
        except Exception:  # the proctoring app is optional for the overview
            logging.getLogger(__name__).exception("proximity count failed")
            totals["proximity_alerts"] = 0
        out["recent_activity"] = [
            {"id": a.pk, "actor": _person(a.actor) if a.actor_id else "System", "action": a.action, "target": a.target,
             "at": a.created_at}
            for a in AuditLog.objects.select_related("actor").order_by("-created_at")[:10]]
    return Response(out)
