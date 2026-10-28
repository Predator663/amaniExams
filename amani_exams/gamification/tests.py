"""Phase 3 tests: XP, streaks, badges, review, practice, leaderboard, settings.
Run:  python manage.py test gamification
(The pure rules are also tested without Django in gamification/test_rules.py.)"""
from datetime import timedelta

from django.utils import timezone

from analytics.tests import AnalyticsBase
from core.models import SchoolSettings
from exams.models import Exam, ExamQuestion
from exams.tests import mcq
from questions.models import Question
from . import services
from .models import ActivityDay, BadgeAward, ExamRewardMark, PracticeSession, XPEvent


def practice_question(subject, topic="Algebra", form_level=1, eligible=True):
    m = mcq()
    return Question.objects.create(subject=subject, form_level=form_level, topic=topic, difficulty="easy", marks=1,
                                   qtype="mcq_single", prompt="2+2?", content=m["content"], answer={"correct": "b"},
                                   explanation="Because 4.", status=Question.APPROVED, practice_eligible=eligible)


class ExamRewardTests(AnalyticsBase):
    def setUp(self):
        super().setUp()
        self.exam, self.attempts = self.make_exam(self.maths, picks={self.amina: ["b", "b"], self.zawadi: ["a", "a"]})
        self.aid = self.attempts[self.amina.pk].pk

    def test_result_page_pays_xp_and_badges_once(self):
        c = self.client_for(self.amina)
        d = c.get(f"/api/results/{self.aid}/").json()
        kinds = {x["kind"]: x["points"] for x in d["rewards"]["xp"]}
        self.assertEqual(kinds, {"submit": 50, "early": 10, "score": 100, "perfect": 100})  # SRS 5.1
        self.assertEqual(d["rewards"]["xp_total"], 260)
        self.assertEqual({b["code"] for b in d["rewards"]["badges"]}, {"first_steps", "perfect_score", "steady_pace", "subject_star"})  # 100% is also the top grade (SRS 5.4)
        c.get(f"/api/results/{self.aid}/")  # opening it again pays nothing more
        self.assertEqual(services.total_xp(self.amina), 260)
        self.assertEqual(ExamRewardMark.objects.filter(user=self.amina).count(), 1)

    def test_home_summary_shows_xp_level_streak_and_badges(self):
        d = self.client_for(self.amina).get("/api/gamification/me/").json()  # also processes pending rewards
        self.assertEqual((d["xp"], d["level"]["level"], d["level"]["name"]), (260, 2, "Learner"))
        self.assertEqual(d["streak"]["current"], 1)
        self.assertEqual(len(d["recent_badges"]), 3)
        self.assertEqual(d["level_up"]["to"], 2)
        self.client_for(self.amina).post("/api/gamification/ack/")
        self.assertIsNone(self.client_for(self.amina).get("/api/gamification/me/").json()["level_up"])

    def test_no_rewards_before_results_are_visible(self):  # BR-10
        s = SchoolSettings.load()
        s.result_delay_minutes = 600
        s.save()
        self.assertEqual(services.reward_pending_for(self.amina), 0)
        self.assertEqual(services.total_xp(self.amina), 0)

    def test_failing_student_still_gets_effort_xp_and_nothing_negative(self):
        services.reward_pending_for(self.zawadi)
        self.assertEqual(services.total_xp(self.zawadi), 60)  # submit 50 + finish early 10, 0 percent
        self.assertFalse(BadgeAward.objects.filter(user=self.zawadi, code="perfect_score").exists())

    def test_scheduler_batch_is_idempotent_and_marks_never_change(self):
        from exams.models import Result
        before = list(Result.objects.values_list("score", flat=True).order_by("pk"))
        self.assertEqual(services.reward_pending(), 2)
        self.assertEqual(services.reward_pending(), 0)
        self.assertEqual(list(Result.objects.values_list("score", flat=True).order_by("pk")), before)  # BR-10

    def test_improvement_xp_needs_a_previous_exam(self):
        self.end = self.start - timedelta(hours=1)
        self.start = self.end - timedelta(hours=1)
        self.make_exam(self.maths, "Earlier", picks={self.amina: ["b", "a"]})  # 50 percent, earlier
        services.reward_pending_for(self.amina)
        self.assertTrue(XPEvent.objects.filter(user=self.amina, kind="improve").exists())  # 100 beat 50

    def test_streak_milestone_xp(self):
        cfg = services.config()
        today = timezone.localdate()
        for i in range(3):
            ActivityDay.objects.create(user=self.amina, day=today - timedelta(days=i), source="practice")
        services.sync_streak(self.amina, cfg)
        self.assertEqual(XPEvent.objects.get(user=self.amina, kind="streak").points, 15)
        services.sync_streak(self.amina, cfg)
        self.assertEqual(XPEvent.objects.filter(user=self.amina, kind="streak").count(), 1)

    def test_all_gamification_is_private(self):
        r = self.client_for(self.zawadi).get(f"/api/results/{self.aid}/")
        self.assertEqual(r.status_code, 404)
        r = self.client_for(self.zawadi).post(f"/api/results/{self.aid}/review/seen/", {"numbers": [1]}, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client_for(self.teacher).get("/api/gamification/me/").status_code, 403)


