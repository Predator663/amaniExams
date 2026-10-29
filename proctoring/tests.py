"""Anti-cheat proximity tests.  python manage.py test proctoring"""
import math
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from exams import services
from exams.models import Attempt
from exams.tests import Base
from notifications.models import Notification
from .models import LegalAcceptance, LiveLocation, ProximityAlert

LAT, LNG = -6.8, 39.25


def at(north_m=0.0, east_m=0.0, acc=8):
    return {"lat": LAT + north_m / 111_320.0, "lng": LNG + east_m / (111_320.0 * math.cos(math.radians(LAT))), "accuracy": acc}


class ProximityBase(Base):
    def setUp(self):
        super().setUp()
        self.neema = User.objects.create(username="neema", role="student", school_class=self.cls,
                                         password=make_password("pw-neema-1"), index_number="S3")
        self.teacher = User.objects.create(username="mwl", role="teacher", password=make_password("T3acher-pass!"))
        self.a_amina = services.start_attempt(self.exam, self.amina, now=self.at(1))
        self.a_zawadi = services.start_attempt(self.exam, self.zawadi, now=self.at(1))
        self.a_neema = services.start_attempt(self.exam, self.neema, now=self.at(1))

    def board(self):
        return self.client_for(self.admin).get(f"/api/proctoring/exams/{self.exam.pk}/").json()

    def ping(self, user, attempt, pos, **extra):
        # the server ignores reports closer than 2 s apart, so move the stored time back for repeated test pings
        LiveLocation.objects.filter(attempt=attempt).update(updated_at=timezone.now() - timedelta(seconds=5))
        return self.client_for(user).post(f"/api/attempts/{attempt.pk}/location/", {**pos, **extra}, format="json")


