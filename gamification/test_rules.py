"""Tests for the pure gamification rules. They need NO Django, so run them anywhere:

    python -m unittest gamification.test_rules            (from the project folder)

(The Django-based tests are in gamification/tests.py and run with `python manage.py test`.)"""
import unittest
from datetime import date, timedelta

from . import catalog, rules

D = date(2026, 10, 1)  # a Thursday; October has 31 days


def days(*offsets):
    return [D + timedelta(days=o) for o in offsets]


class XPTests(unittest.TestCase):
    def test_score_xp_is_one_per_percent_capped(self):
        self.assertEqual(rules.score_xp(0), 0)
        self.assertEqual(rules.score_xp(72.4), 72)
        self.assertEqual(rules.score_xp(72.5), 73)  # half rounds up
        self.assertEqual(rules.score_xp(100), 100)
        self.assertEqual(rules.score_xp(100, per_percent=2, cap=100), 100)  # cap holds
        self.assertEqual(rules.score_xp(50, per_percent=0), 0)

    def test_defaults_match_the_srs_table(self):
        x = rules.DEFAULT_XP
        self.assertEqual((x["submit_exam"], x["finish_early"], x["improvement"], x["perfect_score"]), (50, 10, 30, 100))
        self.assertEqual((x["review_wrong"], x["practice_quiz"]), (10, 20))
        self.assertEqual([x[f"streak_{n}"] for n in rules.STREAK_MILESTONES], [15, 50, 100, 250])


class LevelTests(unittest.TestCase):
    def test_srs_thresholds(self):
        names = {0: "Beginner", 199: "Beginner", 200: "Learner", 499: "Learner", 500: "Achiever", 999: "Achiever",
                 1000: "Scholar", 1999: "Scholar", 2000: "Star", 3499: "Star", 3500: "Champion", 4999: "Champion",
                 5000: "Genius", 99999: "Genius"}
        for xp, name in names.items():
            self.assertEqual(rules.level_for(xp)["name"], name, xp)

    def test_progress_to_next(self):
        lv = rules.level_for(350)  # level 2 (200) -> level 3 (500)
        self.assertEqual((lv["level"], lv["next_level"], lv["xp_to_next"], lv["progress_percent"]), (2, 3, 150, 50.0))
        top = rules.level_for(6000)
        self.assertEqual((top["level"], top["next_level"], top["xp_to_next"], top["progress_percent"]), (7, None, 0, 100.0))

    def test_negative_and_unsorted_input_are_safe(self):
        self.assertEqual(rules.level_for(-5)["level"], 1)
        self.assertEqual(rules.level_for(250, list(reversed(rules.DEFAULT_LEVELS)))["level"], 2)

    def test_swahili_name(self):
        self.assertEqual(rules.level_for(5000)["name_sw"], "Kipanga")


