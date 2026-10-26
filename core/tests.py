from django.contrib.auth.hashers import make_password

from analytics.tests import AnalyticsBase
from core import grading
from core.models import SchoolSettings, audit


class SettingsAndAuditTests(AnalyticsBase):
    def test_only_admins_change_settings(self):
        self.assertEqual(self.client_for(self.amina).patch("/api/settings/", {"school_name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client_for(self.amina).get("/api/settings/").status_code, 200)

    def test_settings_are_validated(self):
        a = self.client_for(self.admin)
        r = a.patch("/api/settings/", {"result_delay_minutes": 10, "late_entry_minutes": 15, "default_theme": "soft"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SchoolSettings.load().result_delay_minutes, 10)
        bad = a.patch("/api/settings/", {"result_delay_minutes": -1, "default_theme": "neon", "leaderboard_enabled": "yes"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(bad.json()["errors"]), {"result_delay_minutes", "default_theme", "leaderboard_enabled"})

    def test_grade_scale_edit_is_checked_for_gaps(self):
        a = self.client_for(self.admin)
        scale = grading.normalize_scale(grading.DEFAULT_SCALE)
        scale["grades"][1]["min"] = 60  # gap between C and B
        r = a.patch("/api/settings/", {"grade_scale": scale}, format="json")
        self.assertEqual(r.status_code, 400)
        scale = grading.normalize_scale(grading.DEFAULT_SCALE)
        scale["grades"][0]["min"] = 80  # A from 80; B must now reach up to 79
        scale["grades"][1]["max"] = 79
        self.assertEqual(a.patch("/api/settings/", {"grade_scale": scale}, format="json").status_code, 200)
        self.assertEqual(grading.grade_for(78, SchoolSettings.load().grade_scale)["grade"], "B")

    def test_audit_log_filters_and_paging(self):
        audit(self.admin, "student.create", 1)
        audit(self.admin, "password.reset", 2)
        a = self.client_for(self.admin)
        d = a.get("/api/audit-log/?action=password").json()
        self.assertEqual((d["count"], d["results"][0]["action"]), (1, "password.reset"))
        self.assertEqual(len(a.get("/api/audit-log/?limit=1").json()["results"]), 1)
        self.assertEqual(self.client_for(self.teacher).get("/api/audit-log/").status_code, 403)


class PresenceTests(AnalyticsBase):
    """The online counter: numbers only for students (BR-08), one key per student so heartbeats never overwrite each other."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def test_heartbeats_count_each_student_and_show_a_number_only(self):
        from core.views import online_ids
        self.client_for(self.amina).post("/api/presence/", {}, format="json")
        r = self.client_for(self.zawadi).post("/api/presence/", {}, format="json")
        self.assertEqual(set(r.json()), {"online"})            # a number, never names
        self.assertEqual(online_ids(), {self.amina.pk, self.zawadi.pk})

    def test_old_heartbeat_expires_and_get_does_not_count_as_a_heartbeat(self):
        from django.core.cache import cache
        from core.views import _heartbeat_key, online_ids
        cache.set(_heartbeat_key(self.amina.pk), 1.0, 600)      # a heartbeat from 1970
        self.client_for(self.zawadi).get("/api/presence/")
        self.assertEqual(online_ids(), set())
