"""Admin messages to one account.  python manage.py test notifications.test_messages"""
from django.contrib.auth.hashers import make_password

from accounts.models import User
from exams.tests import Base
from .models import AdminMessage


class AdminMessages(Base):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create(username="mwl", role="teacher", password=make_password("T3acher-pass!"))

    def send(self, ids, body="Please sit apart from your sister.", who=None):
        return self.client_for(who or self.admin).post("/api/admin/messages/", {"recipients": ids, "body": body}, format="json")

    def test_admin_sends_and_the_person_sees_a_banner_then_it_stays_in_her_tab(self):
        self.assertEqual(self.send([self.amina.pk]).status_code, 201)
        c = self.client_for(self.amina)
        r = c.get("/api/messages/?banner=1").json()
        self.assertEqual((r["unseen"], len(r["items"]), r["items"][0]["body"]), (1, 1, "Please sit apart from your sister."))
        mid = r["items"][0]["id"]
        self.assertEqual(c.post(f"/api/messages/{mid}/dismiss/").status_code, 200)  # she tapped the banner away
        self.assertEqual(c.get("/api/messages/?banner=1").json(), {"unseen": 0, "items": []})
        tab = c.get("/api/messages/").json()
        self.assertEqual((tab["unseen"], len(tab["items"]), tab["items"][0]["dismissed"]), (0, 1, True))  # still in the Messages tab
        sent = self.client_for(self.admin).get("/api/admin/messages/").json()["results"][0]
        self.assertTrue(sent["seen"])
        self.assertEqual((sent["recipient"]["name"], sent["recipient"]["role"]), ("amina", "student"))

    def test_only_the_admin_can_delete_and_it_disappears_for_the_person(self):
        self.send([self.amina.pk, self.teacher.pk])
        m = AdminMessage.objects.get(recipient=self.amina)
        c = self.client_for(self.amina)
        self.assertEqual(c.delete(f"/api/admin/messages/{m.pk}/").status_code, 403)  # she cannot delete it herself
        self.assertEqual(self.client_for(self.teacher).delete(f"/api/admin/messages/{m.pk}/").status_code, 403)
        self.assertEqual(self.client_for(self.admin).delete(f"/api/admin/messages/{m.pk}/").status_code, 200)
        self.assertEqual(c.get("/api/messages/").json(), {"unseen": 0, "items": []})
        self.assertEqual(self.client_for(self.teacher).get("/api/messages/").json()["unseen"], 1)  # the teacher's own copy is separate

    def test_teachers_can_receive_too_and_nobody_reads_or_dismisses_another_persons_message(self):
        self.send([self.teacher.pk], "Marking meeting at 3pm.")
        self.assertEqual(self.client_for(self.teacher).get("/api/messages/").json()["items"][0]["body"], "Marking meeting at 3pm.")
        m = AdminMessage.objects.get()
        self.assertEqual(self.client_for(self.amina).get("/api/messages/").json()["items"], [])
        self.assertEqual(self.client_for(self.amina).post(f"/api/messages/{m.pk}/dismiss/").status_code, 404)
        m.refresh_from_db()
        self.assertIsNone(m.dismissed_at)

    def test_validation_and_permissions(self):
        self.assertEqual(self.send([self.amina.pk], "   ").status_code, 400)
        self.assertEqual(self.send([self.amina.pk], "x" * 1001).status_code, 400)
        for bad in ([], None, "x", [self.amina.pk, "z"], list(range(1, 40))):
            self.assertEqual(self.send(bad).status_code, 400, bad)
        self.assertEqual(self.send([self.admin.pk]).status_code, 400)  # not to administrators
        self.assertEqual(self.send([99999]).status_code, 400)
        for who in (self.amina, self.teacher):
            self.assertEqual(self.send([self.zawadi.pk], who=who).status_code, 403)
            self.assertEqual(self.client_for(who).get("/api/admin/messages/").status_code, 403)
        self.assertFalse(AdminMessage.objects.exists())

    def test_one_message_to_several_people_and_the_list_can_be_filtered(self):
        self.assertEqual(self.send([self.amina.pk, self.zawadi.pk]).json()["sent"], 2)
        self.assertEqual(AdminMessage.objects.count(), 2)
        rows = self.client_for(self.admin).get(f"/api/admin/messages/?user={self.zawadi.pk}").json()["results"]
        self.assertEqual([r["recipient"]["id"] for r in rows], [self.zawadi.pk])
