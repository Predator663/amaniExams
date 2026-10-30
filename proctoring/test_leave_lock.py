"""Leaving the exam screen: counting, automatic lock over the limit, manual lock/unlock.  python manage.py test proctoring.test_leave_lock"""
from core.models import AuditLog, SchoolSettings
from exams.models import Attempt, AttemptEvent
from notifications.models import Notification
from .tests import ProximityBase


class LeaveLockTests(ProximityBase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()  # the event throttle counts per user in the cache; user ids repeat from test to test

    def cfg(self, **kw):
        s = SchoolSettings.load()
        for k, v in kw.items():
            setattr(s, k, v)
        s.save()

    def leave(self, user, attempt, n=1):
        r = None
        for _ in range(n):
            r = self.client_for(user).post(f"/api/attempts/{attempt.pk}/event/", {"kind": "left_screen"}, format="json")
            self.client_for(user).post(f"/api/attempts/{attempt.pk}/event/", {"kind": "returned"}, format="json")
        return r

    def answer(self, user, attempt):
        attempt.refresh_from_db()
        q = attempt.order[attempt.current_index]
        return self.client_for(user).post(f"/api/attempts/{attempt.pk}/answer/", {"question_id": q, "response": "A"}, format="json")

    def test_defaults_are_on_with_three(self):
        s = SchoolSettings.load()
        self.assertTrue(s.leave_lock_enabled)
        self.assertEqual(s.leave_lock_limit, 3)

    def test_three_exits_only_warn_the_fourth_locks(self):
        for i in (1, 2, 3):
            r = self.leave(self.amina, self.a_amina).json()
            self.assertEqual((r["locked"], r["left"], r["limit"]), (False, i, 3))
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        r = self.leave(self.zawadi, self.a_zawadi, 3).json()
        self.assertFalse(r["locked"])
        r = self.leave(self.amina, self.a_amina).json()  # her fourth
        self.assertEqual((r["locked"], r["lock_reason"], r["locked_now"]), (True, "leaves", True))
        a = self.answer(self.amina, self.a_amina)
        self.assertEqual((a.status_code, a.json()["code"]), (423, "locked"))
        st = self.client_for(self.amina).get(f"/api/attempts/{self.a_amina.pk}/").json()
        self.assertEqual((st["locked"], st["lock_reason"]), (True, "leaves"))
        self.assertEqual(self.answer(self.neema, self.a_neema).status_code, 200)  # others are not affected
        self.assertTrue(AuditLog.objects.filter(action="leave_lock").exists())
        self.assertEqual(Notification.objects.filter(kind="integrity_alert", title__icontains="left the screen").count(), 1)

    def test_the_limit_is_set_by_the_admin_and_validated(self):
        a = self.client_for(self.admin)
        r = a.patch("/api/settings/", {"leave_lock_limit": 1, "leave_lock_enabled": True}, format="json")
        self.assertEqual((r.status_code, r.json()["leave_lock_limit"]), (200, 1))
        for bad in (-1, 51, "x", None, True):
            self.assertEqual(a.patch("/api/settings/", {"leave_lock_limit": bad}, format="json").status_code, 400)
        self.assertEqual(a.patch("/api/settings/", {"leave_lock_enabled": "yes"}, format="json").status_code, 400)
        self.assertEqual(self.client_for(self.teacher).patch("/api/settings/", {"leave_lock_limit": 9}, format="json").status_code, 403)
        self.assertFalse(self.leave(self.amina, self.a_amina).json()["locked"])  # first exit is allowed
        self.assertTrue(self.leave(self.amina, self.a_amina).json()["locked"])  # second is over the limit of 1

    def test_switching_auto_lock_off_never_locks_and_releases(self):
        self.cfg(leave_lock_enabled=False)
        self.assertFalse(self.leave(self.amina, self.a_amina, 6).json()["locked"])
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        self.assertEqual(AttemptEvent.objects.filter(attempt=self.a_amina, kind="left_screen").count(), 6)  # still counted for the monitor
        self.cfg(leave_lock_enabled=True)
        self.leave(self.zawadi, self.a_zawadi, 4)
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 423)
        self.cfg(leave_lock_enabled=False)
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 200)

    def test_admin_unlock_gives_a_fresh_allowance(self):
        self.leave(self.amina, self.a_amina, 4)
        r = self.client_for(self.admin).post(f"/api/proctoring/attempts/{self.a_amina.pk}/unlock/")
        self.assertEqual((r.status_code, r.json()["unlocked"]), (200, True))
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        self.assertEqual(self.leave(self.amina, self.a_amina, 3).json()["locked"], False)  # three more are fine
        self.assertTrue(self.leave(self.amina, self.a_amina).json()["locked"])  # the fourth after the unlock locks again
        self.assertTrue(AuditLog.objects.filter(action="attempt_unlock").exists())

    def test_manual_lock_and_unlock_and_students_cannot_do_it(self):
        a = self.client_for(self.admin)
        self.assertEqual(self.client_for(self.amina).post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/").status_code, 403)
        self.assertEqual(self.client_for(self.teacher).post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/").status_code, 403)
        self.assertTrue(a.post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/").json()["locked"])
        self.assertFalse(a.post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/").json()["locked"])  # already locked
        st = self.client_for(self.amina).get(f"/api/attempts/{self.a_amina.pk}/").json()
        self.assertEqual((st["locked"], st["lock_reason"]), (True, "manual"))
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)
        self.cfg(leave_lock_enabled=False)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)  # a hand lock is not a setting: it stays
        self.assertTrue(a.post(f"/api/proctoring/attempts/{self.a_amina.pk}/unlock/").json()["unlocked"])
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)

    def test_manual_unlock_keeps_the_exits_already_used(self):
        self.leave(self.amina, self.a_amina, 2)
        a = self.client_for(self.admin)
        a.post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/")
        a.post(f"/api/proctoring/attempts/{self.a_amina.pk}/unlock/")
        self.assertFalse(self.leave(self.amina, self.a_amina).json()["locked"])  # 3rd exit
        self.assertTrue(self.leave(self.amina, self.a_amina).json()["locked"])  # 4th: the 2 earlier exits still count

    def test_location_report_carries_the_lock_even_with_position_checks_off(self):
        self.leave(self.amina, self.a_amina, 4)
        with self.settings(PROCTORING_ENABLED=False):
            r = self.client_for(self.amina).post(f"/api/attempts/{self.a_amina.pk}/location/", {"lat": -6.8, "lng": 39.25, "accuracy": 8}, format="json").json()
        self.assertEqual((r["locked"], r["lock_reason"]), (True, "leaves"))

    def test_monitor_shows_counts_and_lock(self):
        self.leave(self.amina, self.a_amina, 2)
        self.leave(self.zawadi, self.a_zawadi, 4)
        b = self.client_for(self.admin).get("/api/exams/monitor-board/").json()
        ex = next(e for e in b["exams"] if e["exam_id"] == self.exam.pk)
        self.assertEqual(ex["leave_lock"], {"enabled": True, "limit": 3})
        rows = {r["id"]: r for r in ex["in_progress_students"]}
        self.assertEqual((rows[self.amina.pk]["leaves_used"], rows[self.amina.pk]["locked"]), (2, False))
        self.assertEqual((rows[self.zawadi.pk]["leaves_used"], rows[self.zawadi.pk]["locked"], rows[self.zawadi.pk]["lock_reason"]), (4, True, "leaves"))
        self.assertEqual(rows[self.zawadi.pk]["attempt_id"], self.a_zawadi.pk)

    def test_unlock_all_releases_leave_locks_too(self):
        self.leave(self.amina, self.a_amina, 4)
        self.client_for(self.admin).post(f"/api/proctoring/attempts/{self.a_zawadi.pk}/lock/")
        r = self.client_for(self.admin).post(f"/api/proctoring/exams/{self.exam.pk}/unlock-all/")
        self.assertEqual(r.json()["unlocked"], 2)
        self.assertFalse(Attempt.objects.exclude(screen_lock="").exists())

    def test_finished_attempts_are_not_locked_or_counted(self):
        from exams import services
        services.finalize_attempt(self.a_amina.pk)
        r = self.client_for(self.amina).post(f"/api/attempts/{self.a_amina.pk}/event/", {"kind": "left_screen"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AttemptEvent.objects.filter(attempt=self.a_amina).exists())
        self.assertEqual(self.client_for(self.admin).post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/").status_code, 409)


class SecurityPatchTests(ProximityBase):
    """Audit fixes: question withheld while locked, event throttle, masked parent phones, admin-only anti-cheat settings."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def test_locked_student_gets_no_question_text(self):
        r = self.client_for(self.amina).get(f"/api/attempts/{self.a_amina.pk}/")
        self.assertIsNotNone(r.json()["question"])
        self.client_for(self.admin).post(f"/api/proctoring/attempts/{self.a_amina.pk}/lock/")
        r = self.client_for(self.amina).get(f"/api/attempts/{self.a_amina.pk}/")
        self.assertTrue(r.json()["locked"])
        self.assertIsNone(r.json()["question"])
        self.client_for(self.admin).post(f"/api/proctoring/attempts/{self.a_amina.pk}/unlock/")
        self.assertIsNotNone(self.client_for(self.amina).get(f"/api/attempts/{self.a_amina.pk}/").json()["question"])

    def test_event_endpoint_is_throttled(self):
        codes = [self.client_for(self.amina).post(f"/api/attempts/{self.a_amina.pk}/event/", {"kind": "returned"}, format="json").status_code
                 for _ in range(35)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 200)

    def test_anticheat_settings_hidden_from_students(self):
        s = self.client_for(self.amina).get("/api/settings/").json()
        for f in ("proximity_alert_meters", "proximity_lock_enabled", "leave_lock_enabled", "leave_lock_limit"):
            self.assertNotIn(f, s)
        a = self.client_for(self.admin).get("/api/settings/").json()
        for f in ("proximity_alert_meters", "proximity_lock_enabled", "leave_lock_enabled", "leave_lock_limit"):
            self.assertIn(f, a)

    def test_mask_phone(self):
        from exams.views import mask_phone
        self.assertEqual(mask_phone("+255712345678"), "+255••••••678")
        self.assertNotIn("1234", mask_phone("0712345678"))
        self.assertTrue(mask_phone("0712345678").endswith("678"))
        self.assertEqual(mask_phone(""), "")