class ReviewTests(AnalyticsBase):
    def test_reviewing_every_wrong_answer_pays_once(self):
        exam, att = self.make_exam(self.maths, picks={self.amina: ["b", "a"]})  # question 2 is wrong
        a = att[self.amina.pk]
        c = self.client_for(self.amina)
        c.get(f"/api/results/{a.pk}/")
        info = c.get(f"/api/results/{a.pk}/review/seen/").json()
        self.assertEqual((info["wrong"], info["completed"]), ([2], False))
        r = c.post(f"/api/results/{a.pk}/review/seen/", {"numbers": [1]}, format="json").json()
        self.assertFalse(r["completed"])
        r = c.post(f"/api/results/{a.pk}/review/seen/", {"numbers": [2]}, format="json").json()
        self.assertEqual((r["completed"], r["xp_awarded"]), (True, 10))
        r = c.post(f"/api/results/{a.pk}/review/seen/", {"numbers": [2]}, format="json").json()
        self.assertEqual(r["xp_awarded"], 0)
        self.assertTrue(BadgeAward.objects.filter(user=self.amina, code="mistake_master").exists())

    def test_perfect_paper_has_nothing_to_review(self):
        exam, att = self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        r = self.client_for(self.amina).get(f"/api/results/{att[self.amina.pk].pk}/review/seen/").json()
        self.assertTrue(r["all_correct"])


