"""Teacher, student and admin analytics plus report downloads (SRS 4.6, 4.7, 4.8).

Rules enforced here:
- Only PUBLISHED results are ever counted (TCH-08). During a live exam staff use the monitor.
- A teacher only sees her own subjects, and only the classes she is assigned to (TCH-01).
- A student only ever sees her own data (BR-07, RES-08).
- Nothing here can change a mark (TCH-10)."""
from collections import defaultdict
from urllib.parse import quote

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from academics.models import Subject, Term, TeacherAssignment
from accounts.models import User
from accounts.permissions import IsAdminRole, IsStaffUser, IsStudent
from core import grading, reports
from core.models import SchoolSettings, audit
from exams import services
from exams.models import Answer, Attempt, AttemptEvent, Exam, Result
from exams.views import _result_payload, _visible_result_or_404
from gamification import services as gamification
from . import calc


# ---------------------------------------------------------------- scope and data access

def scope_for(user):
    """None for admins (everything). For a teacher: {subject_id: None (all classes) or {class ids}}."""
    if user.is_admin_role:
        return None
    scope = {}
    for a in TeacherAssignment.objects.filter(teacher=user):
        if a.school_class_id is None:
            scope[a.subject_id] = None
        elif a.subject_id not in scope:
            scope[a.subject_id] = {a.school_class_id}
        elif scope[a.subject_id] is not None:
            scope[a.subject_id].add(a.school_class_id)
    return scope


def _sync_due_exams():
    """Make sure an exam whose publish time has passed is Published before we count it (no cron needed)."""
    now = timezone.now()
    for e in Exam.objects.filter(status__in=[Exam.LIVE, Exam.CLOSED], end_at__lt=now):
        services.sync_exam(e, now)


def visible_results(user):
    _sync_due_exams()
    qs = Result.objects.filter(exam__status=Exam.PUBLISHED).select_related(
        "exam__subject", "student__school_class", "attempt")
    scope = scope_for(user)
    if scope is None:
        return qs
    q = Q(pk__in=[])
    for subject_id, classes in scope.items():
        part = Q(exam__subject_id=subject_id)
        if classes is not None:
            part &= Q(student__school_class_id__in=classes)
        q |= part
    return qs.filter(q)


def to_rows(results):
    rows = []
    for r in results:
        s, c, e = r.student, r.student.school_class, r.exam
        rows.append({
            "result_id": r.pk, "attempt_id": r.attempt_id, "attempt_no": r.attempt.attempt_no,
            "student_id": s.pk, "student_name": f"{s.first_name} {s.last_name}".strip() or s.username,
            "class_id": c.pk if c else None, "class_label": str(c) if c else "-", "stream": c.stream if c else "",
            "exam_id": e.pk, "exam_title": e.title, "subject_id": e.subject_id, "subject": e.subject.name,
            "term_id": e.term_id, "date": e.start_at, "percent": r.percent, "grade": r.grade, "points": r.points,
            "passed": r.passed, "time_taken": r.time_taken_seconds, "topic_stats": r.topic_stats,
            "scale": r.scale_snapshot,
        })
    return calc.latest_attempts(rows)


def _subject_rows(request, subject_id):
    scope = scope_for(request.user)
    if scope is not None and subject_id not in scope:
        raise NotFound()  # same answer as "does not exist"
    get_object_or_404(Subject, pk=subject_id)
    qs = visible_results(request.user).filter(exam__subject_id=subject_id)
    p = request.query_params
    if p.get("class"):
        qs = qs.filter(student__school_class_id=p["class"])
    if p.get("term"):
        qs = qs.filter(exam__term_id=p["term"])
    return to_rows(qs)


def _roster(rows, subject_id, user):
    """Students a teacher can see for a subject: her classes that sit its exams, plus anyone with a result."""
    exams = list(Exam.objects.filter(subject_id=subject_id, status=Exam.PUBLISHED).prefetch_related("classes", "students"))
    class_ids = {c.pk for e in exams for c in e.classes.all()}
    scope = scope_for(user)
    if scope is not None and scope.get(subject_id) is not None:
        class_ids &= scope[subject_id]
    ids = {r["student_id"] for r in rows}
    q = Q(pk__in=ids)
    if class_ids:
        q |= Q(school_class_id__in=class_ids)
    students = User.objects.filter(role=User.Role.STUDENT, is_archived=False).filter(q).select_related("school_class")
    if scope is not None and scope.get(subject_id) is not None:
        students = students.filter(school_class_id__in=scope[subject_id])
    return list(students), exams