class StartRules(Base):
    def open_exam(self):
        now = timezone.now()
        self.exam.start_at, self.exam.end_at = now - timedelta(minutes=1), now + timedelta(minutes=59)
        self.exam.save()

    def test_legal_acceptance_is_required(self):
        self.open_exam()
        c = self.client_for(self.amina)
        r = c.post(f"/api/student/exams/{self.exam.pk}/start/", {"agree_rules": True, "location": at()}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "legal"))
        self.assertFalse(Attempt.objects.exists())

    def test_location_is_required(self):
        self.open_exam()
        c = self.client_for(self.amina)
        for loc in (None, {}, {"lat": 0, "lng": 0, "accuracy": 5}, {"lat": "x", "lng": 1}):
            r = c.post(f"/api/student/exams/{self.exam.pk}/start/", {"agree_rules": True, "accept_legal": True, "location": loc}, format="json")
            self.assertEqual((r.status_code, r.json()["code"]), (400, "location_required"))
        self.assertFalse(Attempt.objects.exists())

    def test_start_records_acceptance_and_first_position(self):
        self.open_exam()
        c = self.client_for(self.amina)
        r = c.post(f"/api/student/exams/{self.exam.pk}/start/", {"agree_rules": True, "accept_legal": True, "location": at(),
                                                                 "sensors": {"ble": "unsupported", "net": "wifi", "perm": "granted", "evil": "x"}}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(LegalAcceptance.objects.filter(user=self.amina, exam=self.exam).count(), 1)
        ll = LiveLocation.objects.get(student=self.amina)
        self.assertEqual(ll.sensors, {"ble": "unsupported", "net": "wifi", "perm": "granted"})

    @override_settings(PROCTORING_ENABLED=False)
    def test_can_be_switched_off(self):
        self.open_exam()
        r = self.client_for(self.amina).post(f"/api/student/exams/{self.exam.pk}/start/", {"agree_rules": True}, format="json")
        self.assertEqual(r.status_code, 201)


class Proximity(ProximityBase):
    def test_two_students_under_20m_raise_an_alert_for_admins(self):
        self.assertEqual(self.ping(self.amina, self.a_amina, at(0, 0)).status_code, 200)
        self.assertEqual(self.ping(self.zawadi, self.a_zawadi, at(12, 5)).status_code, 200)  # 13 m away
        al = ProximityAlert.objects.get()
        self.assertEqual((al.confidence, al.active), ("confirmed", True))
        self.assertAlmostEqual(al.last_distance, 13, delta=0.6)
        self.assertEqual(Notification.objects.filter(user=self.admin, kind="integrity_alert").count(), 1)
        b = self.board()
        self.assertEqual(len(b["alerts"]), 1)
        self.assertEqual({b["alerts"][0]["a"]["name"], b["alerts"][0]["b"]["name"]}, {"amina", "zawadi"})
        self.assertEqual(len(b["students"]), 2)

    def test_exactly_one_alert_per_pair_while_they_stay_close(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        for _ in range(3):
            self.ping(self.zawadi, self.a_zawadi, at(10, 0))
        self.assertEqual(ProximityAlert.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 1)

    def test_far_apart_no_alert(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(40, 0))
        self.assertFalse(ProximityAlert.objects.exists())

    def test_rough_position_is_flagged_possible_and_useless_one_ignored(self):
        self.ping(self.amina, self.a_amina, at(0, 0, acc=70))
        self.ping(self.zawadi, self.a_zawadi, at(5, 0, acc=10))
        self.assertEqual(ProximityAlert.objects.get().confidence, "possible")
        ProximityAlert.objects.all().delete()
        self.ping(self.neema, self.a_neema, at(0, 3, acc=400))
        self.assertFalse(ProximityAlert.objects.exists())

    def test_stale_position_is_not_compared_and_alert_closes(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        LiveLocation.objects.filter(student=self.amina).update(updated_at=timezone.now() - timedelta(minutes=5))
        self.ping(self.zawadi, self.a_zawadi, at(5, 0))
        self.assertFalse(ProximityAlert.objects.exists())

    def test_alert_ends_after_students_part(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(5, 0))
        ProximityAlert.objects.update(last_seen=timezone.now() - timedelta(minutes=3))
        self.assertFalse(self.board()["alerts"][0]["active"])

    def test_only_same_exam_is_compared(self):
        from exams.models import Exam, ExamQuestion
        from exams.tests import mcq
        other = Exam.objects.create(title="Other", subject=self.subject, start_at=self.start, end_at=self.start + timedelta(hours=1),
                                    duration_minutes=40, status=Exam.SCHEDULED)
        other.classes.add(self.cls)
        ExamQuestion.objects.create(exam=other, position=1, payload=mcq())
        o = User.objects.create(username="other", role="student", school_class=self.cls, password=make_password("x-pw-1234"), index_number="S9")
        ao = services.start_attempt(other, o, now=self.at(1))
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(o, ao, at(2, 0))
        self.assertFalse(ProximityAlert.objects.exists())

    def test_moving_indicator_from_walking_and_from_motion_sensor(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.assertFalse(self.board()["students"][0]["moving"])
        self.ping(self.amina, self.a_amina, at(3, 2))  # GPS jitter on a desk
        self.assertFalse(self.board()["students"][0]["moving"])
        self.ping(self.amina, self.a_amina, at(40, 0))  # walked 40 m
        row = self.board()["students"][0]
        self.assertEqual((row["moving"], row["moving_source"]), (True, "gps"))
        LiveLocation.objects.update(moving_until=None, moving_source="")
        self.ping(self.amina, self.a_amina, at(40, 0), sensors={"motion": "moving"})
        row = self.board()["students"][0]
        self.assertEqual((row["moving"], row["moving_source"]), (True, "motion"))

    def test_student_without_signal_is_listed(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        b = self.board()
        self.assertEqual({s["name"] for s in b["no_signal"]}, {"zawadi", "neema"})

    def test_permissions(self):
        url = f"/api/proctoring/exams/{self.exam.pk}/"
        self.assertEqual(self.client_for(self.amina).get(url).status_code, 403)  # a student must never see others' positions
        self.assertEqual(self.client_for(self.teacher).get(url).status_code, 403)  # names and places: administrators only
        self.assertEqual(self.client_for(self.admin).get(url).status_code, 200)
        # a student cannot report for someone else's attempt
        r = self.client_for(self.zawadi).post(f"/api/attempts/{self.a_amina.pk}/location/", at(), format="json")
        self.assertEqual(r.status_code, 404)

    def test_finished_attempt_cannot_report_and_bad_fix_is_rejected(self):
        self.assertEqual(self.ping(self.amina, self.a_amina, {"lat": 120, "lng": 0, "accuracy": 3}).status_code, 400)
        services.finalize_attempt(self.a_amina.pk)
        self.assertEqual(self.ping(self.amina, self.a_amina, at()).status_code, 409)

    def test_acknowledge_is_audited(self):
        from core.models import AuditLog
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(5, 0))
        al = ProximityAlert.objects.get()
        self.assertEqual(self.client_for(self.admin).post(f"/api/proctoring/alerts/{al.pk}/ack/").status_code, 200)
        al.refresh_from_db()
        self.assertEqual(al.acknowledged_by, self.admin)
        self.assertTrue(AuditLog.objects.filter(action="proximity_alert_reviewed").exists())

    def test_purge_removes_finished_positions_only(self):
        from django.core.management import call_command
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(500, 0))
        services.finalize_attempt(self.a_amina.pk)
        LiveLocation.objects.update(updated_at=timezone.now() - timedelta(days=2))
        call_command("purge_locations")
        self.assertEqual(list(LiveLocation.objects.values_list("student__username", flat=True)), ["zawadi"])


class PlaceName(ProximityBase):
    def test_admin_only_and_validated(self):
        from unittest import mock
        fake = {"street": "Old Bagamoyo Road", "area": "", "district": "Kinondoni", "region": "Dar es Salaam", "country": "Tanzania",
                "label": "Old Bagamoyo Road, Kinondoni, Dar es Salaam, Tanzania"}
        with mock.patch("proctoring.geocode.reverse", return_value=fake):
            self.assertEqual(self.client_for(self.amina).get("/api/proctoring/place/?lat=-6.8&lng=39.2").status_code, 403)
            r = self.client_for(self.admin).get("/api/proctoring/place/?lat=-6.8&lng=39.2")
            self.assertEqual((r.status_code, r.json()["label"]), (200, fake["label"]))
            self.assertEqual(self.client_for(self.admin).get("/api/proctoring/place/?lat=abc&lng=1").status_code, 400)

    @override_settings(GEOCODER_URL="")
    def test_switched_off_sends_nothing(self):
        from . import geocode
        self.assertIsNone(geocode.reverse(-6.8, 39.2))

    def test_alert_carries_position_for_place_lookup(self):
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(5, 0))
        al = self.client_for(self.admin).get(f"/api/proctoring/exams/{self.exam.pk}/").json()["alerts"][0]
        self.assertAlmostEqual(al["lat"], LAT, places=2)


class ProximityLock(ProximityBase):
    """Admin-set alert distance, and the optional lock of both students' screens until an admin unlocks."""

    def settings(self, **kw):
        from core.models import SchoolSettings
        s = SchoolSettings.load()
        for k, v in kw.items():
            setattr(s, k, v)
        s.save()

    def close_pair(self, d=5, acc=8):
        self.ping(self.amina, self.a_amina, at(0, 0, acc))
        return self.ping(self.zawadi, self.a_zawadi, at(d, 0, acc))

    def answer(self, user, attempt):
        q = attempt.order[attempt.current_index]
        return self.client_for(user).post(f"/api/attempts/{attempt.pk}/answer/", {"question_id": q, "response": "A"}, format="json")

    def test_alert_distance_comes_from_settings(self):
        self.settings(proximity_alert_meters=8)
        self.close_pair(d=12)
        self.assertFalse(ProximityAlert.objects.exists())  # 12 m is outside the 8 m the admin chose
        self.settings(proximity_alert_meters=30)
        self.ping(self.zawadi, self.a_zawadi, at(25, 0))
        self.assertEqual(ProximityAlert.objects.count(), 1)  # 25 m is inside 30 m
        self.assertEqual(self.board()["alert_meters"], 30)

    def test_admin_can_edit_the_distance_and_lock_option_and_it_is_validated(self):
        a = self.client_for(self.admin)
        r = a.patch("/api/settings/", {"proximity_alert_meters": 35.5, "proximity_lock_enabled": True}, format="json")
        self.assertEqual((r.status_code, r.json()["proximity_alert_meters"], r.json()["proximity_lock_enabled"]), (200, 35.5, True))
        for bad in (0, 501, "abc", None):
            self.assertEqual(a.patch("/api/settings/", {"proximity_alert_meters": bad}, format="json").status_code, 400)
        self.assertEqual(a.patch("/api/settings/", {"proximity_lock_enabled": "yes"}, format="json").status_code, 400)
        self.assertEqual(self.client_for(self.teacher).patch("/api/settings/", {"proximity_alert_meters": 5}, format="json").status_code, 403)

    def test_off_by_default_alert_does_not_lock(self):
        self.close_pair()
        al = ProximityAlert.objects.get()
        self.assertFalse(al.locked)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)

    def test_close_students_are_both_locked_and_cannot_answer_but_the_clock_runs(self):
        self.settings(proximity_lock_enabled=True)
        r = self.close_pair()
        self.assertTrue(r.json()["locked"])  # the phone learns about the lock from its own position report
        self.assertTrue(ProximityAlert.objects.get().locked)
        deadline = Attempt.objects.get(pk=self.a_amina.pk).deadline_at
        for u, att in ((self.amina, self.a_amina), (self.zawadi, self.a_zawadi)):
            r = self.answer(u, att)
            self.assertEqual((r.status_code, r.json()["code"]), (423, "locked"))
            self.assertTrue(self.client_for(u).get(f"/api/attempts/{att.pk}/").json()["locked"])
        self.assertEqual(Attempt.objects.get(pk=self.a_amina.pk).deadline_at, deadline)  # time was not paused or extended
        self.assertFalse(self.client_for(self.neema).get(f"/api/attempts/{self.a_neema.pk}/").json()["locked"])  # a bystander far away
        self.assertEqual(self.answer(self.neema, self.a_neema).status_code, 200)
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 1)
        self.assertIn("locked", Notification.objects.filter(kind="integrity_alert").first().body)

    def test_moving_apart_does_not_unlock_only_the_admin_does(self):
        self.settings(proximity_lock_enabled=True)
        self.close_pair()
        ProximityAlert.objects.update(last_seen=timezone.now() - timedelta(minutes=3))
        self.ping(self.zawadi, self.a_zawadi, at(300, 0))  # far away now, alert has ended
        b = self.board()
        self.assertFalse(b["alerts"][0]["active"])
        self.assertTrue(b["alerts"][0]["locked"])
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)
        r = self.client_for(self.admin).post(f"/api/proctoring/alerts/{ProximityAlert.objects.get().pk}/unlock/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 200)
        self.assertFalse(self.ping(self.amina, self.a_amina, at(0, 0)).json()["locked"])

    def test_unlocking_while_still_close_does_not_lock_again_at_once(self):
        from core.models import AuditLog
        self.settings(proximity_lock_enabled=True)
        self.close_pair()
        al = ProximityAlert.objects.get()
        self.client_for(self.admin).post(f"/api/proctoring/alerts/{al.pk}/unlock/")
        self.assertFalse(self.close_pair().json()["locked"])
        self.assertEqual(ProximityAlert.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action="proximity_lock").exists() and AuditLog.objects.filter(action="proximity_unlock").exists())
        # they part for good, then sit close again later: a new alert, a new lock
        ProximityAlert.objects.update(last_seen=timezone.now() - timedelta(minutes=3))
        self.ping(self.zawadi, self.a_zawadi, at(300, 0))
        ProximityAlert.objects.update(active=False)
        self.ping(self.zawadi, self.a_zawadi, at(4, 0))
        self.assertEqual(ProximityAlert.objects.count(), 2)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)

    def test_rough_position_alerts_but_never_locks(self):
        self.settings(proximity_lock_enabled=True)
        self.ping(self.amina, self.a_amina, at(0, 0, acc=70))
        r = self.ping(self.zawadi, self.a_zawadi, at(5, 0, acc=10))
        al = ProximityAlert.objects.get()
        self.assertEqual((al.confidence, al.locked, r.json()["locked"]), ("possible", False, False))
        self.ping(self.amina, self.a_amina, at(0, 0, acc=8))  # her position becomes precise: now it is confirmed and locks
        self.assertTrue(ProximityAlert.objects.get().locked)

    def test_turning_the_option_off_releases_everyone_and_unlock_all(self):
        self.settings(proximity_lock_enabled=True)
        self.close_pair()
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)
        self.settings(proximity_lock_enabled=False)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        self.settings(proximity_lock_enabled=True)
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 423)
        r = self.client_for(self.admin).post(f"/api/proctoring/exams/{self.exam.pk}/unlock-all/")
        self.assertEqual((r.status_code, r.json()["unlocked"]), (200, 1))
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 200)

    def test_only_admins_can_unlock(self):
        self.settings(proximity_lock_enabled=True)
        self.close_pair()
        al = ProximityAlert.objects.get()
        for who in (self.amina, self.zawadi, self.teacher):  # a locked student must not be able to free herself
            self.assertEqual(self.client_for(who).post(f"/api/proctoring/alerts/{al.pk}/unlock/").status_code, 403)
            self.assertEqual(self.client_for(who).post(f"/api/proctoring/exams/{self.exam.pk}/unlock-all/").status_code, 403)
        al.refresh_from_db()
        self.assertIsNone(al.unlocked_at)


