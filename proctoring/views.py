
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdminRole, IsStudent
from core.models import audit
from exams.models import Attempt, Exam
from . import geocode, services
from . import geo
from .models import LiveLocation, ProximityAlert


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
    services.ingest(attempt, fix, speed=num("speed"), heading=num("heading"), sensors=sensors, motion_moving=motion_moving)
    return Response({"ok": True})


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
            "acknowledged": bool(al.acknowledged_at), "duration_s": int((al.last_seen - al.first_seen).total_seconds())}


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
    return Response({"server_time": now.isoformat(), "exam": {"id": exam.pk, "title": exam.title, "status": exam.status},
                     "alert_meters": services.threshold(), "writing": len(attempts), "students": students, "no_signal": silent,
                     "alerts": [_alert(a, now) for a in alerts], "enabled": services.enabled()})


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
