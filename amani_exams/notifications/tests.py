from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from analytics.tests import AnalyticsBase
from exams import services
from exams.models import Exam
from . import services as ns
from .models import Notification


class NotificationTests(AnalyticsBase):
    def future_exam(self, hours_ahead):
        start = timezone.now() + timedelta(hours=hours_ahead)
        exam = Exam.objects.create(title="Maths T1", subject=self.maths, start_at=start, end_at=start + timedelta(hours=1),
                                   duration_minutes=40, status=Exam.SCHEDULED)
        exam.classes.add(self.cls_a)
        return exam

    def test_due_specs_choose_one_reminder(self):
        exam = self.future_exam(12)
        now = timezone.now()
        self.assertEqual(ns.due_specs(exam, now)[0][0], f"exam1d:{exam.pk}")
        self.assertEqual(ns.due_specs(exam, exam.start_at - timedelta(minutes=30))[0][0], f"exam1h:{exam.pk}")
        self.assertEqual(ns.due_specs(exam, exam.start_at + timedelta(minutes=1))[0][0], f"examstart:{exam.pk}")
        self.assertEqual(ns.due_specs(exam, exam.start_at - timedelta(days=3)), [])

    def test_scheduler_notifies_eligible_students_once(self):
        self.future_exam(12)
        self.assertEqual(ns.run_exam_notifications(), 1)  # amina is in the class; zawadi is not
        self.assertEqual(ns.run_exam_notifications(), 0)  # idempotent
        self.assertEqual(Notification.objects.filter(user=self.amina).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.zawadi).count(), 0)

    def test_list_is_private_and_lazy_reminders_work_without_cron(self):
        self.future_exam(12)
        c = self.client_for(self.amina)
        d = c.get("/api/notifications/").json()
        self.assertEqual(d["unread"], 1)
        self.assertEqual(self.client_for(self.zawadi).get("/api/notifications/").json()["items"], [])
        self.assertEqual(c.post("/api/notifications/read/", {"all": True}, format="json").json()["marked"], 1)
        self.assertEqual(c.get("/api/notifications/").json()["unread"], 0)

    def test_cannot_mark_someone_elses_notification(self):
        ns.notify([self.amina], "announcement", "Hi")
        n = Notification.objects.get()
        r = self.client_for(self.zawadi).post("/api/notifications/read/", {"ids": [n.pk]}, format="json")
        self.assertEqual(r.json()["marked"], 0)

    def test_results_ready_when_exam_publishes(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        n = Notification.objects.get(user=self.amina, kind="results_ready")
        self.assertIn("Test", n.title)
        self.assertFalse(Notification.objects.filter(user=self.zawadi, kind="results_ready").exists())

    def test_announcements_target_class_stream_or_all(self):
        admin = self.client_for(self.admin)
        r = admin.post("/api/announcements/", {"title": "Hello", "body": "Holiday rules", "audience": "class",
                                               "class_ids": [self.cls_a.pk]}, format="json")
        self.assertEqual(r.json()["recipients"], 1)
        r = admin.post("/api/announcements/", {"title": "B only", "body": "x", "audience": "stream", "stream": "b"}, format="json")
        self.assertEqual(r.json()["recipients"], 1)
        r = admin.post("/api/announcements/", {"title": "All", "body": "x"}, format="json")
        self.assertEqual(r.json()["recipients"], 2)
        self.assertEqual(self.client_for(self.amina).post("/api/announcements/", {"title": "x", "body": "y"}, format="json").status_code, 403)

    def test_push_subscription(self):
        c = self.client_for(self.amina)
        body = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
        self.assertEqual(c.post("/api/push/subscribe/", body, format="json").status_code, 201)
        self.assertEqual(c.post("/api/push/subscribe/", {"endpoint": "x"}, format="json").status_code, 400)
        self.assertIsNone(c.get("/api/push/public-key/").json()["public_key"])  # not configured in tests
