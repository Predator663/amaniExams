"""Small geodesy helpers. Distances use the haversine formula, which is accurate to well under a metre at 20 m."""
import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bbox(lat, lng, meters):
    """Degrees of latitude/longitude that cover `meters` around a point (used to pre-filter in the database)."""
    dlat = meters / 111_320.0
    dlng = meters / (111_320.0 * max(0.05, math.cos(math.radians(lat))))
    return dlat, dlng


# ---- pure decision rules (no database, so they can be tested on their own) ----

def valid_fix(lat, lng, accuracy):
    return (isinstance(lat, (int, float)) and isinstance(lng, (int, float)) and isinstance(accuracy, (int, float))
            and -90 <= lat <= 90 and -180 <= lng <= 180 and 0 <= accuracy <= 20_000
            and not (lat == 0 and lng == 0))


def has_moved(anchor, new, accuracy, floor_m=12.0):
    """True when `new` is further from the last still point than GPS jitter can explain.
    Indoors a phone can wander 5-15 m while lying on a desk, so the limit is max(12 m, reported accuracy)."""
    if not anchor:
        return False
    return haversine_m(anchor[0], anchor[1], new[0], new[1]) > max(floor_m, accuracy)


def classify_pair(distance_m, acc_a, acc_b, threshold_m, max_accuracy, sure_accuracy=25.0):
    """None = not an alert. 'confirmed' = both positions are precise enough that the distance can be trusted.
    'possible' = the distance is under the limit but at least one phone reported a rough position (indoors, weak sky view).
    A fix worse than `max_accuracy` is never compared, it would raise false alarms."""
    if acc_a > max_accuracy or acc_b > max_accuracy or distance_m >= threshold_m:
        return None
    return "confirmed" if max(acc_a, acc_b) <= sure_accuracy else "possible"
