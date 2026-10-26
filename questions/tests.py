from django.test import TestCase
from rest_framework.exceptions import ValidationError

from .validation import validate_question


class QuestionValidationTests(TestCase):
    def test_mcq_needs_a_correct_answer(self):
        content = {"options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}]}
        with self.assertRaises(ValidationError):
            validate_question("mcq_single", content, {})
        c, a = validate_question("mcq_single", content, {"correct": "a"})
        self.assertEqual(a, {"correct": "a"})

    def test_image_requires_alt_text(self):
        content = {"options": [{"id": "a", "text": "", "image": "/m/x.webp"}, {"id": "b", "text": "y"}]}
        with self.assertRaises(ValidationError):
            validate_question("mcq_single", content, {"correct": "a"})

    def test_script_in_text_is_stripped(self):
        content = {"options": [{"id": "a", "text": "<script>alert(1)</script>ok"}, {"id": "b", "text": "y"}]}
        c, _ = validate_question("mcq_single", content, {"correct": "a"})
        self.assertNotIn("<script>", c["options"][0]["text"])

    def test_ordering_answer_derived_from_authored_order(self):
        items = [{"id": "1", "text": "first"}, {"id": "2", "text": "second"}]
        _, a = validate_question("ordering", {"items": items}, {})
        self.assertEqual(a["order"], ["1", "2"])

    def test_matching_must_cover_every_left_item(self):
        content = {"left": [{"id": "l1", "text": "a"}, {"id": "l2", "text": "b"}],
                   "right": [{"id": "r1", "text": "x"}, {"id": "r2", "text": "y"}]}
        with self.assertRaises(ValidationError):
            validate_question("matching", content, {"pairs": {"l1": "r1"}})
        validate_question("matching", content, {"pairs": {"l1": "r1", "l2": "r2"}})
