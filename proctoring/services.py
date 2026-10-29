import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from core.models import SchoolSettings, audit
from exams.models import Attempt
from . import geo, spoof
from .models import IntegrityFlag, LegalAcceptance, LiveLocation, ProximityAlert, StudentRelation

log = logging.getLogger(__name__)

MOVING_HOLD_S = 15  # how long the "moving" indicator stays on after the last sign of movement
MIN_GAP_S = 2  # reports arriving faster than this are ignored (a phone that floods the server)


def enabled():
    return getattr(settings, "PROCTORING_ENABLED", True)


def threshold():
    """The alert distance in metres, set by an administrator under Settings -> School (one cheap primary-key read)."""
    return float(SchoolSettings.load().proximity_alert_meters)


def lock_enabled():
    """True when students who sit closer than the alert distance get their exam screen locked until an admin unlocks."""
    return bool(SchoolSettings.load().proximity_lock_enabled)


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


def ingest(attempt, fix, speed=None, heading=None, sensors=None, motion_moving=False, now=None, device="", ua="", ip=""):
    """Store the latest position of a student and look for neighbours and for signs of a faked position or another device.
    `device` is the random id the browser made for itself, `ua` its User-Agent and `ip` the address the server saw.
    Returns the LiveLocation."""
    now = now or timezone.now()
    lat, lng, acc = fix
    sensors = clean_sensors(sensors)
    with transaction.atomic():
        ll = LiveLocation.objects.select_for_update().filter(attempt=attempt).first()
        if ll and (now - ll.updated_at).total_seconds() < MIN_GAP_S:
            return ll
        prev_fix = (ll.lat, ll.lng, ll.accuracy) if ll else None
        prev_dt = (now - ll.updated_at).total_seconds() if ll else None
        counters = spoof.next_counters(ll.spoof if ll else None, prev_fix, fix)
        devices, device_change = spoof.track_device(ll.devices if ll else None, spoof.clean_device(device), spoof.platform_of(ua), ip)
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
                      sensors=sensors, spoof=counters, devices=devices, updated_at=now)
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
    try:
        check_integrity(attempt, fix, prev_fix, prev_dt, counters, device_change, now)
    except Exception:
        log.exception("integrity checks failed")
    return ll


def client_ip(request):
    """The address the server saw. Behind the hosting proxy the real client is the LAST entry the proxy appended."""
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[-1].strip() if fwd else request.META.get("REMOTE_ADDR", ""))[:45]


def client_info(request):
    """Keyword arguments for services.ingest describing the device that sent this request."""
    return {"device": request.data.get("device") if hasattr(request.data, "get") else "",
            "ua": request.META.get("HTTP_USER_AGENT", "")[:300], "ip": client_ip(request)}


def check_integrity(attempt, fix, prev_fix, prev_dt, counters, device_change, now):
    """Raise flags for a device change and for the signs of a faked position (see spoof.py). Flags only inform administrators."""
    if device_change:
        sev = spoof.change_severity(device_change)
        raise_flag(attempt, IntegrityFlag.DEVICE_CHANGED, sev, {
            "from": _short(device_change["from"]), "to": _short(device_change["to"]), "at_start": _short(device_change["first"])}, now)
    jump = spoof.teleport(prev_fix, fix, prev_dt)
    if jump:
        raise_flag(attempt, IntegrityFlag.TELEPORT, IntegrityFlag.HIGH, jump, now)
    for kind, detail in spoof.episodes(counters, fix):
        raise_flag(attempt, kind, IntegrityFlag.WARNING, detail, now)


def _short(dev):
    """Evidence kept with a flag: a short device code (never the full id), the kind of device and the network address."""
    return {"device": (dev.get("id") or "")[:6], "platform": dev.get("platform", ""), "ip": dev.get("ip", "")}


_RANK = {IntegrityFlag.INFO: 0, IntegrityFlag.WARNING: 1, IntegrityFlag.HIGH: 2}


