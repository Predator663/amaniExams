
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdminRole, IsStudent
from core.models import audit
from exams.models import Attempt, Exam
from . import geocode, services
from . import geo
from accounts.models import User
from .models import IntegrityFlag, LiveLocation, ProximityAlert, StudentRelation


@api_view(["GET"])
@permission_classes([IsStudent])
def config(request):
    """What the student's phone needs to know before and during an exam."""
    return Response({"enabled": services.enabled(), "legal_version": settings.LEGAL_VERSION,
                     "report_every_seconds": 6, "alert_meters": services.threshold()})


@api_view(["POST"])
@permission_classes([IsStudent])
def report_location(request, attempt_id):
    """The phone reports where it is. Positions of students who are not in an exam attempt are never accepted."""
    attempt = get_object_or_404(Attempt.objects.select_related("exam", "student"), pk=attempt_id, student=request.user)
    if not services.enabled():
        return Response({"ok": True, "enabled": False})
    if attempt.status != Attempt.IN_PROGRESS:
        return Response({"detail": "This exam attempt is finished.", "code": "finished"}, status=409)
    fix = services.parse_fix(request.data)
    if not fix:
        return Response({"detail": "Position not valid.", "code": "bad_fix"}, status=400)

    def num(k):
        try:
            v = float(request.data.get(k))
            return v if v == v else None  # NaN guard
        except (TypeError, ValueError):
            return None
    sensors = request.data.get("sensors")
    motion_moving = isinstance(sensors, dict) and sensors.get("motion") == "moving"
    services.ingest(attempt, fix, speed=num("speed"), heading=num("heading"), sensors=sensors, motion_moving=motion_moving, **services.client_info(request))
    lock = services.locking_alert(attempt.exam_id, request.user.pk)
    from notifications.models import AdminMessage
    unseen = AdminMessage.objects.filter(recipient=request.user, dismissed_at__isnull=True).count()  # the exam screen then shows the banner at once
    return Response({"ok": True, "locked": bool(lock), "messages": unseen})


def _row(ll, now):
    age = (now - ll.updated_at).total_seconds()
    fresh = age <= services.stale_after()
    moving = bool(ll.moving_until and ll.moving_until > now and fresh)
    poor = ll.accuracy > services.max_accuracy()
    return {"id": ll.student_id, "name": services.name_of(ll.student), "class": str(ll.student.school_class) if ll.student.school_class_id else "",
            "index": ll.student.index_number, "lat": ll.lat, "lng": ll.lng, "accuracy": round(ll.accuracy, 1),
            "speed": ll.speed, "heading": ll.heading, "moving": moving, "moving_source": ll.moving_source if moving else "",
            "age_s": int(age), "fresh": fresh, "poor": poor, "checks": ll.sensors or {}}


def _alert(al, now):
    pos = next(iter((al.snapshot or {}).get("positions", {}).values()), None)  # where the pair was at their closest moment
    return {"lat": pos[0] if pos else None, "lng": pos[1] if pos else None, "id": al.pk, "a": {"id": al.a_id, "name": services.name_of(al.a)}, "b": {"id": al.b_id, "name": services.name_of(al.b)},
            "distance_m": round(al.last_distance, 1), "min_distance_m": round(al.min_distance, 1), "confidence": al.confidence,
            "first_seen": al.first_seen.isoformat(), "last_seen": al.last_seen.isoformat(), "active": al.active,
            "acknowledged": bool(al.acknowledged_at), "duration_s": int((al.last_seen - al.first_seen).total_seconds()),
            "locked": bool(al.locked and not al.unlocked_at), "locked_at": al.locked_at.isoformat() if al.locked_at else None,
            "unlocked_at": al.unlocked_at.isoformat() if al.unlocked_at else None}


@api_view(["GET"])
@permission_classes([IsAdminRole])
def exam_board(request, exam_id):
    """Anti-cheat tab: where every writing student is, who is moving, who is too close to whom, and who has no signal."""
    exam = get_object_or_404(Exam, pk=exam_id)
    now = timezone.now()
    services.close_stale_alerts(exam.pk, now)
    attempts = list(Attempt.objects.filter(exam=exam, status=Attempt.IN_PROGRESS).select_related("student", "student__school_class"))
    by_attempt = {ll.attempt_id: ll for ll in LiveLocation.objects.filter(attempt__in=attempts).select_related("student", "student__school_class")}
    students, silent = [], []
    for a in attempts:
        ll = by_attempt.get(a.pk)
        if ll is None or (now - ll.updated_at).total_seconds() > services.stale_after() * 2:
            silent.append({"id": a.student_id, "name": services.name_of(a.student), "class": str(a.student.school_class) if a.student.school_class_id else "",
                           "index": a.student.index_number, "last_seen_s": int((now - ll.updated_at).total_seconds()) if ll else None,
                           "checks": (ll.sensors if ll else {}) or {}})
        if ll is not None:
            students.append(_row(ll, now))
    alerts = ProximityAlert.objects.filter(exam=exam).select_related("a", "b").order_by("-active", "-last_seen")[:60]
    rank = {"high": 0, "warning": 1, "info": 2}
    flags = sorted(IntegrityFlag.objects.filter(exam=exam).select_related("student", "attempt")[:200],
                   key=lambda f: (f.acknowledged_at is not None, rank.get(f.severity, 3), -f.last_seen.timestamp()))
    return Response({"server_time": now.isoformat(), "exam": {"id": exam.pk, "title": exam.title, "status": exam.status},
                     "alert_meters": services.threshold(), "lock_enabled": services.lock_enabled(), "writing": len(attempts),
                     "students": students, "no_signal": silent, "alerts": [_alert(a, now) for a in alerts], "flags": [_flag(f) for f in flags],
                     "links": services.relation_links(students, services.threshold()),
                     "enabled": services.enabled()})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def ack_alert(request, alert_id):
    al = get_object_or_404(ProximityAlert.objects.select_related("a", "b", "exam"), pk=alert_id)
    if not al.acknowledged_at:
        al.acknowledged_by, al.acknowledged_at = request.user, timezone.now()
        al.save(update_fields=["acknowledged_by", "acknowledged_at"])
        audit(request.user, "proximity_alert_reviewed", f"alert {al.pk}", exam=al.exam_id, students=[al.a_id, al.b_id],
              min_distance_m=round(al.min_distance, 1))
    return Response({"ok": True})


