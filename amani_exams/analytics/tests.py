"""Phase 2 analytics tests. Run:  python manage.py test analytics"""
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from academics.models import SchoolClass, Subject, TeacherAssignment
from accounts.models import User
from exams import services
from exams.models import Exam, ExamQuestion
from exams.tests import mcq
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class AnalyticsBase(TestCase):
    def setUp(self):
        self.cls_a = SchoolClass.objects.create(name="Form 1", stream="A", form_level=1)
        self.cls_b = SchoolClass.objects.create(name="Form 1", stream="B", form_level=1)
        self.maths = Subject.objects.create(name="Mathematics")
        self.english = Subject.objects.create(name="English")
        mk = lambda name, cls, idx: User.objects.create(
            username=name, first_name=name.title(), last_name="Test", role="student", school_class=cls,
            index_number=idx, password=make_password("pw-" + name + "-1"))
        self.amina, self.zawadi = mk("amina", self.cls_a, "S1"), mk("zawadi", self.cls_b, "S2")
        self.teacher = User.objects.create(username="teach", role="teacher", password=make_password("Teach-pass-1"))
        TeacherAssignment.objects.create(teacher=self.teacher, subject=self.maths, school_class=self.cls_a)
        self.admin = User.objects.create(username="admin1", role="admin", password=make_password("Adm1n-pass!"))
        self.end = timezone.now() - timedelta(hours=1)
        self.start = self.end - timedelta(hours=1)

    def client_for(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Token " + Token.objects.get_or_create(user=user)[0].key)
        return c

    def make_exam(self, subject, title="Test", picks=None, publish=True):
        """picks: {student: [answer for q1, answer for q2]}; correct answer is 'b'."""
        exam = Exam.objects.create(title=title, subject=subject, start_at=self.start, end_at=self.end,
                                   duration_minutes=30, status=Exam.SCHEDULED, shuffle_questions=False)
        exam.classes.add(self.cls_a, self.cls_b)
        for i in (1, 2):
            ExamQuestion.objects.create(exam=exam, position=i, payload=mcq())
        attempts = {}
        for student, answers in (picks or {}).items():
            a = services.start_attempt(exam, student, now=self.start + timedelta(minutes=1))
            for qid, ans in zip(a.order, answers):
                services.submit_answer(a.pk, student, qid, ans, now=self.start + timedelta(minutes=5))
            attempts[student.pk] = a
        if publish:
            services.sync_exam(exam)
            exam.refresh_from_db()
            assert exam.status == Exam.PUBLISHED, exam.status
        return exam, attempts


class TeacherScopeTests(AnalyticsBase):
    def test_teacher_sees_only_assigned_subject_and_class(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"], self.zawadi: ["a", "a"]})
        self.make_exam(self.english, "Eng", picks={self.amina: ["b", "b"]})
        c = self.client_for(self.teacher)
        d = c.get(f"/api/analytics/subjects/{self.maths.pk}/").json()
        self.assertEqual(d["count"], 1)  # only Form 1 A (amina); zawadi is in B
        self.assertEqual(d["average"], 100.0)
        self.assertEqual(c.get(f"/api/analytics/subjects/{self.english.pk}/").status_code, 404)
        names = [s["name"] for s in c.get("/api/analytics/subjects/").json()]
        self.assertEqual(names, ["Mathematics"])

    def test_admin_sees_everything(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"], self.zawadi: ["a", "a"]})
        d = self.client_for(self.admin).get(f"/api/analytics/subjects/{self.maths.pk}/").json()
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["average"], 50.0)
        self.assertEqual(len(d["by_class"]), 2)

    def test_nothing_before_results_are_published(self):
        exam, _ = self.make_exam(self.maths, picks={self.amina: ["b", "b"]}, publish=False)
        # still inside the exam window, so it is not Published (and cannot be published by a request)
        Exam.objects.filter(pk=exam.pk).update(end_at=timezone.now() + timedelta(hours=1), status=Exam.LIVE)
        c = self.client_for(self.teacher)
        self.assertEqual(c.get(f"/api/analytics/subjects/{self.maths.pk}/").json()["count"], 0)
        self.assertEqual(c.get(f"/api/analytics/exams/{exam.pk}/questions/").status_code, 404)
        self.assertEqual(c.get(f"/api/analytics/exams/{exam.pk}/integrity/").status_code, 404)

    def test_students_list_flags_and_profile(self):
        self.make_exam(self.maths, picks={self.amina: ["a", "a"]})  # 0 percent
        c = self.client_for(self.teacher)
        rows = c.get(f"/api/analytics/subjects/{self.maths.pk}/students/").json()
        self.assertEqual([r["name"] for r in rows], ["Amina Test"])  # zawadi is not in her class
        self.assertEqual(rows[0]["flag"], "needs_support")
        prof = c.get(f"/api/analytics/subjects/{self.maths.pk}/students/{self.amina.pk}/").json()
        self.assertEqual(prof["participation"], {"taken": 1, "eligible": 1})
        self.assertEqual(c.get(f"/api/analytics/subjects/{self.maths.pk}/students/{self.zawadi.pk}/").status_code, 404)

    def test_question_analysis(self):
        exam, _ = self.make_exam(self.maths, picks={self.amina: ["b", "a"]})
        d = self.client_for(self.teacher).get(f"/api/analytics/exams/{exam.pk}/questions/").json()
        q1, q2 = d["questions"]
        self.assertEqual((q1["percent_correct"], q2["percent_correct"]), (100.0, 0.0))
        self.assertEqual(q2["most_chosen_wrong"]["text"], "3")

    def test_heatmap(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"], self.zawadi: ["b", "a"]})
        d = self.client_for(self.admin).get(f"/api/analytics/subjects/{self.maths.pk}/heatmap/").json()
        self.assertEqual(d["topics"], ["Algebra"])
        self.assertEqual(d["cells"], [[100.0, 50.0]])

    def test_teacher_cannot_use_admin_endpoints(self):
        c = self.client_for(self.teacher)
        self.assertEqual(c.get("/api/analytics/school/").status_code, 403)
        self.assertEqual(c.get("/api/exports/students/").status_code, 403)

    def test_school_analytics_and_participation(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})  # zawadi never sat it
        d = self.client_for(self.admin).get("/api/analytics/school/").json()
        self.assertEqual(d["participation"]["overall_rate"], 50.0)
        self.assertTrue(d["engagement"]["available"])  # Phase 3: engagement numbers exist now


class DownloadTests(AnalyticsBase):
    def test_subject_export_xlsx_and_pdf(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        c = self.client_for(self.teacher)
        r = c.get(f"/api/analytics/subjects/{self.maths.pk}/export/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        r = c.get(f"/api/analytics/subjects/{self.maths.pk}/export/?file=pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(c.get(f"/api/analytics/subjects/{self.english.pk}/export/").status_code, 404)

    def test_result_slip_is_private(self):
        _, attempts = self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        a = attempts[self.amina.pk]
        r = self.client_for(self.amina).get(f"/api/results/{a.pk}/slip/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(self.client_for(self.zawadi).get(f"/api/results/{a.pk}/slip/").status_code, 404)
        self.assertEqual(self.client_for(self.admin).get(f"/api/exports/slip/{a.pk}/").status_code, 200)

    def test_slip_hidden_before_publish(self):
        exam, attempts = self.make_exam(self.maths, picks={self.amina: ["b", "b"]}, publish=False)
        Exam.objects.filter(pk=exam.pk).update(end_at=timezone.now())  # ended just now: inside the 5 minutes
        a = attempts[self.amina.pk]
        self.assertEqual(self.client_for(self.amina).get(f"/api/results/{a.pk}/slip/").status_code, 404)

    def test_admin_exports(self):
        exam, _ = self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        c = self.client_for(self.admin)
        self.assertEqual(c.get(f"/api/exports/exams/{exam.pk}/results/").status_code, 200)
        self.assertTrue(c.get("/api/exports/students/?file=pdf").content.startswith(b"%PDF"))


class StudentAnalyticsTests(AnalyticsBase):
    def test_student_sees_only_own_analytics_and_projection(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "a"], self.zawadi: ["b", "b"]})
        d = self.client_for(self.amina).get("/api/student/analytics/").json()
        self.assertEqual(d["subjects"][0]["average"], 50.0)
        self.assertEqual(d["subjects"][0]["subject"], "Mathematics")
        self.assertTrue(d["projected"]["is_projection"])
        self.assertIsNone(d["projected"]["division"])  # only one subject so far
        self.assertEqual(self.client_for(self.admin).get("/api/student/analytics/").status_code, 403)

    def test_report_card_marked_projection_without_term(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        d = self.client_for(self.amina).get("/api/student/report-card/").json()
        self.assertTrue(d["is_projection"])
        self.assertEqual(d["subjects_needed"], 7)