def raise_flag(attempt, kind, severity, detail, now):
    """Create the flag, or count one more episode on the existing one (and show it to the administrators again)."""
    with transaction.atomic():
        flag, created = IntegrityFlag.objects.select_for_update().get_or_create(
            attempt=attempt, kind=kind,
            defaults=dict(exam_id=attempt.exam_id, student_id=attempt.student_id, severity=severity, first_seen=now, last_seen=now, detail=detail))
        if not created:
            flag.count += 1
            flag.last_seen, flag.detail = now, detail
            if _RANK[severity] > _RANK[flag.severity]:
                flag.severity = severity
            flag.acknowledged_at = flag.acknowledged_by = None
            flag.save(update_fields=["count", "last_seen", "detail", "severity", "acknowledged_at", "acknowledged_by"])
    if created and severity != IntegrityFlag.INFO:
        _notify_flag(flag)
    return flag


def note_login(user, ip="", ua="", now=None):
    """A student logged in while an exam attempt of hers is running. On its own this is often innocent (a phone that restarted,
    a lost connection), so it is only recorded as information; it matters together with a device change."""
    if not enabled() or not user.is_student:
        return
    now = now or timezone.now()
    for attempt in Attempt.objects.filter(student=user, status=Attempt.IN_PROGRESS):
        raise_flag(attempt, IntegrityFlag.LOGIN_DURING_EXAM, IntegrityFlag.INFO,
                   {"platform": spoof.platform_of(ua), "ip": ip or ""}, now)


FLAG_TEXT = {
    IntegrityFlag.DEVICE_CHANGED: "is now sending from a different device than before",
    IntegrityFlag.LOGIN_DURING_EXAM: "logged in again while the exam was running (the first session ended)",
    IntegrityFlag.TELEPORT: "position jumped to another place faster than any vehicle could travel",
    IntegrityFlag.FROZEN: "position has not changed at all, not even by the normal GPS drift",
    IntegrityFlag.PERFECT: "reports a position accuracy that no phone can reach indoors",
    IntegrityFlag.ROUNDED: "position has round coordinates, typical of a location typed into a fake-location app",
}


def flag_text(f):
    """One plain sentence for the administrator's screen, built from the evidence kept in the flag."""
    d = f.detail or {}
    if f.kind == IntegrityFlag.DEVICE_CHANGED:
        a, b = d.get("at_start", {}), d.get("to", {})
        return (f"Started on {a.get('platform') or 'a device'} (code {a.get('device', '?')}); now sending from {b.get('platform') or 'a device'} "
                f"(code {b.get('device', '?')}){'' if a.get('ip') == b.get('ip') else ' on a different network'}.")
    if f.kind == IntegrityFlag.LOGIN_DURING_EXAM:
        return f"Logged in again from {d.get('platform') or 'a device'} during the exam."
    if f.kind == IntegrityFlag.TELEPORT:
        return f"Moved {d.get('distance_m', '?')} m in {d.get('seconds', '?')} s (about {d.get('speed_ms', '?')} m/s) while both positions were precise."
    if f.kind == IntegrityFlag.FROZEN:
        return f"Exactly the same position and accuracy (±{d.get('accuracy_m', '?')} m) in {d.get('reports', '?')} reports in a row."
    if f.kind == IntegrityFlag.PERFECT:
        return f"Accuracy of ±{d.get('accuracy_m', '?')} m in {d.get('reports', '?')} reports in a row."
    if f.kind == IntegrityFlag.ROUNDED:
        return f"Coordinates {d.get('lat')}, {d.get('lng')} have at most 4 decimals, {d.get('reports', '?')} reports in a row."
    return ""


def _notify_flag(flag):
    from notifications.services import notify
    admins = list(User.objects.filter(role__in=["admin", "super_admin"], is_active=True))
    body = (f"{name_of(flag.student)} {FLAG_TEXT[flag.kind]} during “{flag.exam.title}”. This is a sign to look at, not proof. "
            "Open Live monitor → Anti-cheat.")
    notify(admins, "integrity_alert", "Check this student", body, key=f"flag:{flag.pk}", data={"exam_id": flag.exam_id, "flag_id": flag.pk}, push=True)


