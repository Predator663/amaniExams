"""Phase 2 admin-portal tests. Run:  python manage.py test accounts"""
from django.contrib.auth.hashers import make_password

from analytics.tests import AnalyticsBase
from academics.models import Subject
from accounts import temp_password
from accounts.models import User

STRONG = "Strong-Pass-2026"


class AdminPortalTests(AnalyticsBase):
    def setUp(self):
        super().setUp()
        self.super = User.objects.create(username="boss", role="super_admin", password=make_password("Sup3r-pass-1"))
        self.a = self.client_for(self.admin)

    def test_teacher_account_needs_strong_password_and_forced_change(self):
        weak = self.a.post("/api/teachers/", {"username": "mwl", "first_name": "M", "last_name": "W", "password": "short1"}, format="json")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("password", weak.json())
        ok = self.a.post("/api/teachers/", {"username": "mwl", "first_name": "M", "last_name": "W", "password": STRONG}, format="json")
        self.assertEqual(ok.status_code, 201)
        self.assertNotIn("password", ok.json())
        u = User.objects.get(username="mwl")
        self.assertEqual((u.role, u.must_change_password), ("teacher", True))
        self.assertTrue(u.check_password(STRONG))

    def test_only_admins_manage_teachers_and_only_super_admin_manages_admins(self):
        t = self.client_for(self.teacher)
        self.assertEqual(t.get("/api/teachers/").status_code, 403)
        self.assertEqual(self.a.post("/api/admins/", {"username": "x", "password": STRONG}, format="json").status_code, 403)
        s = self.client_for(self.super)
        r = s.post("/api/admins/", {"username": "newadmin", "first_name": "N", "last_name": "A", "password": STRONG}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(User.objects.get(username="newadmin").role, "admin")
        self.assertEqual(s.delete(f"/api/admins/{User.objects.get(username='newadmin').pk}/").status_code, 204)
        self.assertEqual(s.delete(f"/api/admins/{self.super.pk}/").status_code, 404)  # a Super Admin is not in the admins list, so she cannot be removed here

    def test_reset_teacher_password_returns_temporary_once(self):
        r = self.a.post(f"/api/teachers/{self.teacher.pk}/reset-password/", {}, format="json")
        pw = r.json()["temporary_password"]
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password(pw))
        self.assertTrue(self.teacher.must_change_password)
        weak = self.a.post(f"/api/teachers/{self.teacher.pk}/reset-password/", {"new_password": "abc"}, format="json")
        self.assertEqual(weak.status_code, 400)

    def test_deactivate_teacher_keeps_account_and_logs_out(self):
        tc = self.client_for(self.teacher)
        self.assertEqual(self.a.delete(f"/api/teachers/{self.teacher.pk}/").status_code, 204)
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertEqual(tc.get("/api/me/").status_code, 401)

    def test_student_lifecycle_actions(self):
        self.assertEqual(self.a.post(f"/api/students/{self.amina.pk}/move/", {"school_class": self.cls_b.pk}, format="json").status_code, 200)
        self.amina.refresh_from_db()
        self.assertEqual(self.amina.school_class_id, self.cls_b.pk)
        self.a.post(f"/api/students/{self.amina.pk}/graduate/")
        self.amina.refresh_from_db()
        self.assertEqual((self.amina.graduated, self.amina.is_active), (True, False))
        self.a.post(f"/api/students/{self.amina.pk}/activate/")
        self.amina.refresh_from_db()
        self.assertEqual((self.amina.graduated, self.amina.is_active), (False, True))

    def test_bulk_actions(self):
        ids = [self.amina.pk, self.zawadi.pk]
        r = self.a.post("/api/students/bulk-action/", {"ids": ids, "action": "change_class", "school_class": self.cls_b.pk}, format="json")
        self.assertEqual(r.json()["affected"], 2)
        r = self.a.post("/api/students/bulk-action/", {"ids": ids, "action": "reset_passwords"}, format="json")
        self.amina.refresh_from_db()
        self.assertTrue(self.amina.must_change_password)
        self.assertFalse(self.amina.check_password("S1"))  # NOT the index number any more
        self.assertTrue(self.amina.check_password(temp_password.password_for(self.amina)))  # a random code from the credentials sheet
        self.assertEqual(self.a.post("/api/students/bulk-action/", {"ids": ids, "action": "nope"}, format="json").status_code, 400)
        self.assertEqual(self.client_for(self.teacher).post("/api/students/bulk-action/", {"ids": ids, "action": "deactivate"}, format="json").status_code, 403)

    def test_credential_sheet_pdf_lists_only_students_still_on_starting_password(self):
        temp_password.issue(self.amina)
        r = self.a.get(f"/api/students/credentials/?class={self.cls_a.pk}")
        self.assertTrue(r.content.startswith(b"%PDF"))
        csv = self.a.get("/api/students/credentials/?file=csv")
        self.assertIn(b"amina", csv.content)
        self.assertNotIn(b"zawadi", csv.content)  # zawadi already has her own password

    def test_academic_years_and_terms(self):
        y = self.a.post("/api/academic-years/", {"name": "2026", "is_current": True}, format="json").json()
        t = self.a.post("/api/terms/", {"year": y["id"], "name": "Term 1", "start_date": "2026-01-05", "end_date": "2026-06-05"}, format="json")
        self.assertEqual(t.status_code, 201)
        bad = self.a.post("/api/terms/", {"year": y["id"], "name": "Term 2", "start_date": "2026-07-01", "end_date": "2026-06-01"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(len(self.client_for(self.amina).get("/api/terms/").json()), 1)  # students may read
        self.assertEqual(self.client_for(self.amina).post("/api/terms/", {}, format="json").status_code, 403)

    def test_accessibility_preferences_are_saved_and_clamped(self):
        c = self.client_for(self.amina)
        d = c.patch("/api/me/", {"text_size": 250, "dyslexia_font": True, "reduce_motion": "true", "theme": "high_contrast"}, format="json").json()
        self.assertEqual(d["accessibility"]["text_size"], 200)
        self.assertTrue(d["accessibility"]["dyslexia_font"] and d["accessibility"]["reduce_motion"])
        self.assertEqual(d["theme"], "high_contrast")
        self.assertEqual(c.patch("/api/me/", {"text_size": "huge"}, format="json").status_code, 400)

    def test_modern_warfare_theme_can_be_chosen(self):
        c = self.client_for(self.amina)
        self.assertEqual(c.patch("/api/me/", {"theme": "mw3"}, format="json").json()["theme"], "mw3")
        self.assertEqual(c.patch("/api/me/", {"theme": "neon"}, format="json").status_code, 400)

    def test_password_change_creates_notification(self):
        from notifications.models import Notification
        c = self.client_for(self.amina)
        r = c.post("/api/auth/change-password/", {"old_password": "pw-amina-1", "new_password": "A-better-pass-9"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.amina, kind="password_changed").exists())
