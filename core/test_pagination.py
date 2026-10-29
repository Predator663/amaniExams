"""Paging is opt-in (?page=) and the old plain lists keep working.  Run with:  python manage.py test core.test_pagination"""
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from academics.models import SchoolClass
from accounts.models import User
from core.models import audit
from notifications.models import Notification


class PagingTests(TestCase):
    def setUp(self):
        self.cls = SchoolClass.objects.create(name="Form 1", form_level=1)
        self.admin = User.objects.create(username="admin1", role="admin", password=make_password("Adm1n-pass!"))
        for i in range(25):
            User.objects.create(username=f"s{i:02}", role="student", school_class=self.cls, last_name="Same",
                                index_number=f"S{i:02}", password=make_password("x"))
        self.api = self.client_for(self.admin)

    def client_for(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Token " + Token.objects.get_or_create(user=user)[0].key)
        return c

    def test_plain_list_when_no_page(self):
        r = self.api.get("/api/students/")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        self.assertEqual(len(r.json()), 25)

    def test_pages_have_the_envelope_and_do_not_overlap(self):
        seen = []
        for p in (1, 2, 3):
            r = self.api.get(f"/api/students/?page={p}&page_size=10")
            self.assertEqual(r.status_code, 200)
            d = r.json()
            self.assertEqual((d["count"], d["pages"], d["page"], d["page_size"]), (25, 3, p, 10))
            seen += [s["id"] for s in d["results"]]
        self.assertEqual(len(seen), 25)
        self.assertEqual(len(set(seen)), 25)  # equal last names never swap places between pages

    def test_page_past_the_end_shows_the_last_page(self):
        d = self.api.get("/api/students/?page=99&page_size=10").json()
        self.assertEqual((d["page"], len(d["results"])), (3, 5))

    def test_bad_numbers_are_a_400_and_size_is_capped(self):
        self.assertEqual(self.api.get("/api/students/?page=abc").status_code, 400)
        self.assertEqual(self.api.get("/api/students/?page=1&page_size=100000").json()["page_size"], 100)

    def test_filters_still_apply_to_a_page(self):
        d = self.api.get("/api/students/?page=1&page_size=10&q=s07").json()
        self.assertEqual(d["count"], 1)

    def test_empty_list_is_one_empty_page(self):
        d = self.api.get("/api/teachers/?page=1").json()
        self.assertEqual((d["count"], d["pages"], d["page"], d["results"]), (0, 1, 1, []))

    def test_notifications_keep_the_items_key_and_the_unread_count(self):
        u = User.objects.get(username="s00")
        for i in range(30):
            Notification.objects.create(user=u, kind="announcement", title=f"n{i}")
        c = self.client_for(u)
        old = c.get("/api/notifications/").json()
        self.assertEqual(len(old["items"]), 30)
        self.assertNotIn("pages", old)
        d = c.get("/api/notifications/?page=2&page_size=20").json()
        self.assertEqual((d["unread"], d["count"], d["pages"], len(d["items"])), (30, 30, 2, 10))

    def test_audit_log_pages_and_old_limit_offset_still_work(self):
        for i in range(30):
            audit(self.admin, "test.row", i)
        d = self.api.get("/api/audit-log/?page=2&page_size=25").json()
        self.assertEqual((d["count"], d["pages"], d["page"], len(d["results"])), (30, 2, 2, 5))
        old = self.api.get("/api/audit-log/?limit=10&offset=5").json()
        self.assertEqual(len(old["results"]), 10)
        self.assertNotIn("pages", old)