class IntegrityChecks(ProximityBase):
    """Device changes and signs of a faked position raise flags for the administrators. Flags inform, they never block."""
    ANDROID = "Mozilla/5.0 (Linux; Android 13; TECNO) AppleWebKit/537.36 Chrome/118 Mobile"
    WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/118"

    def send(self, user, attempt, pos, device="", ua=ANDROID, ip="10.0.0.5"):
        LiveLocation.objects.filter(attempt=attempt).update(updated_at=timezone.now() - timedelta(seconds=5))
        body = {**pos, "device": device} if device else dict(pos)
        return self.client_for(user).post(f"/api/attempts/{attempt.pk}/location/", body, format="json",
                                          HTTP_USER_AGENT=ua, HTTP_X_FORWARDED_FOR=f"6.6.6.6, {ip}")

    def flags(self, kind=None):
        from .models import IntegrityFlag
        q = IntegrityFlag.objects.all()
        return q.filter(kind=kind) if kind else q

    def test_one_device_all_exam_raises_nothing(self):
        for i in range(12):
            self.assertEqual(self.send(self.amina, self.a_amina, at(i % 3, i % 2, acc=5 + i % 3), device="dev-aaaa-1111").status_code, 200)
        self.assertEqual(self.flags().count(), 0)
        ll = LiveLocation.objects.get(attempt=self.a_amina)
        self.assertEqual((ll.devices["first"]["id"], ll.devices["first"]["platform"], ll.devices["first"]["ip"]), ("dev-aaaa-1111", "Android", "10.0.0.5"))

    def test_another_kind_of_device_is_a_high_flag_and_admins_are_told(self):
        self.send(self.amina, self.a_amina, at(0, 0), device="dev-aaaa-1111")
        self.send(self.amina, self.a_amina, at(1, 0), device="dev-bbbb-2222", ua=self.WINDOWS, ip="10.0.0.9")
        f = self.flags("device_changed").get()
        self.assertEqual((f.severity, f.count, f.student_id), ("high", 1, self.amina.pk))
        self.assertEqual(f.detail["at_start"]["platform"], "Android")
        self.assertEqual(f.detail["to"]["platform"], "Windows")
        self.assertNotIn("dev-bbbb-2222", str(f.detail))  # only a short code is kept, never the whole id
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 1)
        row = self.board()["flags"][0]
        self.assertEqual((row["kind"], row["severity"], row["acknowledged"], row["student"]["id"]), ("device_changed", "high", False, self.amina.pk))
        self.assertIn("Windows", row["text"])
        self.send(self.amina, self.a_amina, at(2, 0), device="dev-bbbb-2222", ua=self.WINDOWS, ip="10.0.0.9")
        self.assertEqual(self.flags("device_changed").get().count, 1)  # staying on the new device is not a new change

    def test_same_phone_new_id_is_only_a_warning(self):
        self.send(self.amina, self.a_amina, at(0, 0), device="dev-aaaa-1111")
        self.send(self.amina, self.a_amina, at(0, 1), device="dev-cccc-3333")  # same kind of phone, same network
        self.assertEqual(self.flags("device_changed").get().severity, "warning")

    def test_clients_without_a_device_id_are_never_flagged(self):
        self.send(self.amina, self.a_amina, at(0, 0), device="")
        self.send(self.amina, self.a_amina, at(0, 1), device="x")  # too short to be one of ours
        self.send(self.amina, self.a_amina, at(0, 2), device="dev-aaaa-1111", ua=self.WINDOWS)
        self.assertEqual(self.flags().count(), 0)

    def test_login_during_an_exam_is_recorded_as_information_only(self):
        from rest_framework.test import APIClient
        r = APIClient().post("/api/auth/login/", {"username": "amina", "password": "pw-amina-1"}, format="json", HTTP_USER_AGENT=self.WINDOWS)
        self.assertEqual(r.status_code, 200)
        f = self.flags("login_during_exam").get()
        self.assertEqual((f.severity, f.student_id, f.detail["platform"]), ("info", self.amina.pk, "Windows"))
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 0)  # information does not page the admins
        # a student with no running attempt leaves no trace
        Attempt.objects.filter(pk=self.a_zawadi.pk).update(status=Attempt.SUBMITTED)
        APIClient().post("/api/auth/login/", {"username": "zawadi", "password": "pw-zawadi-1"}, format="json")
        self.assertEqual(self.flags("login_during_exam").count(), 1)

    def test_a_jump_to_another_place_is_flagged(self):
        self.send(self.amina, self.a_amina, at(0, 0, acc=6))
        self.send(self.amina, self.a_amina, at(8000, 0, acc=6))
        f = self.flags("teleport").get()
        self.assertEqual(f.severity, "high")
        self.assertAlmostEqual(f.detail["distance_m"], 8000, delta=50)

    def test_normal_walking_and_rough_fixes_are_not_a_jump(self):
        self.send(self.amina, self.a_amina, at(0, 0, acc=6))
        self.send(self.amina, self.a_amina, at(40, 0, acc=6))
        self.send(self.amina, self.a_amina, at(5000, 0, acc=900))  # a rough network fix far away
        self.assertEqual(self.flags("teleport").count(), 0)

    def test_frozen_position_perfect_accuracy_and_typed_coordinates(self):
        frozen = {"lat": LAT + 1.2345678e-5, "lng": LNG + 2.3456789e-5, "accuracy": 6.0}
        for _ in range(9):
            self.send(self.amina, self.a_amina, frozen)
        self.assertEqual(self.flags("frozen_fix").get().detail["reports"], 8)
        for i in range(3):
            self.send(self.zawadi, self.a_zawadi, {"lat": LAT + i * 1e-6, "lng": LNG + i * 1.7e-6, "accuracy": 1.0})
        self.assertEqual(self.flags("perfect_accuracy").get().student_id, self.zawadi.pk)
        for _ in range(3):
            self.send(self.neema, self.a_neema, {"lat": -6.8, "lng": 39.25, "accuracy": 10})
        self.assertEqual(self.flags("rounded_coords").get().student_id, self.neema.pk)

    def test_real_gps_drift_is_never_flagged(self):
        for i in range(30):
            self.send(self.amina, self.a_amina, at(math.sin(i) * 2.5, math.cos(i) * 2.5, acc=5 + (i % 4) * 0.8))
        self.assertEqual(self.flags().count(), 0)

    def test_a_second_episode_counts_and_shows_the_flag_again_after_review(self):
        self.send(self.amina, self.a_amina, at(0, 0, acc=6))
        self.send(self.amina, self.a_amina, at(8000, 0, acc=6))
        f = self.flags("teleport").get()
        r = self.client_for(self.admin).post(f"/api/proctoring/flags/{f.pk}/ack/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.board()["flags"][0]["acknowledged"])
        self.send(self.amina, self.a_amina, at(0, 0, acc=6))  # jumps back
        f.refresh_from_db()
        self.assertEqual(f.count, 2)
        self.assertFalse(self.board()["flags"][0]["acknowledged"])  # the administrator sees it again
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 1)  # but is not paged twice

    def test_only_admins_can_review_and_flags_never_block_the_exam(self):
        self.send(self.amina, self.a_amina, at(0, 0, acc=6))
        self.send(self.amina, self.a_amina, at(8000, 0, acc=6))
        f = self.flags("teleport").get()
        for who in (self.amina, self.teacher):
            self.assertEqual(self.client_for(who).post(f"/api/proctoring/flags/{f.pk}/ack/").status_code, 403)
        q = self.a_amina.order[self.a_amina.current_index]
        self.assertEqual(self.client_for(self.amina).post(f"/api/attempts/{self.a_amina.pk}/answer/", {"question_id": q, "response": "A"}, format="json").status_code, 200)

    def test_start_records_the_first_device(self):
        Attempt.objects.all().delete()
        now = timezone.now()
        self.exam.start_at, self.exam.end_at = now - timedelta(minutes=1), now + timedelta(minutes=59)
        self.exam.save()
        r = self.client_for(self.amina).post(f"/api/student/exams/{self.exam.pk}/start/", {"agree_rules": True, "accept_legal": True, "location": at(),
                                             "device": "dev-aaaa-1111"}, format="json", HTTP_USER_AGENT=self.ANDROID)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(LiveLocation.objects.get(student=self.amina).devices["first"]["id"], "dev-aaaa-1111")