def _eligible_count(student, exams):
    n = 0
    for e in exams:
        if student.school_class_id in {c.pk for c in e.classes.all()} or student.pk in {s.pk for s in e.students.all()}:
            n += 1
    return n


def _full_name(u):
    return f"{u.first_name} {u.last_name}".strip() or u.username


# ---------------------------------------------------------------- teacher / admin analytics

@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_list(request):
    scope = scope_for(request.user)
    subjects = Subject.objects.all() if scope is None else Subject.objects.filter(pk__in=scope.keys())
    rows = to_rows(visible_results(request.user))
    by_subject = defaultdict(list)
    for r in rows:
        by_subject[r["subject_id"]].append(r)
    return Response([{"id": s.pk, "name": s.name, **calc.summary(by_subject[s.pk])} for s in subjects])


@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_dashboard(request, subject_id):
    """TCH-02: average, highest, lowest, pass rate, grade distribution, trend, class and stream comparison."""
    rows = _subject_rows(request, subject_id)
    return Response({
        "subject": get_object_or_404(Subject, pk=subject_id).name,
        **calc.summary(rows),
        "trend": calc.trend(rows),
        "by_class": calc.by_group(rows, lambda r: r["class_id"], lambda r: r["class_label"]),
        "by_stream": calc.by_group(rows, lambda r: r["stream"], lambda r: r["stream"] or "(no stream)"),
        "topics": calc.topic_percentages(rows),
    })


@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_students(request, subject_id):
    """TCH-03 + TCH-04: students with score history, participation and automatic flags."""
    rows = _subject_rows(request, subject_id)
    students, exams = _roster(rows, subject_id, request.user)
    overview = calc.student_overview(rows)
    engagement = gamification.engagement_for([s.pk for s in students], subject_id=subject_id)
    out = []
    for s in students:
        o = overview.get(s.pk, {"exams_taken": 0, "average": None, "latest": None, "history": [], "flag": None, "flag_reason": ""})
        eligible = _eligible_count(s, exams) or o["exams_taken"]
        out.append({"student_id": s.pk, "name": _full_name(s), "class": str(s.school_class) if s.school_class else None,
                    **o, "exams_eligible": eligible,
                    "current_streak": engagement[s.pk]["current_streak"],
                    "practice_sessions": engagement[s.pk]["practice_sessions"],
                    "participation_percent": round(o["exams_taken"] / eligible * 100, 1) if eligible else None})
    order = {"needs_support": 0, "top_performer": 1, None: 2}
    out.sort(key=lambda x: (order[x["flag"]], x["name"]))
    return Response(out)


@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_student_profile(request, subject_id, student_id):
    """TCH-03: one student in the teacher's subject, with her streak and practice activity (no other students' data)."""
    rows = _subject_rows(request, subject_id)
    students, exams = _roster(rows, subject_id, request.user)
    student = next((s for s in students if s.pk == student_id), None)
    if not student:
        raise NotFound()
    mine = [r for r in rows if r["student_id"] == student_id]
    topics = calc.topic_percentages(mine)
    hist = calc.history(mine)
    eligible = _eligible_count(student, exams) or len(hist)
    flag, reason = calc.flag_for([h["percent"] for h in hist])
    eng = gamification.engagement_for([student.pk], subject_id=subject_id)[student.pk]
    return Response({
        "student_id": student.pk, "name": _full_name(student), "class": str(student.school_class) if student.school_class else None,
        "scores_over_time": hist, **calc.summary(mine), **calc.strengths_and_weaknesses(topics), "topics": topics,
        "average_time_taken_seconds": round(sum(r["time_taken"] for r in mine) / len(mine)) if mine else None,
        "participation": {"taken": len(hist), "eligible": eligible},
        "flag": flag, "flag_reason": reason,
        "streak": {"current": eng["current_streak"], "best": eng["best_streak"]},
        "practice_activity": {k: eng[k] for k in ("practice_sessions", "practice_sessions_last_30_days",
                                                  "practice_average_percent", "last_practice_at")},
        "engagement": {k: eng[k] for k in ("total_xp", "active_days_last_30")},
    })


@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_heatmap(request, subject_id):
    """TCH-06: topic mastery by class."""
    return Response(calc.heatmap(_subject_rows(request, subject_id)))