def acknowledge_flag(flag, admin, now=None):
    if flag.acknowledged_at:
        return False
    flag.acknowledged_at, flag.acknowledged_by = now or timezone.now(), admin
    flag.save(update_fields=["acknowledged_at", "acknowledged_by"])
    audit(admin, "integrity_flag_reviewed", f"flag {flag.pk}", exam=flag.exam_id, student=flag.student_id, kind=flag.kind)
    return True


def _pair(x, y):
    return (x, y) if x.pk < y.pk else (y, x)


def evaluate(ll, now):
    """Compare this student with every other student of the same exam who has a fresh position, and open or refresh alerts."""
    cfg = SchoolSettings.load()
    limit, lock_on = float(cfg.proximity_alert_meters), bool(cfg.proximity_lock_enabled)
    dlat, dlng = geo.bbox(ll.lat, ll.lng, limit + 5)
    fresh = now - timedelta(seconds=stale_after())
    near = (LiveLocation.objects.filter(exam_id=ll.exam_id, attempt__status=Attempt.IN_PROGRESS, updated_at__gte=fresh,
                                        lat__range=(ll.lat - dlat, ll.lat + dlat), lng__range=(ll.lng - dlng, ll.lng + dlng))
            .exclude(student_id=ll.student_id).select_related("student"))
    new_alerts, newly_locked = [], []
    excused = related_ids(ll.student_id)  # twins, same house, same room: expected to be close, so no alert and never locked
    for other in near:
        if other.student_id in excused:
            continue
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
        # Only a precise position can lock a screen: a rough indoor fix could lock a student who is really far away, and her
        # exam clock keeps running while she is locked. Rough ("possible") alerts still go to the administrators.
        if lock_on and alert.confidence == ProximityAlert.CONFIRMED and _lock(alert, now):
            newly_locked.append(alert)
    if new_alerts:
        _notify_admins(new_alerts)
    later = [al for al in newly_locked if al not in new_alerts]  # the new ones already say "locked" in their own message
    if later:
        _notify_locked(later)
    close_stale_alerts(ll.exam_id, now)


def related_ids(student_id):
    """The ids of the students an administrator marked as related to this one."""
    rows = StudentRelation.objects.filter(Q(a_id=student_id) | Q(b_id=student_id)).values_list("a_id", "b_id")
    return {b if a == student_id else a for a, b in rows}


def relation_links(rows, limit):
    """For the map: the related pairs that are close together right now. `rows` are the board's student rows (dicts with id, lat,
    lng, fresh). Only pairs of which both have a fresh position and are closer than `limit` metres get a line."""
    pos = {r["id"]: r for r in rows if r.get("fresh")}
    if len(pos) < 2:
        return []
    ids = list(pos)
    out = []
    for rel in StudentRelation.objects.filter(a_id__in=ids, b_id__in=ids):
        p, q = pos[rel.a_id], pos[rel.b_id]
        d = geo.haversine_m(p["lat"], p["lng"], q["lat"], q["lng"])
        if d <= limit:
            out.append({"id": rel.pk, "a": rel.a_id, "b": rel.b_id, "kind": rel.kind, "label": rel.get_kind_display(),
                        "note": rel.note, "distance_m": round(d, 1)})
    return out


def mark_related(admin, ids, kind, note="", now=None):
    """Mark every pair among `ids` as related (twins, triplets, a whole household). Pairs that exist are updated. Alerts already open
    for these pairs are ended and their locks released, because the administrator has just said they are expected to be close.
    Returns the list of relations."""
    ids = sorted(set(ids))
    now = now or timezone.now()
    rels = []
    with transaction.atomic():
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                rel, created = StudentRelation.objects.get_or_create(a_id=x, b_id=y, defaults={"kind": kind, "note": note, "created_by": admin})
                if not created and (rel.kind != kind or rel.note != note):
                    rel.kind, rel.note = kind, note
                    rel.save(update_fields=["kind", "note"])
                rels.append(rel)
                for al in ProximityAlert.objects.filter(a_id=x, b_id=y).filter(Q(active=True) | Q(locked=True, unlocked_at__isnull=True)):
                    unlock(al, admin, now)
                    if al.active:
                        al.active, al.acknowledged_at, al.acknowledged_by = False, al.acknowledged_at or now, al.acknowledged_by or admin
                        al.save(update_fields=["active", "acknowledged_at", "acknowledged_by"])
    audit(admin, "student_relation_set", f"{len(rels)} pair(s)", students=ids, kind=kind)
    return rels