class RelatedStudents(ProximityBase):
    """Twins / same house / same room: shown with a line and a label, never alerted, never locked."""

    def settings(self, **kw):
        from core.models import SchoolSettings
        s = SchoolSettings.load()
        for k, v in kw.items():
            setattr(s, k, v)
        s.save()

    def mark(self, ids, kind="twin", note="", who=None):
        return self.client_for(who or self.admin).post("/api/proctoring/relations/", {"students": ids, "kind": kind, "note": note}, format="json")

    def close_pair(self, d=5):
        self.ping(self.amina, self.a_amina, at(0, 0))
        return self.ping(self.zawadi, self.a_zawadi, at(d, 0))

    def answer(self, user, attempt):
        q = attempt.order[attempt.current_index]
        return self.client_for(user).post(f"/api/attempts/{attempt.pk}/answer/", {"question_id": q, "response": "A"}, format="json")

    def test_related_pair_gets_a_line_and_label_but_no_alert_and_no_lock(self):
        self.settings(proximity_lock_enabled=True)
        r = self.mark([self.zawadi.pk, self.amina.pk], "twin")
        self.assertEqual((r.status_code, len(r.json()["results"])), (201, 1))
        self.assertEqual(self.close_pair().json()["locked"], False)
        self.assertFalse(ProximityAlert.objects.exists())
        self.assertEqual(Notification.objects.filter(kind="integrity_alert").count(), 0)
        b = self.board()
        self.assertEqual(b["alerts"], [])
        self.assertEqual(len(b["links"]), 1)
        link = b["links"][0]
        self.assertEqual((link["kind"], link["label"]), ("twin", "Twins"))
        self.assertEqual({link["a"], link["b"]}, {self.amina.pk, self.zawadi.pk})
        self.assertAlmostEqual(link["distance_m"], 5, delta=1)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)

    def test_the_line_only_shows_while_they_are_close_and_reporting(self):
        self.mark([self.amina.pk, self.zawadi.pk], "house")
        self.close_pair(d=300)
        self.assertEqual(self.board()["links"], [])  # far apart: no line
        self.ping(self.zawadi, self.a_zawadi, at(10, 0))
        self.assertEqual(self.board()["links"][0]["label"], "Same house")
        LiveLocation.objects.filter(attempt=self.a_zawadi).update(updated_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.board()["links"], [])  # her position is old

    def test_a_third_student_is_still_alerted(self):
        self.mark([self.amina.pk, self.zawadi.pk], "room")
        self.ping(self.amina, self.a_amina, at(0, 0))
        self.ping(self.zawadi, self.a_zawadi, at(3, 0))
        self.ping(self.neema, self.a_neema, at(6, 0))
        als = ProximityAlert.objects.all()
        self.assertEqual({frozenset((a.a_id, a.b_id)) for a in als}, {frozenset((self.amina.pk, self.neema.pk)), frozenset((self.zawadi.pk, self.neema.pk))})

    def test_marking_ends_an_open_alert_and_releases_the_lock(self):
        self.settings(proximity_lock_enabled=True)
        self.close_pair()
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 423)
        self.mark([self.amina.pk, self.zawadi.pk], "twin")
        al = ProximityAlert.objects.get()
        self.assertFalse(al.active)
        self.assertIsNotNone(al.unlocked_at)
        self.assertEqual(self.answer(self.amina, self.a_amina).status_code, 200)
        self.assertEqual(self.answer(self.zawadi, self.a_zawadi).status_code, 200)
        self.assertEqual(self.close_pair().json()["locked"], False)
        self.assertEqual(ProximityAlert.objects.count(), 1)  # no new alert for the pair

    def test_a_household_of_three_makes_three_pairs_and_updating_changes_the_kind(self):
        r = self.mark([self.amina.pk, self.zawadi.pk, self.neema.pk], "house", note="same compound")
        self.assertEqual(len(r.json()["results"]), 3)
        self.assertEqual(self.mark([self.amina.pk, self.zawadi.pk], "twin").status_code, 201)
        rows = self.client_for(self.admin).get("/api/proctoring/relations/").json()["results"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["kind"] for r in rows}, {"twin", "house"})
        found = self.client_for(self.admin).get("/api/proctoring/relations/?q=S3").json()["results"]
        self.assertEqual(len(found), 2)

    def test_removing_the_relation_brings_alerts_back(self):
        self.mark([self.amina.pk, self.zawadi.pk], "twin")
        self.close_pair()
        self.assertFalse(ProximityAlert.objects.exists())
        rid = self.client_for(self.admin).get("/api/proctoring/relations/").json()["results"][0]["id"]
        self.assertEqual(self.client_for(self.admin).delete(f"/api/proctoring/relations/{rid}/").status_code, 200)
        self.ping(self.zawadi, self.a_zawadi, at(4, 0))
        self.assertEqual(ProximityAlert.objects.count(), 1)

    def test_validation_and_permissions(self):
        for ids in ([self.amina.pk], [self.amina.pk, self.amina.pk], list(range(1, 11)), "x", None, [self.amina.pk, "z"]):
            self.assertEqual(self.mark(ids).status_code, 400, ids)
        self.assertEqual(self.mark([self.amina.pk, self.zawadi.pk], "cousins").status_code, 400)
        self.assertEqual(self.mark([self.amina.pk, self.teacher.pk]).status_code, 400)  # only students
        for who in (self.amina, self.teacher):
            self.assertEqual(self.mark([self.amina.pk, self.zawadi.pk], who=who).status_code, 403)
            self.assertEqual(self.client_for(who).get("/api/proctoring/relations/").status_code, 403)
        self.assertEqual(self.client_for(self.amina).delete("/api/proctoring/relations/1/").status_code, 403)
