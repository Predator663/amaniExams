"""Place names for positions (street, district, region, country), shown to administrators only.

A phone position is just two numbers; turning it into a street name needs a reverse-geocoding service. By default this asks the
public OpenStreetMap Nominatim service, or any Nominatim-compatible server the school hosts (GEOCODER_URL). Only rounded
coordinates are sent: no names, no exam, no student identity. Answers are cached for 30 days by a ~11 m grid cell, requests are
limited to one per second (Nominatim's usage policy), and failures are remembered briefly so a down service is not hammered.
Set GEOCODER_URL="" to switch place names off completely, then nothing leaves the school's server."""
import json
import logging
import urllib.parse
import urllib.request


log = logging.getLogger(__name__)
TTL = 30 * 24 * 3600


def enabled():
    from django.conf import settings
    return bool(getattr(settings, "GEOCODER_URL", ""))


def _first(a, *keys):
    for k in keys:
        if a.get(k):
            return a[k]
    return ""


def parse_address(data):
    """Nominatim JSON -> {street, area, district, region, country, label}. Pure function, easy to test."""
    a = (data or {}).get("address") or {}
    street = _first(a, "road", "pedestrian", "footway", "path", "residential", "track")
    area = _first(a, "neighbourhood", "suburb", "quarter", "village", "hamlet")
    district = _first(a, "city_district", "county", "state_district", "municipality", "city", "town")
    region = _first(a, "state", "region")
    country = a.get("country", "")
    parts = []
    for p in (street, area, district, region, country):
        if p and p not in parts:
            parts.append(p)
    return {"street": street, "area": area, "district": district, "region": region, "country": country, "label": ", ".join(parts)}


def _key(lat, lng):
    return f"geo:{round(lat, 4)}:{round(lng, 4)}"


def reverse(lat, lng):
    """Place for a position, or None when switched off, rate-limited, or the service is unreachable."""
    from django.conf import settings
    from django.core.cache import cache
    if not enabled():
        return None
    key = _key(lat, lng)
    hit = cache.get(key)
    if hit is not None:
        return hit or None  # {} = "known to have no answer"
    if not cache.add("geo:lock", 1, 1):  # one request per second; the page asks again on its next refresh
        return None
    q = urllib.parse.urlencode({"format": "jsonv2", "lat": f"{round(lat, 4):.4f}", "lon": f"{round(lng, 4):.4f}", "zoom": 18,
                                "addressdetails": 1, "accept-language": "en"})
    req = urllib.request.Request(f"{settings.GEOCODER_URL}?{q}", headers={"User-Agent": getattr(settings, "GEOCODER_USER_AGENT", "AmaniExams")})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            place = parse_address(json.loads(r.read().decode("utf-8")))
    except Exception as e:
        log.warning("reverse geocoding failed: %s", e)
        cache.set(key, {}, 60)
        return None
    cache.set(key, place if place["label"] else {}, TTL)
    return place if place["label"] else None