def _relation(r):
    return {"id": r.pk, "kind": r.kind, "label": r.get_kind_display(), "note": r.note,
            "a": {"id": r.a_id, "name": services.name_of(r.a), "index": r.a.index_number, "class": str(r.a.school_class) if r.a.school_class_id else ""},
            "b": {"id": r.b_id, "name": services.name_of(r.b), "index": r.b.index_number, "class": str(r.b.school_class) if r.b.school_class_id else ""},
            "created_at": r.created_at.isoformat()}


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def relations(request):
    """GET: the related pairs (?q= searches names). POST {students: [ids], kind, note}: mark every pair among 2 to 8 students
    (twins, triplets, a household) as related, so they are shown with a line instead of being alerted or locked."""
    if request.method == "GET":
        qs = StudentRelation.objects.select_related("a", "b", "a__school_class", "b__school_class")
        q = (request.query_params.get("q") or "").strip()
        if q:
            f = lambda p: Q(**{p + "first_name__icontains": q}) | Q(**{p + "last_name__icontains": q}) | Q(**{p + "index_number__icontains": q})
            qs = qs.filter(f("a__") | f("b__"))
        return Response({"results": [_relation(r) for r in qs[:300]]})
    ids = request.data.get("students")
    kind = request.data.get("kind")
    note = str(request.data.get("note") or "").strip()[:120]
    if not isinstance(ids, list) or not 2 <= len(set(map(str, ids))) <= 8:
        return Response({"detail": "Choose from 2 to 8 students."}, status=400)
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return Response({"detail": "Choose students from the list."}, status=400)
    if kind not in dict(StudentRelation.KINDS):
        return Response({"detail": "Choose the kind of relation: twins, same house or same room."}, status=400)
    found = set(User.objects.filter(pk__in=ids, role=User.Role.STUDENT, is_archived=False).values_list("pk", flat=True))
    if found != set(ids):
        return Response({"detail": "Only current students can be marked as related."}, status=400)
    rels = services.mark_related(request.user, ids, kind, note)
    rels = StudentRelation.objects.filter(pk__in=[r.pk for r in rels]).select_related("a", "b", "a__school_class", "b__school_class")
    return Response({"ok": True, "results": [_relation(r) for r in rels]}, status=201)


@api_view(["DELETE"])
@permission_classes([IsAdminRole])
def relation_delete(request, relation_id):
    r = get_object_or_404(StudentRelation, pk=relation_id)
    audit(request.user, "student_relation_removed", f"relation {r.pk}", students=[r.a_id, r.b_id], kind=r.kind)
    r.delete()
    return Response({"ok": True})


def _flag(f):
    return {"id": f.pk, "student": {"id": f.student_id, "name": services.name_of(f.student), "index": f.student.index_number},
            "kind": f.kind, "label": f.get_kind_display(), "severity": f.severity, "count": f.count, "text": services.flag_text(f),
            "meaning": services.FLAG_TEXT.get(f.kind, ""), "first_seen": f.first_seen.isoformat(), "last_seen": f.last_seen.isoformat(),
            "acknowledged": bool(f.acknowledged_at)}


@api_view(["POST"])
@permission_classes([IsAdminRole])
def ack_flag(request, flag_id):
    """The administrator has looked at it. A new episode of the same sign shows it again."""
    f = get_object_or_404(IntegrityFlag.objects.select_related("exam"), pk=flag_id)
    services.acknowledge_flag(f, request.user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def unlock_alert(request, alert_id):
    """Let both students of one alert carry on. The exam clock never stopped, so they have lost the time they were locked."""
    al = get_object_or_404(ProximityAlert.objects.select_related("a", "b", "exam"), pk=alert_id)
    services.unlock(al, request.user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def unlock_exam(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    return Response({"ok": True, "unlocked": services.unlock_all(exam.pk, request.user)})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def place(request):
    """Street / district / region / country for a position (administrators only, see geocode.py)."""
    try:
        lat, lng = float(request.query_params.get("lat")), float(request.query_params.get("lng"))
    except (TypeError, ValueError):
        return Response({"detail": "lat and lng are required.", "code": "bad_fix"}, status=400)
    if not geo.valid_fix(lat, lng, 0):
        return Response({"detail": "Position not valid.", "code": "bad_fix"}, status=400)
    p = geocode.reverse(lat, lng)
    return Response({"enabled": geocode.enabled(), **(p or {"label": None})})
