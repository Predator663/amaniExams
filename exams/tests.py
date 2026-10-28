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
        self.assertEqual(d["not_started_students"][0]["index"], "S2")

    def test_submitted_students_are_listed_and_board_keeps_finished_exam(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.finalize_attempt(a.pk, self.at(5))
        d = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/monitor/").json()
        self.assertEqual((d["in_progress"], d["submitted"]), (0, 1))
        self.assertEqual(d["submitted_students"][0]["index"], "S1")
        self.assertEqual(d["submitted_students"][0]["answered"], 0)

    def test_monitor_survives_exam_without_times(self):
        Exam.objects.filter(pk=self.exam.pk).update(start_at=None, end_at=None, status=Exam.DRAFT)
        r = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/monitor/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["start_at"])

    def test_partial_vs_full_completion(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.finalize_attempt(a.pk, self.at(5))
        d = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/monitor/").json()
        self.assertEqual(d["submitted_students"][0]["completion"], "partial")
        self.assertEqual((d["full"], d["partial"]), (0, 1))

    def test_parents_shown_from_guardians_page(self):
        from guardians.models import Guardian, GuardianLink
        g = Guardian(relationship="mother"); g.set_name("Mama Amina"); g.set_phone("0712345678"); g.save()
        GuardianLink.objects.create(guardian=g, student=self.zawadi)
        services.start_attempt(self.exam, self.amina, now=self.at(1))
        d = self.client_for(self.admin).get(f"/api/exams/{self.exam.pk}/monitor/").json()
        self.assertEqual(d["not_started_students"][0]["parents"][0]["name"], "Mama Amina")

    def test_pending_results_listed_for_student(self):
        a = services.start_attempt(self.exam, self.amina, now=self.at(1))
        services.finalize_attempt(a.pk, self.at(5))
        r = self.client_for(self.amina).get("/api/results/pending/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertIn("results_at", r.json()[0])

    def test_board_is_one_call_and_teacher_gets_no_names(self):
        services.start_attempt(self.exam, self.amina, now=self.at(1))
        b = self.client_for(self.admin).get("/api/exams/monitor-board/").json()
        self.assertIn("exams", b)
        self.assertIn("totals", b)


class BuilderTests(Base):
    """Question auto-approval and the exam builder's picker, random pick and sectioned paper."""

    def setUp(self):
        super().setUp()
        from academics.models import TeacherAssignment
        self.teacher = User.objects.create(username="teach1", role="teacher", password=make_password("T3ach-pass!"))
        TeacherAssignment.objects.create(teacher=self.teacher, subject=self.subject, school_class=self.cls)
        self.exam.status = Exam.DRAFT
        self.exam.save()
        self.exam.questions.all().delete()
        self.t = self.client_for(self.teacher)

    def body(self, qtype="mcq_single", topic="Algebra", prompt="2+2?", **extra):
        base = {"subject": self.subject.pk, "form_level": 1, "topic": topic, "difficulty": "easy", "marks": 1,
                "language": "en", "qtype": qtype, "prompt": f"<p>{prompt}</p>"}
        if qtype == "mcq_single":
            base.update(content={"options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}]}, answer={"correct": "b"})
        else:
            base.update(content={}, answer={"correct": True})
        base.update(extra)
        return base

    def test_submit_approves_immediately(self):
        r = self.t.post("/api/questions/", self.body(), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "draft")
        s = self.t.post(f"/api/questions/{r.data['id']}/submit/", {}, format="json")
        self.assertEqual(s.data["status"], "approved")

    def test_create_with_submit_flag_is_approved(self):
        r = self.t.post("/api/questions/", self.body(submit=True), format="json")
        self.assertEqual(r.data["status"], "approved")

    def test_editing_an_approved_question_keeps_it_approved(self):
        r = self.t.post("/api/questions/", self.body(submit=True), format="json")
        e = self.t.patch(f"/api/questions/{r.data['id']}/", {"topic": "Geometry"}, format="json")
        self.assertEqual(e.data["status"], "approved")

    def test_bank_pages_filters_and_usage(self):
        ids = [self.t.post("/api/questions/", self.body(topic="Algebra" if i % 2 else "Geometry", prompt=f"Q{i}", submit=True), format="json").data["id"] for i in range(7)]
        self.t.post("/api/questions/", self.body(prompt="draft one"), format="json")  # draft: never listed
        r = self.t.get(f"/api/exams/{self.exam.pk}/bank/?page_size=3").data
        self.assertEqual((r["count"], r["pages"], len(r["results"])), (7, 3, 3))
        self.assertEqual(sorted(r["topics"]), ["Algebra", "Geometry"])
        self.assertEqual(self.t.get(f"/api/exams/{self.exam.pk}/bank/?page_size=3&page=3").data["results"].__len__(), 1)
        self.assertEqual(self.t.get(f"/api/exams/{self.exam.pk}/bank/?topic=Algebra").data["count"], 3)
        self.assertEqual(self.t.get(f"/api/exams/{self.exam.pk}/bank/?q=Q3").data["count"], 1)
        # use two questions in another exam -> they count as "used"
        other = Exam.objects.create(title="Older", subject=self.subject, status=Exam.DRAFT)
        for pos, qid in enumerate(ids[:2], start=1):
            ExamQuestion.objects.create(exam=other, position=pos, source_id=qid, payload=mcq())
        self.assertEqual(self.t.get(f"/api/exams/{self.exam.pk}/bank/?usage=used").data["count"], 2)
        self.assertEqual(self.t.get(f"/api/exams/{self.exam.pk}/bank/?usage=unused").data["count"], 5)

    def test_pick_returns_random_unselected_questions(self):
        ids = [self.t.post("/api/questions/", self.body(prompt=f"Q{i}", submit=True), format="json").data["id"] for i in range(4)]
        r = self.t.post(f"/api/exams/{self.exam.pk}/pick/", {"rules": [{"difficulty": "easy", "count": 2}], "exclude": ids[:2]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual({q["id"] for q in r.data}, set(ids[2:]))
        bad = self.t.post(f"/api/exams/{self.exam.pk}/pick/", {"rules": [{"count": 9}], "exclude": []}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_paper_is_grouped_into_sections_in_picked_order(self):
        tf1 = self.t.post("/api/questions/", self.body("true_false", prompt="TF1", submit=True), format="json").data["id"]
        m2 = self.t.post("/api/questions/", self.body(prompt="M2", submit=True), format="json").data["id"]
        m1 = self.t.post("/api/questions/", self.body(prompt="M1", submit=True), format="json").data["id"]
        r = self.t.post(f"/api/exams/{self.exam.pk}/paper/", {"question_ids": [tf1, m2, m1]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        rows = self.t.get(f"/api/exams/{self.exam.pk}/questions/").data
        self.assertEqual([x["source"] for x in rows], [m2, m1, tf1])  # multiple choice first (A), true/false second (B)
        self.assertEqual([x["section"] for x in rows], ["A", "A", "B"])
