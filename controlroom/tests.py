from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from . import state
from .models import ControlEvent, SiteControl

PW = "Pw12345!xyz"


# The project uses a manifest static storage (needs `collectstatic`). Tests render admin pages, so use the plain storage here.
PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(CONTROLROOM_OWNERS="goose", STORAGES=PLAIN_STATIC)
class ControlRoomTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.owner = U.objects.create_superuser("goose", "g@x.tz", PW)
        self.other = U.objects.create_superuser("other", "o@x.tz", PW)
        self.student = U.objects.create_user("stu1", password=PW, role="student")
        self.tok_owner = Token.objects.create(user=self.owner)
        self.tok_student = Token.objects.create(user=self.student)
        state.reset_cache()

    def tearDown(self):
        state.reset_cache()

    def _on(self, client, **extra):
        client.get("/controlroom/")  # shows the words
        phrase = client.session["cr_phrase"]
        return client.post("/controlroom/maintenance/on/", {"phrase": phrase, **extra})

    def _auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def test_site_open_by_default(self):
        r = self.client.get("/api/site-status/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["maintenance"])
        self.assertEqual(self.client.get("/api/me/", **self._auth(self.tok_student)).status_code, 200)

    def test_only_owner_enters_control_room(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/controlroom/").status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/controlroom/").status_code, 200)

    def test_anonymous_goes_to_admin_login(self):
        r = self.client.get("/controlroom/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/django-admin/login/", r["Location"])

    def test_wrong_phrase_keeps_site_online(self):
        self.client.force_login(self.owner)
        self.client.get("/controlroom/")
        self.client.post("/controlroom/maintenance/on/", {"phrase": "not the words"})
        self.assertFalse(SiteControl.get().maintenance)
        self.assertTrue(ControlEvent.objects.filter(action="enable_refused").exists())

    def test_phrase_is_single_use(self):
        self.client.force_login(self.owner)
        self.client.get("/controlroom/")
        phrase = self.client.session["cr_phrase"]
        self.client.post("/controlroom/maintenance/on/", {"phrase": "wrong"})
        self.client.post("/controlroom/maintenance/on/", {"phrase": phrase})
        self.assertFalse(SiteControl.get().maintenance)

    def test_phrase_is_case_and_space_tolerant(self):
        self.client.force_login(self.owner)
        self.client.get("/controlroom/")
        phrase = self.client.session["cr_phrase"]
        self.client.post("/controlroom/maintenance/on/", {"phrase": "  " + phrase.upper().replace(" ", "   ") + " "})
        self.assertTrue(SiteControl.get().maintenance)

    def test_maintenance_blocks_everyone_but_owner(self):
        self.client.force_login(self.owner)
        self._on(self.client, message="Server upgrade", back_at="18:00")
        self.assertTrue(SiteControl.get().maintenance)
        anon = self.client_class()
        r = anon.get("/api/me/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["code"], "maintenance")
        self.assertEqual(r.json()["message"], "Server upgrade")
        self.assertEqual(anon.get("/").status_code, 503)
        # a student with a valid token is blocked too
        self.assertEqual(anon.get("/api/me/", **self._auth(self.tok_student)).status_code, 503)
        # the owner's token still works
        self.assertEqual(anon.get("/api/me/", **self._auth(self.tok_owner)).status_code, 200)
        # status endpoint stays up and says who is blocked
        self.assertTrue(anon.get("/api/site-status/").json()["blocked"])
        self.assertFalse(anon.get("/api/site-status/", **self._auth(self.tok_owner)).json()["blocked"])

    def test_only_owner_can_sign_in_while_off(self):
        self.client.force_login(self.owner)
        self._on(self.client)
        anon = self.client_class()
        ok = anon.post("/api/auth/login/", {"username": "goose", "password": PW}, content_type="application/json")
        self.assertEqual(ok.status_code, 200)
        no = anon.post("/api/auth/login/", {"username": "stu1", "password": PW}, content_type="application/json")
        self.assertEqual(no.status_code, 503)
        no2 = anon.post("/api/auth/login/", {"username": "other", "password": PW}, content_type="application/json")
        self.assertEqual(no2.status_code, 503)  # a superuser who is not the owner

    def test_other_superuser_cannot_use_admin_in_maintenance(self):
        self.client.force_login(self.owner)
        self._on(self.client)
        o = self.client_class()
        o.force_login(self.other)
        self.assertEqual(o.get("/controlroom/").status_code, 503)
        self.assertEqual(o.get("/django-admin/").status_code, 503)

    def test_forged_token_does_not_pass(self):
        self.client.force_login(self.owner)
        self._on(self.client)
        self.assertEqual(self.client_class().get("/api/me/", HTTP_AUTHORIZATION="Token nope").status_code, 503)

    def test_sign_everyone_out(self):
        self.client.force_login(self.owner)
        self._on(self.client, logout_all="on")
        self.assertFalse(Token.objects.filter(user=self.student).exists())
        self.assertTrue(Token.objects.filter(user=self.owner).exists())

    def test_turn_back_on(self):
        self.client.force_login(self.owner)
        self._on(self.client)
        self.client.post("/controlroom/maintenance/off/")
        self.assertFalse(SiteControl.get().maintenance)
        state.reset_cache()
        self.assertEqual(self.client_class().get("/api/site-status/").json()["maintenance"], False)
        self.assertEqual(self.client_class().get("/api/me/", **self._auth(self.tok_student)).status_code, 200)

    def test_god_eye_and_tables(self):
        self.client.force_login(self.owner)
        r = self.client.get("/controlroom/eye/data/")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["users"]["total"], 3)
        self.assertIn("guardians.smsjob", [c["label"] for c in r.json()["counts"]])
        r = self.client.get("/controlroom/eye/tables/accounts.user/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"pbkdf2", r.content)  # password hashes are always hidden
        self.assertNotIn(self.tok_owner.key.encode(), self.client.get("/controlroom/eye/tables/authtoken.token/").content)  # tokens too
        self.assertEqual(self.client.get("/controlroom/eye/tables/nope.nothing/").status_code, 404)

    def test_god_eye_denied_to_non_owner(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/controlroom/eye/data/").status_code, 403)

    def test_shell_command(self):
        call_command("maintenance", "on", "--message", "x")
        self.assertTrue(SiteControl.get().maintenance)
        call_command("maintenance", "off")
        self.assertFalse(SiteControl.get().maintenance)
