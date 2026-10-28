"""Pure tests (no database). Run with:  python manage.py test analytics"""
from datetime import datetime, timedelta
from unittest import TestCase

from core.grading import DEFAULT_SCALE
from . import calc

T0 = datetime(2026, 11, 1)


def row(student=1, exam=1, percent=50, grade="C", passed=True, cls=1, label="Form 1", day=0, topics=None, no=1):
    return dict(result_id=1, attempt_id=1, attempt_no=no, student_id=student, student_name=f"S{student}", class_id=cls,
                class_label=label, stream="", exam_id=exam, exam_title=f"E{exam}", subject_id=1, subject="Maths",
                term_id=None, date=T0 + timedelta(days=day), percent=percent, grade=grade, points=3, passed=passed,
                time_taken=600, topic_stats=topics or {}, scale=DEFAULT_SCALE)


class CalcTests(TestCase):
    def test_summary_and_trend(self):
        rows = [row(1, 1, 80, "A"), row(2, 1, 20, "F", passed=False), row(1, 2, 60, "C")]
        s = calc.summary(rows[:2])
        self.assertEqual((s["average"], s["highest"], s["lowest"], s["pass_rate"]), (50.0, 80, 20, 50.0))
        self.assertEqual(s["grade_distribution"], {"A": 1, "F": 1})
        t = calc.trend(rows)
        self.assertEqual([x["exam_id"] for x in t], [1, 2])
        self.assertEqual(t[0]["participants"], 2)
        self.assertEqual(calc.summary([])["average"], None)

    def test_retake_replaces_first_attempt(self):
        rows = calc.latest_attempts([row(1, 1, 20, no=1), row(1, 1, 70, no=2)])
        self.assertEqual([r["percent"] for r in rows], [70])

    def test_topics_heatmap_and_strengths(self):
        rows = [row(1, topics={"Algebra": [9, 10], "Geometry": [2, 10]}, cls=1, label="Form 1 A"),
                row(2, topics={"Algebra": [5, 10]}, cls=2, label="Form 1 B")]
        tp = calc.topic_percentages(rows)
        self.assertEqual([t["topic"] for t in tp], ["Geometry", "Algebra"])  # weakest first
        sw = calc.strengths_and_weaknesses(tp)
        self.assertEqual(sw["strengths"][0]["topic"], "Algebra")
        self.assertEqual(sw["weak_areas"][0]["topic"], "Geometry")
        hm = calc.heatmap(rows)
        self.assertEqual(hm["topics"], ["Algebra", "Geometry"])
        self.assertEqual(hm["cells"], [[90.0, 50.0], [20.0, None]])

    def test_flags(self):
        self.assertEqual(calc.flag_for([80, 25])[0], "needs_support")  # latest below pass level
        self.assertEqual(calc.flag_for([70, 62, 55])[0], "needs_support")  # falling by 15
        self.assertEqual(calc.flag_for([40, 42, 44])[0], "needs_support")  # low average
        self.assertEqual(calc.flag_for([80, 76, 90])[0], "top_performer")
        self.assertEqual(calc.flag_for([60, 58, 62])[0], None)
        self.assertEqual(calc.flag_for([]), (None, ""))

    def test_question_stats(self):
        p = {"qtype": "mcq_single", "prompt": "2+2?", "topic": "Algebra", "difficulty": "easy", "marks": 1,
             "content": {"options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}, {"id": "c", "text": "5"}]},
             "answer": {"correct": "b"}}
        qs = [{"id": 10, "position": 1, "voided": False, "payload": p}]
        ans = [{"exam_question_id": 10, "response": r, "skipped": False} for r in ("b", "a", "a", "c")]
        out = calc.question_stats(qs, ans, n_attempts=5)  # one student never answered
        self.assertEqual(out[0]["percent_correct"], 20.0)
        self.assertEqual(out[0]["observed_difficulty"], "hard")
        self.assertEqual(out[0]["most_chosen_wrong"]["text"], "3")
        self.assertEqual(out[0]["most_chosen_wrong"]["count"], 2)

    def test_fill_blank_and_true_false_wrong_answers(self):
        fb = {"qtype": "fill_blank", "prompt": "x", "answer": {"accepted": ["nairobi"]}, "marks": 1}
        out = calc.question_stats([{"id": 1, "position": 1, "voided": False, "payload": fb}],
                                  [{"exam_question_id": 1, "response": r, "skipped": False} for r in ("Arusha", " arusha", "Nairobi")], 3)
        self.assertEqual(out[0]["most_chosen_wrong"]["text"], "arusha")
        tf = {"qtype": "true_false", "prompt": "y", "answer": {"correct": True}, "marks": 1}
        out = calc.question_stats([{"id": 2, "position": 1, "voided": False, "payload": tf}],
                                  [{"exam_question_id": 2, "response": False, "skipped": False}], 1)
        self.assertEqual(out[0]["most_chosen_wrong"]["text"], "False")

    def test_report_card_best_seven_and_projection(self):
        avgs = {f"S{i}": 80 for i in range(7)}
        rc = calc.report_card(avgs, DEFAULT_SCALE)
        self.assertEqual((rc["total_points"], rc["division"]), (7, "I"))
        avgs = {f"S{i}": 80 for i in range(7)}
        avgs.update({"Bad1": 10, "Bad2": 10})  # two weak extra subjects are not counted
        rc = calc.report_card(avgs, DEFAULT_SCALE)
        self.assertEqual(rc["division"], "I")
        self.assertEqual(sum(1 for s in rc["subjects"] if s["counted"]), 7)
        few = calc.report_card({"Maths": 80}, DEFAULT_SCALE)
        self.assertIsNone(few["division"])
        self.assertEqual(few["subjects_needed"], 7)