class PracticeTests(AnalyticsBase):
    def setUp(self):
        super().setUp()
        self.qs = [practice_question(self.maths) for _ in range(6)]
        self.c = self.client_for(self.amina)

    def run_quiz(self, answer="b"):
        state = self.c.post("/api/practice/start/", {"subject_id": self.maths.pk, "count": 5}, format="json").json()
        sid = state["session_id"]
        while not state["finished"]:
            q = state["question"]
            self.assertNotIn("answer", q)  # the answer never travels with the question
            out = self.c.post(f"/api/practice/{sid}/answer/", {"question_id": q["id"], "response": answer}, format="json").json()
            state = out["next"]
        return sid, state, out

    def test_quiz_gives_instant_feedback_xp_and_a_learning_day(self):
        sid, state, last = self.run_quiz("b")
        self.assertTrue(last["feedback"]["correct"])
        self.assertEqual(last["feedback"]["explanation"], "Because 4.")
        self.assertEqual((state["summary"]["fully_correct"], state["summary"]["xp_earned"]), (5, 20))
        self.assertEqual(services.total_xp(self.amina), 20)
        self.assertTrue(ActivityDay.objects.filter(user=self.amina, day=timezone.localdate(), source="practice").exists())

    def test_wrong_answers_still_earn_effort_xp_and_never_touch_results(self):
        from exams.models import Result
        _, state, last = self.run_quiz("a")
        self.assertFalse(last["feedback"]["correct"])
        self.assertEqual(state["summary"]["xp_earned"], 20)
        self.assertEqual(Result.objects.count(), 0)

    def test_daily_xp_limit(self):
        s = services.GamificationSettings.load()
        s.practice_daily_xp_quizzes = 1
        s.save()
        self.run_quiz()
        _, state, _ = self.run_quiz()
        self.assertEqual(state["summary"]["xp_earned"], 0)
        self.assertEqual(services.total_xp(self.amina), 20)

    def test_questions_reserved_for_an_unpublished_exam_are_never_offered(self):
        exam = Exam.objects.create(title="Upcoming", subject=self.maths, status=Exam.DRAFT)
        ExamQuestion.objects.create(exam=exam, position=1, source=self.qs[0], payload=mcq())
        pool = services.practice_pool(self.amina, self.maths)
        self.assertEqual(pool.count(), 5)
        self.assertNotIn(self.qs[0].pk, set(pool.values_list("pk", flat=True)))

    def test_needs_five_questions_form_match_and_switch(self):
        practice_question(self.maths, eligible=False)
        Question.objects.filter(pk=self.qs[0].pk).update(practice_eligible=False)  # 5 left
        Question.objects.filter(pk=self.qs[1].pk).update(form_level=2)             # wrong form: 4 left
        r = self.c.post("/api/practice/start/", {"subject_id": self.maths.pk}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (409, "not_enough"))
        Question.objects.filter(pk=self.qs[1].pk).update(form_level=1)
        t = self.client_for(self.teacher).post(f"/api/practice/subjects/{self.maths.pk}/toggle/", {"enabled": False}, format="json")
        self.assertEqual(t.status_code, 200)
        r = self.c.post("/api/practice/start/", {"subject_id": self.maths.pk}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (403, "practice_off"))

    def test_teacher_cannot_switch_another_subject_and_students_cannot_switch(self):
        r = self.client_for(self.teacher).post(f"/api/practice/subjects/{self.english.pk}/toggle/", {"enabled": False}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.c.post(f"/api/practice/subjects/{self.maths.pk}/toggle/", {"enabled": False}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cannot_open_someone_elses_quiz_and_resend_is_safe(self):
        sid, state, _ = self.run_quiz()
        self.assertEqual(self.client_for(self.zawadi).get(f"/api/practice/{sid}/").status_code, 404)
        self.assertEqual(self.c.post(f"/api/practice/{sid}/answer/", {"question_id": 1, "response": "b"}, format="json").status_code, 409)

    def test_resume_unfinished_quiz(self):
        a = self.c.post("/api/practice/start/", {"subject_id": self.maths.pk}, format="json").json()
        b = self.c.post("/api/practice/start/", {"subject_id": self.maths.pk}, format="json").json()
        self.assertEqual(a["session_id"], b["session_id"])
        self.assertEqual(PracticeSession.objects.count(), 1)

    def test_bulk_mark_eligible_respects_teacher_subjects(self):
        other = practice_question(self.english, eligible=False)
        t = self.client_for(self.teacher)
        r = t.post("/api/practice/mark-eligible/", {"question_ids": [other.pk], "eligible": True}, format="json").json()
        self.assertEqual(r["updated"], 0)
        r = self.client_for(self.admin).post("/api/practice/mark-eligible/", {"question_ids": [other.pk], "eligible": True}, format="json").json()
        self.assertEqual(r["updated"], 1)


class LeaderboardTests(AnalyticsBase):
    def setUp(self):
        super().setUp()
        self.cls_a_mate = type(self.amina).objects.create(username="neema", first_name="Neema", last_name="Juma", role="student",
                                                         school_class=self.cls_a, index_number="S3")
        services.award_xp(self.amina, "practice", 40, "t1")
        services.award_xp(self.cls_a_mate, "practice", 70, "t2")
        services.award_xp(self.zawadi, "practice", 999, "t3")  # other class: never shown to Amina

    def enable(self, on=True):
        s = SchoolSettings.load()
        s.leaderboard_enabled = on
        s.save()

    def test_off_by_default(self):
        self.assertFalse(self.client_for(self.amina).get("/api/gamification/leaderboard/").json()["enabled"])

    def test_class_only_xp_only_and_names_not_ids(self):
        self.enable()
        d = self.client_for(self.amina).get("/api/gamification/leaderboard/").json()
        self.assertEqual([(e["rank"], e["name"], e["xp"]) for e in d["entries"]], [(1, "Neema J.", 70), (2, "Amina T.", 40)])
        self.assertEqual(d["you"]["rank"], 2)
        self.assertTrue(all(set(e) == {"rank", "name", "xp", "avatar", "level", "is_me"} for e in d["entries"]))

    def test_a_student_can_hide_herself(self):
        self.enable()
        c = self.client_for(self.amina)
        self.assertEqual(c.patch("/api/gamification/profile/", {"hide_from_leaderboard": True}, format="json").status_code, 200)
        d = self.client_for(self.cls_a_mate).get("/api/gamification/leaderboard/").json()
        self.assertEqual([e["name"] for e in d["entries"]], ["Neema J."])
        self.assertTrue(c.get("/api/gamification/leaderboard/").json()["you"]["hidden"])

    def test_profile_validation(self):
        c = self.client_for(self.amina)
        self.assertEqual(c.patch("/api/gamification/profile/", {"avatar": "dragon"}, format="json").status_code, 400)
        self.assertEqual(c.patch("/api/gamification/profile/", {"display_name": "x" * 31}, format="json").status_code, 400)
        self.assertEqual(c.patch("/api/gamification/profile/", {"avatar": "lion", "display_name": "Mama A"}, format="json").status_code, 200)


class AdminSettingsAndEngagementTests(AnalyticsBase):
    def test_only_admins_edit_and_values_are_validated(self):
        self.assertEqual(self.client_for(self.teacher).get("/api/gamification/settings/").status_code, 403)
        a = self.client_for(self.admin)
        self.assertEqual(a.patch("/api/gamification/settings/", {"xp_values": {"submit_exam": 60}}, format="json").status_code, 200)
        self.assertEqual(services.config()["xp"]["submit_exam"], 60)
        self.assertEqual(a.patch("/api/gamification/settings/", {"xp_values": {"submit_exam": -5}}, format="json").status_code, 400)
        self.assertEqual(a.patch("/api/gamification/settings/", {"badge_tiers": {"practice_pro": [10, 20, 30]}}, format="json").status_code, 200)
        self.assertEqual(services.config()["tiers"]["practice_pro"], [10, 20, 30])
        self.assertEqual(a.patch("/api/gamification/settings/", {"reset": True}, format="json").status_code, 200)
        self.assertEqual(services.config()["xp"]["submit_exam"], 50)

    def test_teacher_sees_streak_and_practice_activity_for_own_subject_only(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        services.reward_pending_for(self.amina)
        d = self.client_for(self.teacher).get(f"/api/analytics/subjects/{self.maths.pk}/students/{self.amina.pk}/").json()
        self.assertEqual(d["streak"]["current"], 1)
        self.assertEqual(d["practice_activity"]["practice_sessions"], 0)
        self.assertNotIn("xp_events", d)

    def test_school_engagement_for_admin(self):
        self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        services.reward_pending_for(self.amina)
        e = self.client_for(self.admin).get("/api/analytics/school/").json()["engagement"]
        self.assertEqual((e["students"], e["active_last_7_days"]), (2, 1))
        self.assertGreater(e["total_xp"], 0)


class LanguageTests(AnalyticsBase):
    def test_swahili_student_gets_swahili_text(self):
        self.amina.language = "sw"
        self.amina.save()
        exam, att = self.make_exam(self.maths, picks={self.amina: ["b", "b"]})
        d = self.client_for(self.amina).get(f"/api/results/{att[self.amina.pk].pk}/").json()
        self.assertEqual(d["rewards"]["xp"][0]["label"], "Umewasilisha mtihani")
        state = self.client_for(self.amina).get(f"/api/attempts/{att[self.amina.pk].pk}/").json()
        self.assertEqual(state["message"], "Hongera! Mtihani wako umewasilishwa.")
        self.assertEqual(len(state["tips"]), 3)
        from notifications.models import Notification
        self.assertIn("Matokeo tayari", Notification.objects.get(user=self.amina, kind="results_ready").title)

    def test_catalog_is_public(self):
        from rest_framework.test import APIClient
        d = APIClient().get("/api/i18n/sw/").json()
        self.assertEqual(d["levels"]["7"], "Kipanga")
        self.assertEqual(APIClient().get("/api/i18n/xx/").json()["lang"], "en")