def _published_exam_for(request, exam_id):
    scope = scope_for(request.user)
    exam = get_object_or_404(Exam.objects.select_related("subject"), pk=exam_id)
    if scope is not None and exam.subject_id not in scope:
        raise NotFound()
    services.sync_exam(exam)
    exam.refresh_from_db()
    if exam.status != Exam.PUBLISHED:
        raise NotFound()  # TCH-08: nothing before results are published
    return exam


@api_view(["GET"])
@permission_classes([IsStaffUser])
def exam_question_analysis(request, exam_id):
    """TCH-05: % correct, most chosen wrong answer and observed difficulty per question."""
    exam = _published_exam_for(request, exam_id)
    rows = to_rows(visible_results(request.user).filter(exam=exam))
    attempt_ids = [r["attempt_id"] for r in rows]
    answers = list(Answer.objects.filter(attempt_id__in=attempt_ids).values("exam_question_id", "response", "skipped"))
    questions = [{"id": q.pk, "position": q.position, "voided": q.voided, "payload": q.payload} for q in exam.questions.all()]
    return Response({"exam": exam.title, "students": len(rows), "questions": calc.question_stats(questions, answers, len(rows))})


@api_view(["GET"])
@permission_classes([IsStaffUser])
def exam_integrity(request, exam_id):
    """EDAY-11: how many times each student left the exam screen. Information only, never proof."""
    exam = _published_exam_for(request, exam_id)
    rows = to_rows(visible_results(request.user).filter(exam=exam))
    names = {r["attempt_id"]: (r["student_id"], r["student_name"]) for r in rows}
    counts = (AttemptEvent.objects.filter(attempt_id__in=names, kind="left_screen")
              .values("attempt_id").annotate(n=Count("id")))
    return Response({"note": "Leaving the screen can have innocent causes such as a phone call. Use as information only.",
                     "flags": sorted(({"student_id": names[c["attempt_id"]][0], "name": names[c["attempt_id"]][1],
                                       "times_left_screen": c["n"]} for c in counts), key=lambda x: -x["times_left_screen"])})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def school_analytics(request):
    """ADM-08: by subject, class, stream and term; participation; engagement (Phase 3)."""
    rows = to_rows(visible_results(request.user))
    terms = {t.pk: str(t) for t in Term.objects.select_related("year")}
    exams = list(Exam.objects.filter(status=Exam.PUBLISHED).select_related("subject"))
    participation = []
    for e in exams:
        eligible = services.eligible_students(e).count()
        took = e.attempts.values("student").distinct().count()
        participation.append({"exam_id": e.pk, "title": e.title, "eligible": eligible, "participants": took,
                              "rate": round(took / eligible * 100, 1) if eligible else None})
    total_e = sum(p["eligible"] for p in participation)
    total_p = sum(p["participants"] for p in participation)
    return Response({
        **calc.summary(rows),
        "by_subject": calc.by_group(rows, lambda r: r["subject_id"], lambda r: r["subject"]),
        "by_class": calc.by_group(rows, lambda r: r["class_id"], lambda r: r["class_label"]),
        "by_stream": calc.by_group(rows, lambda r: r["stream"], lambda r: r["stream"] or "(no stream)"),
        "by_term": calc.by_group(rows, lambda r: r["term_id"], lambda r: terms.get(r["term_id"], "No term set")),
        "participation": {"overall_rate": round(total_p / total_e * 100, 1) if total_e else None, "exams": participation},
        "engagement": gamification.school_engagement(),
    })


# ---------------------------------------------------------------- student analytics

def _own_rows(user):
    now = timezone.now()
    results = [r for r in Result.objects.filter(student=user).select_related("exam__subject", "student__school_class", "attempt")
               if services.result_visible(r.attempt, now)]
    return to_rows(results)


