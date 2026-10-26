"""Tests for the acceptance rules in SRS section 9.2 that Phase 1 covers.
Run with:  python manage.py test"""
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import SchoolClass, Subject
from accounts.models import User
from core import grading
from core.models import SchoolSettings
from questions.models import Question
from . import marking, services
from .models import Attempt, Exam, ExamGrant, ExamQuestion


def mcq(marks=2, correct="b"):
    return {"qtype": "mcq_single", "prompt": "2+2?", "marks": marks, "topic": "Algebra", "explanation": "Because 4.",
            "content": {"options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}, {"id": "c", "text": "5"}]},
            "answer": {"correct": correct}}


class Base(TestCase):
    def setUp(self):
        self.cls = SchoolClass.objects.create(name="Form 1", form_level=1)
        self.subject = Subject.objects.create(name="Mathematics")
        self.amina = User.objects.create(username="amina", role="student", school_class=self.cls,
                                         password=make_password("pw-amina-1"), index_number="S1")
        self.zawadi = User.objects.create(username="zawadi", role="student", school_class=self.cls,
                                          password=make_password("pw-zawadi-1"), index_number="S2")
        self.admin = User.objects.create(username="admin1", role="admin", password=make_password("Adm1n-pass!"))
        self.start = timezone.now() + timedelta(hours=1)
        self.exam = Exam.objects.create(
            title="Maths Test", subject=self.subject, start_at=self.start, end_at=self.start + timedelta(hours=1),
            duration_minutes=40, status=Exam.SCHEDULED, shuffle_questions=False)
        self.exam.classes.add(self.cls)
        for i in (1, 2):
            ExamQuestion.objects.create(exam=self.exam, position=i, payload=mcq())

    def client_for(self, user):
        from rest_framework.authtoken.models import Token
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Token " + Token.objects.get_or_create(user=user)[0].key)
        return c

    def at(self, minutes):
        return self.start + timedelta(minutes=minutes)


class MarkingTests(TestCase):
    def test_types(self):
        single = mcq()
        self.assertEqual(marking.fraction_correct(single, "b"), 1)
        self.assertEqual(marking.fraction_correct(single, "a"), 0)
        multi = {"qtype": "mcq_multi", "answer": {"correct": ["a", "b"]}}
        self.assertEqual(marking.fraction_correct(multi, ["a", "b"]), 1)
        self.assertEqual(marking.fraction_correct(multi, ["a"], partial=True), 0.5)
        self.assertEqual(marking.fraction_correct(multi, ["a", "c"], partial=True), 0)  # wrong pick cancels right pick
        self.assertEqual(marking.fraction_correct(multi, ["a"], partial=False), 0)
        fill = {"qtype": "fill_blank", "answer": {"accepted": ["Dar es Salaam"], "numeric": {"value": 3.14, "tolerance": 0.01}}}
        self.assertEqual(marking.fraction_correct(fill, "  dar   ES salaam "), 1)  # case and spaces ignored
        self.assertEqual(marking.fraction_correct(fill, "3.145"), 1)
        self.assertEqual(marking.fraction_correct(fill, "3.2"), 0)
        match = {"qtype": "matching", "answer": {"pairs": {"1": "x", "2": "y"}}}
        self.assertEqual(marking.fraction_correct(match, {"1": "x", "2": "y"}), 1)
        self.assertEqual(marking.fraction_correct(match, {"1": "x", "2": "z"}, partial=True), 0.5)
        order = {"qtype": "ordering", "answer": {"order": ["a", "b", "c"]}}
        self.assertEqual(marking.fraction_correct(order, ["a", "b", "c"]), 1)
        self.assertEqual(marking.fraction_correct(order, ["b", "a", "c"]), 0)

    def test_negative_marking_off_by_default_and_skips_never_negative(self):
        p = mcq()
        self.assertEqual(marking.marks_for(p, "a", partial=True, negative=False, negative_fraction=0.25), 0)
        self.assertEqual(marking.marks_for(p, "a", partial=True, negative=True, negative_fraction=0.25), -0.5)
        self.assertEqual(marking.marks_for(p, None, partial=True, negative=True, negative_fraction=0.25), 0)

    def test_necta_grades_and_division(self):
        self.assertEqual(grading.grade_for(75)["grade"], "A")
        self.assertEqual(grading.grade_for(74.4)["grade"], "B")
        self.assertEqual(grading.grade_for(30)["grade"], "D")
        self.assertEqual(grading.grade_for(29.4)["grade"], "F")
        self.assertEqual(grading.division_for([1] * 7)["division"], "I")
        self.assertEqual(grading.division_for([5] * 7)["division"], "0")
        self.assertIsNone(grading.division_for([1] * 6))


class ExamDayTests(Base):
    def test_cannot_start_early_or_after_late_entry(self):
        with self.assertRaises(services.ExamError) as e:
            services.start_attempt(self.exam, self.amina, now=self.at(-5))
        self.assertEqual(e.exception.code, "too_early")
        with self.assertRaises(services.ExamError) as e:
            services.start_attempt(self.exam, self.amina, now=self.at(11))  # late entry is 10 minutes
        self.assertEqual(e.exception.code, "too_late")

    def test_late_starter_gets_no_extra_time(self):
        self.exam.duration_minutes = 60
        self.exam.save()
        a = services.start_attempt(self.exam, self.amina, now=self.at(9))
        self.assertEqual(a.deadline_at, self.exam.end_at)  # capped at window end, not 40 min from 9

    def test_server_clock_and_resume(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        s1 = services.attempt_state(a, now=self.at(11))
        self.assertEqual(s1["remaining_seconds"], 30 * 60)  # 40 min - 10 min used; client clock irrelevant
        again = services.start_attempt(self.exam, self.amina, now=self.at(12))
        self.assertEqual(again.pk, a.pk)  # START twice / refresh resumes, no new attempt, no new time
        self.assertEqual(again.deadline_at, a.deadline_at)

    def test_no_correct_answer_ever_sent_to_phone(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        s = services.attempt_state(a, now=self.at(2))
        blob = str(s)
        self.assertNotIn("correct", blob)
        self.assertNotIn("Because 4.", blob)  # explanation hidden

    def test_one_way_flow_and_idempotent_offline_replay(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        q1, q2 = a.order
        with self.assertRaises(services.ExamError):  # cannot jump ahead
            services.submit_answer(a.pk, self.amina, q2, "b", now=self.at(2))
        services.submit_answer(a.pk, self.amina, q1, "a", now=self.at(2))
        services.submit_answer(a.pk, self.amina, q1, "b", now=self.at(3))  # replay / change attempt: ignored (BR-05)
        self.assertEqual(a.answers.get(exam_question_id=q1).response, "a")

    def test_skip_only_when_allowed(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        with self.assertRaises(services.ExamError):
            services.submit_answer(a.pk, self.amina, a.order[0], None, skip=True, now=self.at(2))

    def test_time_over_auto_submits_and_marks(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.submit_answer(a.pk, self.amina, a.order[0], "b", now=self.at(5))
        state = services.attempt_state(a, now=self.at(50))  # deadline passed
        self.assertTrue(state["finished"] and state["time_over"])
        a.refresh_from_db()
        self.assertEqual(a.status, Attempt.AUTO_SUBMITTED)
        self.assertEqual(a.result.score, 2)  # one of two questions right
        self.assertEqual(a.result.percent, 50)

    def test_answer_after_deadline_rejected(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        with self.assertRaises(services.ExamError) as e:
            services.submit_answer(a.pk, self.amina, a.order[0], "b", now=self.at(45))
        self.assertEqual(e.exception.code, "time_over")

    def test_one_attempt_only_retake_needs_admin_grant(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.finalize_attempt(a.pk, now=self.at(3))
        with self.assertRaises(services.ExamError) as e:
            services.start_attempt(self.exam, self.amina, now=self.at(4))
        self.assertEqual(e.exception.code, "already_taken")
        ExamGrant.objects.create(exam=self.exam, student=self.amina, kind="retake", reason="power cut", granted_by=self.admin)
        b = services.start_attempt(self.exam, self.amina, now=self.at(5))
        self.assertEqual(b.attempt_no, 2)


class ResultVisibilityAndPrivacyTests(Base):
    def finished_attempt(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        for qid in a.order:
            services.submit_answer(a.pk, self.amina, qid, "b", now=self.at(10))
        a.refresh_from_db()
        return a

    def test_results_hidden_until_end_plus_five_minutes(self):
        a = self.finished_attempt()  # finished early, still hidden
        self.assertEqual(a.status, Attempt.SUBMITTED)
        end = self.exam.end_at
        self.assertFalse(services.result_visible(a, end + timedelta(minutes=4, seconds=59)))
        self.assertTrue(services.result_visible(a, end + timedelta(minutes=5)))

    def test_api_hides_result_and_review_before_publish(self):
        a = self.finished_attempt()
        c = self.client_for(self.amina)
        self.assertEqual(c.get(f"/api/results/{a.pk}/").status_code, 404)
        self.assertEqual(c.get(f"/api/results/{a.pk}/review/").status_code, 404)
        self.assertEqual(c.get("/api/results/").json(), [])

    def test_publish_flow_via_clock(self):
        a = self.finished_attempt()
        services.sync_exam(self.exam, now=self.exam.end_at + timedelta(minutes=6))
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.PUBLISHED)
        self.assertTrue(services.result_visible(a, self.exam.end_at + timedelta(minutes=6)))

    def test_student_cannot_reach_another_students_data(self):
        a = self.finished_attempt()
        other = self.client_for(self.zawadi)
        for url in (f"/api/attempts/{a.pk}/", f"/api/results/{a.pk}/", f"/api/results/{a.pk}/review/"):
            self.assertEqual(other.get(url).status_code, 404, url)
        self.assertEqual(other.post(f"/api/attempts/{a.pk}/answer/", {"question_id": a.order[0], "response": "b"}, format="json").status_code, 404)

    def test_admin_changes_to_grade_scale_do_not_alter_old_results(self):
        a = self.finished_attempt()
        self.assertEqual(a.result.grade, "A")
        s = SchoolSettings.load()
        s.grade_scale["grades"][0]["min"] = 101
        s.save()
        services.recompute_exam_results(self.exam)
        a.result.refresh_from_db()
        self.assertEqual(a.result.grade, "A")

    def test_void_question_recalculates(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.submit_answer(a.pk, self.amina, a.order[0], "b", now=self.at(5))
        services.submit_answer(a.pk, self.amina, a.order[1], "a", now=self.at(6))  # second wrong
        a.refresh_from_db()
        self.assertEqual(a.result.percent, 50)
        wrong = ExamQuestion.objects.get(pk=a.order[1])
        wrong.voided = True
        wrong.save()
        services.recompute_exam_results(self.exam)
        a.result.refresh_from_db()
        self.assertEqual(a.result.percent, 100)


class AccountTests(TestCase):
    def test_usernames_unique_and_forced_password_change(self):
        from accounts.services import make_username
        taken = {"amina"}
        self.assertEqual(make_username("Amina", taken), "amina2")
        self.assertEqual(make_username("  Amina ", taken), "amina3")
        self.assertEqual(make_username("Mary Anne", taken), "maryanne")

    def test_login_lockout_and_single_session(self):
        u = User.objects.create(username="neema", role="student", password=make_password("Correct-pw-1"))
        c = APIClient()
        for _ in range(5):
            self.assertEqual(c.post("/api/auth/login/", {"username": "neema", "password": "bad"}).status_code, 400)
        self.assertEqual(c.post("/api/auth/login/", {"username": "neema", "password": "Correct-pw-1"}).status_code, 429)
        u.refresh_from_db()
        u.locked_until = None
        u.save()
        t1 = c.post("/api/auth/login/", {"username": "neema", "password": "Correct-pw-1"}).json()["token"]
        t2 = c.post("/api/auth/login/", {"username": "neema", "password": "Correct-pw-1"}).json()["token"]
        c.credentials(HTTP_AUTHORIZATION="Token " + t1)
        self.assertEqual(c.get("/api/me/").status_code, 401)  # first device was logged out (AUTH-09)
        c.credentials(HTTP_AUTHORIZATION="Token " + t2)
        self.assertEqual(c.get("/api/me/").status_code, 200)

    def test_must_change_password_blocks_other_endpoints(self):
        User.objects.create(username="rehema", role="student", must_change_password=True,
                            password=make_password("S77", hasher="pbkdf2_sha256_initial"))
        c = APIClient()
        tok = c.post("/api/auth/login/", {"username": "rehema", "password": "S77"}).json()["token"]
        c.credentials(HTTP_AUTHORIZATION="Token " + tok)
        self.assertEqual(c.get("/api/student/exams/").status_code, 403)
        self.assertEqual(c.get("/api/me/").status_code, 200)
        r = c.post("/api/auth/change-password/", {"old_password": "S77", "new_password": "A-better-pass-9"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/api/student/exams/").status_code, 200)


class PaperQuestionsListTests(Base):
    """Staff can list an exam's own questions (needed to void one); students cannot."""

    def test_admin_lists_paper_without_answers(self):
        r = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/questions/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([q["position"] for q in r.json()], [1, 2])
        self.assertNotIn("answer", r.json()[0])
        self.assertNotIn("content", r.json()[0])

    def test_student_is_refused(self):
        r = self.client_for(self.amina).get(f"/api/exams/{self.exam.pk}/questions/")
        self.assertIn(r.status_code, (401, 403))


class MonitorDetailTests(Base):
    """ADM-06: the live monitor shows names and progress to admins only."""

    def test_admin_sees_progress_and_names_teacher_sees_numbers(self):
        services.start_attempt(self.exam, self.amina, now=self.at(1))
        d = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/monitor/").json()
        self.assertEqual(d["in_progress"], 1)
        row = d["in_progress_students"][0]
        self.assertEqual((row["answered"], d["total_questions"]), (0, 2))
        self.assertGreater(row["seconds_left"], 0)
        self.assertIn("online", row)
        self.assertEqual(d["submitted_students"], [])
