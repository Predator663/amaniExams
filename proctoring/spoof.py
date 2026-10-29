"""Signs that a reported position is not a real GPS reading, and device bookkeeping. Pure functions (no database), so they are
easy to test. Nothing here proves cheating: every result is a flag for an administrator to look at.

What a real phone does: even when it lies on a desk its GPS position drifts a little from one report to the next, the reported
accuracy changes by a metre or two, coordinates carry many decimals, and it never reaches 1 m accuracy indoors. A typical
fake-location app does the opposite: the same position forever, a perfect accuracy, coordinates typed in by hand, or a sudden
jump to another place."""
import re

from . import geo

MAX_SPEED_MS = 50.0        # ~180 km/h: faster than a car can plausibly go between two reports
JUMP_MIN_M = 300.0         # smaller jumps are normal GPS wobble or a switch between Wi-Fi and satellite positioning
GOOD_ACC_M = 50.0          # a jump only counts when BOTH positions were precise (rough network fixes jump around a lot)
STALE_PREV_S = 600         # a previous position older than this says nothing about the present
FROZEN_ACC_M = 25.0        # "frozen" only matters for a position that claims to be precise
FROZEN_REPORTS = 8         # ~50 seconds with exactly the same position and accuracy
PERFECT_ACC_M = 1.5        # no phone reaches this indoors
PERFECT_REPORTS = 3
ROUND_ACC_M = 50.0
ROUND_REPORTS = 3          # coordinates with at most 4 decimals (an 11 m grid) three times in a row
ROUND_DECIMALS = 4

TELEPORT, FROZEN, PERFECT, ROUNDED = "teleport", "frozen_fix", "perfect_accuracy", "rounded_coords"


def teleport(prev, new, dt):
    """prev/new = (lat, lng, accuracy); dt = seconds between them. Returns {"distance_m", "seconds", "speed_ms"} or None."""
    if prev is None or dt is None or dt <= 0 or dt > STALE_PREV_S:
        return None
    if prev[2] > GOOD_ACC_M or new[2] > GOOD_ACC_M:
        return None
    d = geo.haversine_m(prev[0], prev[1], new[0], new[1])
    if d < max(JUMP_MIN_M, 3 * (prev[2] + new[2])):
        return None
    speed = d / dt
    if speed < MAX_SPEED_MS:
        return None
    return {"distance_m": round(d), "seconds": round(dt), "speed_ms": round(speed)}


def _is_round(v):
    return round(v, ROUND_DECIMALS) == v


def next_counters(counts, prev, new):
    """Consecutive-report counters, updated with the new position. counts = {"same", "perfect", "round"}."""
    counts = counts or {}
    lat, lng, acc = new
    same = prev is not None and prev[0] == lat and prev[1] == lng and prev[2] == acc
    return {
        "same": counts.get("same", 0) + 1 if same else 0,
        "perfect": counts.get("perfect", 0) + 1 if acc < PERFECT_ACC_M else 0,
        "round": counts.get("round", 0) + 1 if (_is_round(lat) and _is_round(lng) and acc <= ROUND_ACC_M) else 0,
    }


def episodes(counters, new):
    """Which signs have just reached their limit with this report (each streak is reported once, when it reaches the limit)."""
    acc = new[2]
    out = []
    if counters["same"] == FROZEN_REPORTS and acc <= FROZEN_ACC_M:
        out.append((FROZEN, {"reports": FROZEN_REPORTS, "accuracy_m": round(acc, 1)}))
    if counters["perfect"] == PERFECT_REPORTS:
        out.append((PERFECT, {"reports": PERFECT_REPORTS, "accuracy_m": round(acc, 2)}))
    if counters["round"] == ROUND_REPORTS:
        out.append((ROUNDED, {"reports": ROUND_REPORTS, "lat": new[0], "lng": new[1]}))
    return out


# ------------------------------------------------------------------ devices

_DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def clean_device(raw):
    """The random id the browser made for itself. Anything else is ignored."""
    return raw if isinstance(raw, str) and _DEVICE_RE.match(raw) else ""


def platform_of(ua):
    u = (ua or "").lower()
    if "android" in u:
        return "Android"
    if "iphone" in u or "ipad" in u or "ipod" in u:
        return "iPhone/iPad"
    if "windows" in u:
        return "Windows"
    if "cros" in u:
        return "ChromeOS"
    if "mac os" in u or "macintosh" in u:
        return "Mac"
    if "linux" in u:
        return "Linux"
    return "Unknown"


def track_device(devices, device, platform, ip):
    """devices = {"first": {...}, "last": {...}} kept on the attempt. Returns (devices, change or None).
    A change is reported when this report comes from another device than the previous one."""
    if not device:
        return devices or {}, None
    cur = {"id": device, "platform": platform, "ip": ip or ""}
    if not devices or not devices.get("first"):
        return {"first": cur, "last": cur}, None
    last = devices.get("last") or devices["first"]
    change = None
    if last["id"] != device:
        change = {"from": last, "to": cur, "first": devices["first"]}
    return {"first": devices["first"], "last": cur}, change


def change_severity(change):
    """High when the other device is a different kind of device or on a different network; otherwise a warning, because the same
    phone can show a new id after the browser's data was cleared, or when the installed app and the browser are mixed up."""
    a, b = change["first"], change["to"]
    other_platform = a["platform"] != b["platform"] and "Unknown" not in (a["platform"], b["platform"])
    other_net = bool(a["ip"] and b["ip"] and a["ip"] != b["ip"])
    return "high" if (other_platform or other_net) else "warning"