@api_view(["GET"])
@permission_classes([IsStudent])
def student_analytics(request):
    """RES-04 / GRD-03: strengths, weak areas, progress per subject, what to revise, projected division."""
    rows = _own_rows(request.user)
    by_subject = defaultdict(list)
    for r in rows:
        by_subject[r["subject"]].append(r)
    subjects, averages = [], {}
    for name, rs in sorted(by_subject.items()):
        h = calc.history(rs)
        topics = calc.topic_percentages(rs)
        sw = calc.strengths_and_weaknesses(topics)
        averages[name] = sum(r["percent"] for r in rs) / len(rs)
        subjects.append({
            "subject": name, "exams_taken": len(h), "average": round(averages[name], 1), "latest": h[-1]["percent"],
            "change_from_previous": round(h[-1]["percent"] - h[-2]["percent"], 1) if len(h) > 1 else None,
            "progress": h, "topics": topics, **sw, "revise": [t["topic"] for t in sw["weak_areas"]][:3],
        })
    latest = max(rows, key=lambda r: r["date"] or timezone.now())["scale"] if rows else grading.DEFAULT_SCALE
    return Response({
        "subjects": subjects, "exams_taken": len(rows),
        "projected": {**calc.report_card(averages, latest), "is_projection": True,
                      "note": "A projection from the exams so far. It is not an official NECTA result."},
    })


@api_view(["GET"])
@permission_classes([IsStudent])
def student_report_card(request):
    """GRD-02: best seven subjects. ?term=<id> for one term; without it, all published results so far.
    It is marked as a projection until the chosen term has ended."""
    rows = _own_rows(request.user)
    term = None
    if request.query_params.get("term"):
        term = get_object_or_404(Term.objects.select_related("year"), pk=request.query_params["term"])
        rows = [r for r in rows if r["term_id"] == term.pk]
    by_subject = defaultdict(list)
    for r in rows:
        by_subject[r["subject"]].append(r["percent"])
    averages = {k: sum(v) / len(v) for k, v in by_subject.items()}
    scale = max(rows, key=lambda r: r["date"] or timezone.now())["scale"] if rows else SchoolSettings.load().grade_scale
    final = bool(term and term.end_date < timezone.localdate())
    return Response({"term": str(term) if term else "All terms so far", **calc.report_card(averages, scale),
                     "is_projection": not final,
                     "note": None if final else "Marked as a projection: the term is still running or no term was chosen."})


# ---------------------------------------------------------------- downloads

def _download(data, content_type, filename):
    resp = HttpResponse(data, content_type=content_type)
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return resp


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file_kind(request, default="xlsx"):
    k = request.query_params.get("file", default)
    return k if k in ("pdf", "xlsx") else default


def _slip(attempt):
    """RES-06. The caller has already checked ownership/visibility."""
    result = attempt.result
    p = _result_payload(attempt, result)
    meaning = next((g.get("meaning", "") for g in result.scale_snapshot["grades"] if g["grade"] == result.grade), "")
    s = attempt.student
    pdf = reports.result_slip_pdf(SchoolSettings.load().school_name, {
        "student": _full_name(s), "klass": str(s.school_class) if s.school_class else "-", "exam": p["exam"],
        "subject": p["subject"], "date": timezone.localtime(attempt.exam.start_at).strftime("%a %d %b %Y"),
        "score": p["score"], "total": p["total"], "percent": p["percent"], "grade": p["grade"], "points": p["points"],
        "meaning": meaning, "passed": p["passed"], "time_taken": p["time_taken_seconds"],
        "class_average": p["class_average_percent"], "position": p.get("class_position"),
        "topics": [(t["topic"], t["percent"]) for t in p["topics"]], "revise": p["revise"],
    })
    return _download(pdf, "application/pdf", f"result_slip_{s.username}_{attempt.exam_id}.pdf")


@api_view(["GET"])
@permission_classes([IsStudent])
def my_slip(request, attempt_id):
    attempt, err = _visible_result_or_404(request, attempt_id)  # own attempt only; hidden before publish
    if err:
        return err
    return _slip(attempt)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_slip(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("exam", "student__school_class", "result"), pk=attempt_id)
    services.sync_exam(attempt.exam)
    if not hasattr(attempt, "result") or not services.result_visible(attempt):
        raise NotFound()
    audit(request.user, "export.slip", attempt.pk)
    return _slip(attempt)