def _lock(alert, now):
    """Lock both students of this alert. Does nothing if it was locked before, or if an admin already unlocked it
    (so unlocking a pair that is still close does not lock them again at once). Returns True when it locked now."""
    if alert.locked:
        return False
    alert.locked, alert.locked_at = True, now
    alert.save(update_fields=["locked", "locked_at"])
    audit(None, "proximity_lock", f"alert {alert.pk}", exam=alert.exam_id, students=[alert.a_id, alert.b_id], distance_m=round(alert.last_distance, 1))
    return True


def locking_alert(exam_id, student_id):
    """The alert that keeps this student's exam locked, or None. A lock outlives the alert: it stays until an admin unlocks it.
    Switching the option off in Settings releases everybody."""
    if not lock_enabled():
        return None
    return (ProximityAlert.objects.filter(exam_id=exam_id, locked=True, unlocked_at__isnull=True)
            .filter(Q(a_id=student_id) | Q(b_id=student_id)).select_related("a", "b").first())


def is_locked(exam_id, student_id):
    return locking_alert(exam_id, student_id) is not None


def unlock(alert, admin, now=None):
    """An administrator lets the pair continue. Returns True if the pair was locked."""
    if not alert.locked or alert.unlocked_at:
        return False
    alert.unlocked_at, alert.unlocked_by = now or timezone.now(), admin
    alert.save(update_fields=["unlocked_at", "unlocked_by"])
    audit(admin, "proximity_unlock", f"alert {alert.pk}", exam=alert.exam_id, students=[alert.a_id, alert.b_id])
    return True


def unlock_all(exam_id, admin, now=None):
    n = 0
    for al in ProximityAlert.objects.filter(exam_id=exam_id, locked=True, unlocked_at__isnull=True).select_related("a", "b"):
        n += unlock(al, admin, now)
    return n


def close_stale_alerts(exam_id, now):
    return ProximityAlert.objects.filter(exam_id=exam_id, active=True, last_seen__lt=now - timedelta(seconds=clear_after())).update(active=False)


def _notify_admins(alerts):
    from notifications.services import notify
    admins = list(User.objects.filter(role__in=["admin", "super_admin"], is_active=True))
    for al in alerts:
        title = "Students sitting close together"
        body = (f"{name_of(al.a)} and {name_of(al.b)} are about {round(al.last_distance)} m apart during “{al.exam.title}”"
                f"{'' if al.confidence == ProximityAlert.CONFIRMED else ' (position is rough, please check)'}."
                f"{' Both exam screens are locked until you unlock them.' if al.locked else ''} Open Live monitor → Anti-cheat.")
        notify(admins, "integrity_alert", title, body, key=f"prox:{al.pk}", data={"exam_id": al.exam_id, "alert_id": al.pk}, push=True)


def _notify_locked(alerts):
    from notifications.services import notify
    admins = list(User.objects.filter(role__in=["admin", "super_admin"], is_active=True))
    for al in alerts:
        body = (f"{name_of(al.a)} and {name_of(al.b)} are now confirmed about {round(al.last_distance)} m apart during “{al.exam.title}”. "
                "Both exam screens are locked until you unlock them. Open Live monitor → Anti-cheat.")
        notify(admins, "integrity_alert", "Exam screens locked", body, key=f"lock:{al.pk}", data={"exam_id": al.exam_id, "alert_id": al.pk}, push=True)