class StreakTests(unittest.TestCase):
    def test_consecutive_days(self):
        runs, used = rules.compute_runs(days(0, 1, 2, 3))
        self.assertEqual([(r["length"], r["frozen"]) for r in runs], [(4, [])])
        self.assertEqual(sum(used.values()), 0)

    def test_order_and_duplicates_do_not_matter(self):
        a, _ = rules.compute_runs(days(3, 0, 1, 1, 2))
        b, _ = rules.compute_runs(days(0, 1, 2, 3))
        self.assertEqual(a, b)

    def test_one_missed_day_is_protected_by_a_freeze_and_adds_nothing(self):
        runs, used = rules.compute_runs(days(0, 1, 3, 4))  # day 2 missed
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["length"], 4)  # frozen day is protected, not counted
        self.assertEqual(runs[0]["frozen"], [D + timedelta(days=2)])
        self.assertEqual(used[(2026, 10)], 1)

    def test_only_two_freezes_per_month(self):
        # days 0,1 then missing 2; 3; missing 4; 5; missing 6 (third freeze in October -> breaks)
        runs, used = rules.compute_runs(days(0, 1, 3, 5, 7))
        self.assertEqual([r["length"] for r in runs], [4, 1])
        self.assertEqual(used[(2026, 10)], 2)

    def test_gap_is_all_or_nothing(self):
        # a 3-day gap needs 3 freezes; only 2 exist, so none are spent and the streak restarts
        runs, used = rules.compute_runs(days(0, 1, 5, 6))
        self.assertEqual([r["length"] for r in runs], [2, 2])
        self.assertEqual(sum(used.values()), 0)

    def test_freezes_reset_each_month(self):
        # Oct 30 and Nov 3 with Oct 31, Nov 1, Nov 2 missed: 1 freeze in Oct, 2 in Nov -> all covered
        oct30 = date(2026, 10, 30)
        runs, used = rules.compute_runs([oct30, date(2026, 11, 3)])
        self.assertEqual([r["length"] for r in runs], [2])
        self.assertEqual((used[(2026, 10)], used[(2026, 11)]), (1, 2))

    def test_custom_freeze_allowance(self):
        runs, _ = rules.compute_runs(days(0, 4), free_per_month=3)
        self.assertEqual([r["length"] for r in runs], [2])
        runs, _ = rules.compute_runs(days(0, 4), free_per_month=2)
        self.assertEqual([r["length"] for r in runs], [1, 1])
        runs, _ = rules.compute_runs(days(0, 2), free_per_month=0)
        self.assertEqual([r["length"] for r in runs], [1, 1])

    def test_status_alive_when_learned_today_or_yesterday(self):
        s = rules.streak_status(days(0, 1, 2), D + timedelta(days=2))
        self.assertEqual((s["current"], s["best"], s["active_today"], s["at_risk"]), (3, 3, True, False))
        s = rules.streak_status(days(0, 1, 2), D + timedelta(days=3))  # not yet today: still alive, at risk
        self.assertEqual((s["current"], s["active_today"], s["at_risk"]), (3, False, True))

    def test_status_survives_gap_that_freezes_cover_and_breaks_otherwise(self):
        s = rules.streak_status(days(0, 1, 2), D + timedelta(days=5))  # missed days 3, 4 -> two freezes
        self.assertEqual((s["current"], s["freezes_left_this_month"]), (3, 0))
        s = rules.streak_status(days(0, 1, 2), D + timedelta(days=6))  # missed 3, 4, 5 -> not coverable
        self.assertEqual((s["current"], s["best"], s["at_risk"]), (0, 3, False))

    def test_status_with_no_days(self):
        s = rules.streak_status([], D)
        self.assertEqual((s["current"], s["best"], s["freezes_left_this_month"]), (0, 0, 2))

    def test_best_streak_survives_a_break(self):
        s = rules.streak_status(days(0, 1, 2, 3, 4, 20), D + timedelta(days=20))
        self.assertEqual((s["current"], s["best"]), (1, 5))

    def test_exam_streak(self):
        self.assertEqual(rules.exam_streak([True, True, False, True, True, True]), (3, 3))
        self.assertEqual(rules.exam_streak([True, True, True, False]), (0, 3))
        self.assertEqual(rules.exam_streak([]), (0, 0))