@api_view(["GET"])
@permission_classes([IsStaffUser])
def subject_export(request, subject_id):
    """TCH-09: subject report as Excel (default) or PDF: ?file=xlsx|pdf. Same scope as the dashboard."""
    rows = _subject_rows(request, subject_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    students, exams = _roster(rows, subject_id, request.user)
    overview = calc.student_overview(rows)
    s = calc.summary(rows)
    topics = calc.topic_percentages(rows)
    summary = [["Results counted", s["count"]], ["Average %", s["average"]], ["Highest %", s["highest"]],
               ["Lowest %", s["lowest"]], ["Pass rate %", s["pass_rate"]]]
    dist = [[g, n] for g, n in s["grade_distribution"].items()]
    trend = [[t["title"], t["date"].strftime("%Y-%m-%d") if t["date"] else "", t["participants"], t["average"], t["pass_rate"]]
             for t in calc.trend(rows)]
    klass = [[c["label"], c["count"], c["average"], c["pass_rate"]]
             for c in calc.by_group(rows, lambda r: r["class_id"], lambda r: r["class_label"])]
    stud = []
    for st in sorted(students, key=lambda u: _full_name(u)):
        o = overview.get(st.pk)
        stud.append([_full_name(st), str(st.school_class or ""), o["exams_taken"] if o else 0, o["average"] if o else "",
                     o["latest"] if o else "", (o["flag"] or "").replace("_", " ") if o else ""])
    top = [[t["topic"], t["percent"]] for t in topics]
    sections = [("Summary", ["Measure", "Value"], summary), ("Grades", ["Grade", "Students"], dist),
                ("Exams", ["Exam", "Date", "Students", "Average %", "Pass rate %"], trend),
                ("Classes", ["Class", "Results", "Average %", "Pass rate %"], klass),
                ("Students", ["Name", "Class", "Exams taken", "Average %", "Latest %", "Flag"], stud),
                ("Topics", ["Topic", "Mastery %"], top)]
    audit(request.user, "export.subject_report", subject.pk)
    if _file_kind(request) == "pdf":
        pdf = reports.sections_pdf(SchoolSettings.load().school_name, f"{subject.name} - subject report",
                                   f"Generated {timezone.localtime().strftime('%d %b %Y %H:%M')}",
                                   [{"heading": t, "headers": h, "rows": r} for t, h, r in sections])
        return _download(pdf, "application/pdf", f"{subject.name}_report.pdf")
    return _download(reports.sheets_xlsx(sections), XLSX, f"{subject.name}_report.xlsx")


@api_view(["GET"])
@permission_classes([IsAdminRole])
def exam_results_export(request, exam_id):
    """ADM-11: all results of one exam (after publish): ?file=xlsx|pdf."""
    exam = get_object_or_404(Exam.objects.select_related("subject"), pk=exam_id)
    services.sync_exam(exam)
    exam.refresh_from_db()
    if exam.status != Exam.PUBLISHED:
        raise ValidationError({"detail": "Results can be exported only after they are published."})
    rows = sorted(to_rows(visible_results(request.user).filter(exam=exam)), key=lambda r: (r["class_label"], r["student_name"]))
    headers = ["Name", "Class", "Score %", "Grade", "Points", "Passed", "Minutes taken"]
    data = [[r["student_name"], r["class_label"], r["percent"], r["grade"], r["points"], "Yes" if r["passed"] else "No",
             round(r["time_taken"] / 60, 1)] for r in rows]
    audit(request.user, "export.exam_results", exam.pk)
    if _file_kind(request) == "pdf":
        pdf = reports.sections_pdf(SchoolSettings.load().school_name, f"{exam.title} - results", exam.subject.name,
                                   [{"heading": "Results", "headers": headers, "rows": data}])
        return _download(pdf, "application/pdf", f"results_{exam.pk}.pdf")
    return _download(reports.sheets_xlsx([("Results", headers, data)]), XLSX, f"results_{exam.pk}.xlsx")


@api_view(["GET"])
@permission_classes([IsAdminRole])
def students_export(request):
    """ADM-11: student list (?class=<id>&file=xlsx|pdf)."""
    qs = User.objects.filter(role=User.Role.STUDENT, is_archived=False).select_related("school_class").order_by(
        "school_class__form_level", "school_class__stream", "last_name")
    if request.query_params.get("class"):
        qs = qs.filter(school_class_id=request.query_params["class"])
    headers = ["Name", "Username", "Index number", "Class", "Status"]
    data = [[_full_name(u), u.username, u.index_number, str(u.school_class or ""),
             "Graduated" if u.graduated else "Active" if u.is_active else "Inactive"] for u in qs]
    audit(request.user, "export.students", "", count=len(data))
    if _file_kind(request) == "pdf":
        pdf = reports.sections_pdf(SchoolSettings.load().school_name, "Student list", "",
                                   [{"heading": "Students", "headers": headers, "rows": data}], wide=False)
        return _download(pdf, "application/pdf", "students.pdf")
    return _download(reports.sheets_xlsx([("Students", headers, data)]), XLSX, "students.xlsx")
