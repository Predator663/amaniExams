"""Pure-logic tests (no database).  python -m unittest proctoring.test_geo"""
import unittest

from . import geo


def offset(lat, lng, north_m=0.0, east_m=0.0):
    import math
    return lat + north_m / 111_320.0, lng + east_m / (111_320.0 * math.cos(math.radians(lat)))


class GeoTests(unittest.TestCase):
    base = (-6.8, 39.25)  # Dar es Salaam

    def test_distance_is_accurate_at_20m(self):
        for n, e in [(20, 0), (0, 20), (14.142, 14.142), (-15, 13.2)]:
            p = offset(*self.base, n, e)
            self.assertAlmostEqual(geo.haversine_m(*self.base, *p), (n * n + e * e) ** 0.5, delta=0.3)

    def test_threshold_boundaries(self):
        near, edge, far = offset(*self.base, 19, 0), offset(*self.base, 20.5, 0), offset(*self.base, 35, 0)
        d = lambda p: geo.haversine_m(*self.base, *p)
        self.assertEqual(geo.classify_pair(d(near), 8, 10, 20, 100), "confirmed")
        self.assertIsNone(geo.classify_pair(d(edge), 8, 10, 20, 100))
        self.assertIsNone(geo.classify_pair(d(far), 8, 10, 20, 100))

    def test_rough_fix_is_possible_and_useless_fix_is_ignored(self):
        self.assertEqual(geo.classify_pair(10, 8, 60, 20, 100), "possible")
        self.assertIsNone(geo.classify_pair(10, 8, 400, 20, 100))

    def test_moved_ignores_gps_jitter_but_sees_walking(self):
        jitter = offset(*self.base, 6, 4)
        walked = offset(*self.base, 30, 0)
        self.assertFalse(geo.has_moved(self.base, jitter, 8))
        self.assertTrue(geo.has_moved(self.base, walked, 8))
        self.assertFalse(geo.has_moved(self.base, walked, 60))  # very rough fix: cannot tell
        self.assertFalse(geo.has_moved(None, walked, 8))

    def test_valid_fix(self):
        self.assertTrue(geo.valid_fix(-6.8, 39.2, 12))
        self.assertFalse(geo.valid_fix(0, 0, 5))  # the "null island" default of broken devices
        self.assertFalse(geo.valid_fix(91, 10, 5))
        self.assertFalse(geo.valid_fix("a", 10, 5))

    def test_bbox_covers_radius(self):
        dlat, dlng = geo.bbox(*self.base, 25)
        p = offset(*self.base, 24, 0)
        self.assertLess(abs(p[0] - self.base[0]), dlat)
        q = offset(*self.base, 0, 24)
        self.assertLess(abs(q[1] - self.base[1]), dlng)


class GeocodeParseTests(unittest.TestCase):
    def test_parse_dar_address(self):
        from .geocode import parse_address
        d = {"address": {"road": "Old Bagamoyo Road", "suburb": "Mikocheni", "city_district": "Kinondoni", "state": "Dar es Salaam", "country": "Tanzania"}}
        p = parse_address(d)
        self.assertEqual(p["label"], "Old Bagamoyo Road, Mikocheni, Kinondoni, Dar es Salaam, Tanzania")
        self.assertEqual((p["street"], p["district"], p["country"]), ("Old Bagamoyo Road", "Kinondoni", "Tanzania"))

    def test_parse_sparse_and_empty(self):
        from .geocode import parse_address
        self.assertEqual(parse_address({"address": {"village": "Usa River", "county": "Arumeru", "state": "Arusha", "country": "Tanzania"}})["label"],
                         "Usa River, Arumeru, Arusha, Tanzania")
        self.assertEqual(parse_address({"address": {"city": "Dar es Salaam", "state": "Dar es Salaam", "country": "Tanzania"}})["label"], "Dar es Salaam, Tanzania")  # no duplicate
        self.assertEqual(parse_address(None)["label"], "")


if __name__ == "__main__":
    unittest.main()