class BadgeTests(unittest.TestCase):
    def test_tiers(self):
        th = [7, 14, 30]
        self.assertEqual([rules.tier_for(v, th) for v in (0, 6, 7, 13, 14, 29, 30, 99)], [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertEqual((rules.next_target(7, th), rules.next_target(30, th)), (14, None))

    def test_comebacks(self):
        self.assertEqual(rules.count_comebacks([40, 55, 50, 70]), 2)   # +15 counts, +20 counts
        self.assertEqual(rules.count_comebacks([40, 54.9]), 0)
        self.assertEqual(rules.count_comebacks([80]), 0)

    def test_top_grade_uses_the_scale_snapshot(self):
        scale = {"grades": [{"grade": "A", "points": 1}, {"grade": "B", "points": 2}, {"grade": "F", "points": 5}]}
        self.assertTrue(rules.is_top_grade(1, scale))
        self.assertFalse(rules.is_top_grade(2, scale))
        self.assertEqual(rules.second_best_points(scale), 2)

    def test_catalogue_matches_the_srs(self):
        codes = {b["code"] for b in catalog.BADGES}
        self.assertEqual(codes, {"first_steps", "perfect_score", "comeback_kid", "on_fire", "subject_star", "all_rounder",
                                 "steady_pace", "mistake_master", "always_on_time", "practice_pro"})
        self.assertEqual(catalog.BY_CODE["practice_pro"]["tiers"][0], 50)
        self.assertEqual(catalog.BY_CODE["always_on_time"]["tiers"][0], 5)
        self.assertEqual(catalog.BY_CODE["on_fire"]["tiers"], [7, 14, 30])
        for b in catalog.BADGES:  # tiers go up; every text exists in both languages
            self.assertEqual(b["tiers"], sorted(set(b["tiers"])))
            self.assertEqual(len(b["tiers"]), 3)
            for key in ("name", "desc", "unit"):
                self.assertTrue(all(b[key]), (b["code"], key))

    def test_gold_on_fire_is_unstoppable(self):
        self.assertEqual(catalog.badge_name("on_fire", "en", 3), "Unstoppable")
        self.assertEqual(catalog.badge_name("on_fire", "en", 1), "On Fire")
        self.assertEqual(catalog.badge_name("on_fire", "sw", 3), "Hazuiliki")
        self.assertEqual(catalog.tier_label(2, "sw"), "Fedha")


class SettingsValidationTests(unittest.TestCase):
    def test_xp_validation(self):
        clean, problems = rules.validate_xp({"submit_exam": 60, "practice_quiz": 25})
        self.assertEqual((clean, problems), ({"submit_exam": 60, "practice_quiz": 25}, []))
        _, problems = rules.validate_xp({"submit_exam": -1, "nonsense": 5, "perfect_score": "100", "finish_early": True})
        self.assertEqual(len(problems), 4)
        self.assertTrue(rules.validate_xp([1])[1])

    def test_level_validation(self):
        clean, problems = rules.validate_levels([{"name": "A", "xp": 0}, {"name": "B", "xp": 100, "name_sw": "Bee"}])
        self.assertEqual(problems, [])
        self.assertEqual(clean[1], {"level": 2, "name": "B", "xp": 100, "name_sw": "Bee"})
        self.assertTrue(rules.validate_levels([{"name": "A", "xp": 5}, {"name": "B", "xp": 100}])[1])      # must start at 0
        self.assertTrue(rules.validate_levels([{"name": "A", "xp": 0}, {"name": "B", "xp": 0}])[1])        # must increase
        self.assertTrue(rules.validate_levels([{"name": "A", "xp": 0}])[1])                                 # at least two
        self.assertTrue(rules.validate_levels([{"name": "", "xp": 0}, {"name": "B", "xp": 10}])[1])        # name needed
        self.assertTrue(rules.validate_levels("x")[1])
        self.assertEqual(rules.validate_levels(rules.DEFAULT_LEVELS)[1], [])

    def test_tier_validation(self):
        codes = {"practice_pro"}
        self.assertEqual(rules.validate_tiers({"practice_pro": [10, 20, 30]}, codes), ({"practice_pro": [10, 20, 30]}, []))
        for bad in ([10, 10, 30], [10, 20], [0, 5, 9], ["a", 2, 3], [True, 2, 3]):
            self.assertTrue(rules.validate_tiers({"practice_pro": bad}, codes)[1], bad)
        self.assertTrue(rules.validate_tiers({"unknown": [1, 2, 3]}, codes)[1])


if __name__ == "__main__":
    unittest.main()
