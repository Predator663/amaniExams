import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from exams.models import Attempt
from . import geo
from .models import LegalAcceptance, LiveLocation, ProximityAlert

log = logging.getLogger(__name__)

MOVING_HOLD_S = 15  # how long the "moving" indicator stays on after the last sign of movement
MIN_GAP_S = 2  # reports arriving faster than this are ignored (a phone that floods the server)


def enabled():
    return getattr(settings, "PROCTORING_ENABLED", True)


def threshold():
    return float(getattr(settings, "PROXIMITY_ALERT_METERS", 20))


def stale_after():
    return int(getattr(settings, "LOCATION_STALE_SECONDS", 45))


def clear_after():
    return int(getattr(settings, "PROXIMITY_CLEAR_SECONDS", 60))


def max_accuracy():
    return float(getattr(settings, "LOCATION_MAX_ACCURACY", 100))


def name_of(u):
    return f"{u.first_name} {u.last_name}".strip() or u.username


def parse_fix(data):
    """Validated (lat, lng, accuracy) from request data, or None."""
    try:
        lat, lng, acc = float(data.get("lat")), float(data.get("lng")), float(data.get("accuracy", 0))
    except (TypeError, ValueError, AttributeError):
        return None
    return (lat, lng, acc) if geo.valid_fix(lat, lng, acc) else None


def clean_sensors(raw):
    """Keep only the few short status words the phone may send (never free text)."""
    raw = raw if isinstance(raw, dict) else {}
    allowed = {"perm": {"granted", "denied", "prompt", "unknown"}, "ble": {"on", "off", "unsupported", "unknown"},
               "net": {"wifi", "cellular", "ethernet", "none", "unknown"}, "motion": {"still", "moving", "denied", "unsupported", "unknown"},
               "source": {"watch", "poll"}}
    out = {k: (raw.get(k) if raw.get(k) in v else "unknown") for k, v in allowed.items() if k in raw}
    return out


def record_acceptance(user, exam):
    return LegalAcceptance.objects.create(user=user, exam=exam, version=settings.LEGAL_VERSION)


def ingest(attempt, fix, speed=None, heading=None, sensors=None, motion_moving=False, now=None):
    """Store the latest position of a student and look for neighbours. Returns the LiveLocation."""
    now = now or timezone.now()
    lat, lng, acc = fix
    sensors = clean_sensors(sensors)
    with transaction.atomic():
        ll = LiveLocation.objects.select_for_update().filter(attempt=attempt).first()
        if ll and (now - ll.updated_at).total_seconds() < MIN_GAP_S:
            return ll
        moving_until, source = (ll.moving_until if ll else None), (ll.moving_source if ll else "")
        anchor = (ll.anchor_lat, ll.anchor_lng) if ll and ll.anchor_lat is not None else None
        moved = geo.has_moved(anchor, (lat, lng), acc)
        fast = speed is not None and speed >= 0.8 and acc <= max_accuracy()
        if moved or fast:
            moving_until, source = now + timedelta(seconds=MOVING_HOLD_S), "gps"
        elif motion_moving:
            moving_until, source = now + timedelta(seconds=MOVING_HOLD_S), "motion"
        if anchor is None or moved:
            anchor = (lat, lng)
        fields = dict(exam=attempt.exam, student=attempt.student, lat=lat, lng=lng, accuracy=acc, speed=speed, heading=heading,
                      anchor_lat=anchor[0], anchor_lng=anchor[1], moving_until=moving_until, moving_source=source,
                      sensors=sensors, updated_at=now)
        if ll:
            for k, v in fields.items():
                setattr(ll, k, v)
            ll.save()
        else:
            ll = LiveLocation.objects.create(attempt=attempt, **fields)
    try:
        evaluate(ll, now)
    except Exception:  # a failure in the alert logic must never break the student's exam
        log.exception("proximity evaluation failed")
    return ll


def _pair(x, y):
    return (x, y) if x.pk < y.pk else (y, x)


def evaluate(ll, now):
    """Compare this student with every other student of the same exam who has a fresh position, and open or refresh alerts."""
    limit = threshold()
    dlat, dlng = geo.bbox(ll.lat, ll.lng, limit + 5)
    fresh = now - timedelta(seconds=stale_after())
    near = (LiveLocation.objects.filter(exam_id=ll.exam_id, attempt__status=Attempt.IN_PROGRESS, updated_at__gte=fresh,
                                        lat__range=(ll.lat - dlat, ll.lat + dlat), lng__range=(ll.lng - dlng, ll.lng + dlng))
            .exclude(student_id=ll.student_id).select_related("student"))
    new_alerts = []
    for other in near:
        d = geo.haversine_m(ll.lat, ll.lng, other.lat, other.lng)
        conf = geo.classify_pair(d, ll.accuracy, other.accuracy, limit, max_accuracy())
        if not conf:
            continue
        a, b = _pair(ll.student, other.student)
        alert = ProximityAlert.objects.filter(exam_id=ll.exam_id, a=a, b=b, active=True).first()
        snap = {"at": now.isoformat(), "distance_m": round(d, 1),
                "positions": {str(ll.student_id): [ll.lat, ll.lng, ll.accuracy], str(other.student_id): [other.lat, other.lng, other.accuracy]}}
        if alert:
            alert.last_seen, alert.last_distance = now, d
            if d < alert.min_distance:
                alert.min_distance, alert.snapshot = d, snap
            if conf == ProximityAlert.CONFIRMED:
                alert.confidence = conf
            alert.save(update_fields=["last_seen", "last_distance", "min_distance", "snapshot", "confidence"])
        else:
            alert = ProximityAlert.objects.create(exam_id=ll.exam_id, a=a, b=b, first_seen=now, last_seen=now, min_distance=d,
                                                  last_distance=d, confidence=conf, snapshot=snap)
            new_alerts.append(alert)
    if new_alerts:
        _notify_admins(new_alerts)
    close_stale_alerts(ll.exam_id, now)


def close_stale_alerts(exam_id, now):
    return ProximityAlert.objects.filter(exam_id=exam_id, active=True, last_seen__lt=now - timedelta(seconds=clear_after())).update(active=False)


def _notify_admins(alerts):
    from notifications.services import notify
    admins = list(User.objects.filter(role__in=["admin", "super_admin"], is_active=True))
    for al in alerts:
        title = "Students sitting close together"
        body = (f"{name_of(al.a)} and {name_of(al.b)} are about {round(al.last_distance)} m apart during “{al.exam.title}”"
                f"{'' if al.confidence == ProximityAlert.CONFIRMED else ' (position is rough, please check)'}. Open Live monitor → Anti-cheat.")
        notify(admins, "integrity_alert", title, body, key=f"prox:{al.pk}", data={"exam_id": al.exam_id, "alert_id": al.pk}, push=True)
