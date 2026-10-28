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
    def board(self):
        return self.client_for(self.admin).get(f"/api/proctoring/exams/{self.exam.pk}/").json()

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
