"""Pure tests of the fake-position and device checks (no database).  python manage.py test proctoring.test_spoof"""
import math
import unittest

from . import spoof

LAT, LNG = -6.8, 39.25


def fix(north_m=0.0, acc=8.0):
    return (LAT + north_m / 111_320.0, LNG, acc)


class Teleport(unittest.TestCase):
    def test_far_jump_in_seconds_is_flagged(self):
        r = spoof.teleport(fix(0), fix(5000), 6)
        self.assertAlmostEqual(r["distance_m"], 5000, delta=30)
        self.assertEqual(r["seconds"], 6)
        self.assertGreater(r["speed_ms"], 800)

    def test_normal_movement_and_wobble_are_not(self):
        self.assertIsNone(spoof.teleport(fix(0), fix(30), 6))      # a walk or GPS wobble
        self.assertIsNone(spoof.teleport(fix(0), fix(250), 6))     # under the minimum jump
        self.assertIsNone(spoof.teleport(fix(0), fix(1000), 120))  # 8 m/s: a bus or boda-boda

    def test_rough_fixes_never_count(self):
        # switching between a satellite fix and a rough network fix jumps by kilometres in real life
        self.assertIsNone(spoof.teleport(fix(0, acc=8), fix(5000, acc=900), 6))
        self.assertIsNone(spoof.teleport(fix(0, acc=300), fix(5000, acc=8), 6))

    def test_old_or_missing_previous_position_says_nothing(self):
        self.assertIsNone(spoof.teleport(None, fix(5000), 6))
        self.assertIsNone(spoof.teleport(fix(0), fix(50000), 3600))
        self.assertIsNone(spoof.teleport(fix(0), fix(5000), 0))


class Counters(unittest.TestCase):
    def run_stream(self, stream):
        counts, prev, out = {}, None, []
        for f in stream:
            counts = spoof.next_counters(counts, prev, f)
            out.extend(k for k, _ in spoof.episodes(counts, f))
            prev = f
        return out

    def test_real_gps_drift_raises_nothing(self):
        stream = [(LAT + math.sin(i) * 3e-6 + 1.234567e-7 * i, LNG + math.cos(i) * 3e-6, 5.0 + (i % 4) * 0.7) for i in range(60)]
        self.assertEqual(self.run_stream(stream), [])

    def test_frozen_position_is_flagged_once_per_streak(self):
        f = (LAT + 1.2345678e-5, LNG + 2.3456789e-5, 6.0)
        self.assertEqual(self.run_stream([f] * (spoof.FROZEN_REPORTS + 1)), ["frozen_fix"])
        self.assertEqual(self.run_stream([f] * 40), ["frozen_fix"])  # not again for the same streak

    def test_frozen_but_rough_is_ignored(self):
        f = (LAT + 1.2345678e-5, LNG + 2.3456789e-5, 600.0)  # a laptop located by Wi-Fi often repeats a rough position
        self.assertEqual(self.run_stream([f] * 20), [])

    def test_impossible_accuracy(self):
        stream = [(LAT + i * 1e-6, LNG + i * 1.3e-6, 1.0) for i in range(spoof.PERFECT_REPORTS)]
        self.assertEqual(self.run_stream(stream), ["perfect_accuracy"])
        self.assertEqual(self.run_stream(stream[:2]), [])

    def test_typed_in_coordinates(self):
        stream = [(-6.8, 39.25, 10.0), (-6.8001, 39.2501, 10.0), (-6.8002, 39.2502, 12.0)]
        self.assertEqual(self.run_stream(stream), ["rounded_coords"])
        self.assertEqual(self.run_stream([(-6.8123457, 39.2512345, 10.0)] * 2 + [(-6.8, 39.25, 10.0)]), [])

    def test_streak_is_broken_by_a_different_report(self):
        f = (LAT + 1.2345678e-5, LNG + 2.3456789e-5, 6.0)
        g = (LAT + 1.3345678e-5, LNG + 2.3456789e-5, 6.0)
        self.assertEqual(self.run_stream(([f] * 5 + [g]) * 3), [])


class Devices(unittest.TestCase):
    def test_platforms(self):
        self.assertEqual(spoof.platform_of("Mozilla/5.0 (Linux; Android 13; TECNO) Chrome/118"), "Android")
        self.assertEqual(spoof.platform_of("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"), "iPhone/iPad")
        self.assertEqual(spoof.platform_of("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"), "Windows")
        self.assertEqual(spoof.platform_of("Mozilla/5.0 (X11; Linux x86_64)"), "Linux")
        self.assertEqual(spoof.platform_of(""), "Unknown")

    def test_device_id_is_cleaned(self):
        self.assertEqual(spoof.clean_device("0a1b2c3d-4e5f-6789"), "0a1b2c3d-4e5f-6789")
        for bad in ("", "short", "has space in it!", "x" * 80, None, 12345, {"a": 1}):
            self.assertEqual(spoof.clean_device(bad), "")

    def test_first_report_sets_the_device_and_a_change_is_seen_once_per_switch(self):
        d, ch = spoof.track_device(None, "aaaaaaaa", "Android", "1.1.1.1")
        self.assertIsNone(ch)
        d, ch = spoof.track_device(d, "aaaaaaaa", "Android", "1.1.1.1")
        self.assertIsNone(ch)
        d, ch = spoof.track_device(d, "bbbbbbbb", "Windows", "2.2.2.2")
        self.assertEqual((ch["from"]["id"], ch["to"]["id"], ch["first"]["id"]), ("aaaaaaaa", "bbbbbbbb", "aaaaaaaa"))
        d, ch = spoof.track_device(d, "bbbbbbbb", "Windows", "2.2.2.2")
        self.assertIsNone(ch)  # still the new device: no second change
        self.assertEqual(spoof.track_device(d, "", "Android", "1.1.1.1")[1], None)  # an old client that sends no id is ignored

    def test_severity(self):
        base = {"id": "aaaaaaaa", "platform": "Android", "ip": "1.1.1.1"}
        same = {"id": "bbbbbbbb", "platform": "Android", "ip": "1.1.1.1"}
        self.assertEqual(spoof.change_severity({"first": base, "from": base, "to": same}), "warning")
        self.assertEqual(spoof.change_severity({"first": base, "from": base, "to": {**same, "platform": "Windows"}}), "high")
        self.assertEqual(spoof.change_severity({"first": base, "from": base, "to": {**same, "ip": "9.9.9.9"}}), "high")
        self.assertEqual(spoof.change_severity({"first": base, "from": base, "to": {**same, "platform": "Unknown"}}), "warning")
