"""Parents, encrypted contacts, and the SMS queue.  Run:  python manage.py test guardians"""
import io
import re
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import User
from analytics.tests import AnalyticsBase
from core.models import AuditLog
from . import crypto
from .models import Guardian, GuardianLink, SmsConfig, SmsJob
from .phones import mask, normalize_phone

CSV = ("parent_name,phone,relationship,student_index,whatsapp,language\n"
       "Mama Amina,0712 345 678,mother,S100,yes,sw\n"
       "Baba Zawadi,+255755123456,father,S101;S100,no,en\n"
       "Bad Phone,12345,aunt,S100,,\n"
       "Ghost,0712999888,aunt,NOPE,,\n")


def csv_file(text=CSV, name="parents.csv"):
    return SimpleUploadedFile(name, text.encode(), content_type="text/csv")


class PhoneTests(AnalyticsBase):
    def test_tanzanian_numbers_are_normalised(self):
        for raw in ("0712345678", "712345678", "255712345678", "+255 712 345 678", "00255712345678", 712345678.0, " 0712-345-678 "):
            self.assertEqual(normalize_phone(raw), "+255712345678", raw)
        for bad in ("", None, "12345", "0512345678", "+255 812 345 678", "07123456789", "abc"):
            self.assertIsNone(normalize_phone(bad), bad)
        self.assertEqual(mask("+255712345678"), "+255 7•• ••• 678")


class GuardianBase(AnalyticsBase):
    def setUp(self):
        super().setUp()
        User.objects.filter(pk=self.amina.pk).update(index_number="S100", must_change_password=True)
        User.objects.filter(pk=self.zawadi.pk).update(index_number="S101", must_change_password=True)
        self.amina.refresh_from_db()
        self.zawadi.refresh_from_db()
        self.a = self.client_for(self.admin)

    def upload(self, confirm=False, skip=False, text=CSV):
        return self.a.post("/api/guardians/upload/", {"file": csv_file(text), "confirm": str(confirm).lower(), "skip_invalid": str(skip).lower()}, format="multipart")

    def load(self, public_url="amani.example"):
        self.assertEqual(self.upload(True, True).status_code, 200)
        c = SmsConfig.load()
        c.public_url = public_url
        c.save()


class UploadTests(GuardianBase):
    def test_preview_saves_nothing_and_reports_each_row(self):
        r = self.upload()
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual((d["total_rows"], d["valid_rows"], d["invalid_rows"], d["parents_new"]), (4, 2, 2, 2))
        self.assertEqual([x["status"] for x in d["rows"]], ["ok", "ok", "error", "error"])
        self.assertIn("valid Tanzanian", d["rows"][2]["problems"][0])
        self.assertIn("No active student", d["rows"][3]["problems"][0])
        self.assertNotIn("0712 345 678", str(d))  # numbers are masked even in the preview
        self.assertEqual(Guardian.objects.count(), 0)

    def test_confirm_needs_skip_when_rows_are_bad_then_links_children(self):
        self.assertEqual(self.upload(True, False).status_code, 400)
        r = self.upload(True, True)
        self.assertEqual((r.status_code, r.json()["parents_created"], r.json()["links_created"], r.json()["skipped"]), (200, 2, 3, 2))
        baba = [g for g in Guardian.objects.all() if g.name == "Baba Zawadi"][0]
        self.assertEqual(baba.links.count(), 2)  # two daughters
        self.assertEqual((baba.language, baba.has_whatsapp), ("en", False))
        self.assertEqual(self.upload(True, True).json()["parents_created"], 0)  # uploading again duplicates nothing

    def test_same_phone_twice_in_a_file_makes_one_parent(self):
        text = "parent_name,phone,student_index\nMama,0712345678,S100\nMama,712345678,S101\n"
        self.assertEqual(self.upload(True, False, text).status_code, 200)
        self.assertEqual((Guardian.objects.count(), GuardianLink.objects.count()), (1, 2))

    def test_xlsx_is_accepted(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Parent name", "Phone", "Student index"])
        ws.append(["Mama X", 712345678, "S100"])
        buf = io.BytesIO()
        wb.save(buf)
        f = SimpleUploadedFile("p.xlsx", buf.getvalue())
        r = self.a.post("/api/guardians/upload/", {"file": f, "confirm": "true"}, format="multipart")
        self.assertEqual((r.status_code, r.json().get("parents_created")), (200, 1))


class PrivacyTests(GuardianBase):
    def test_name_and_phone_are_encrypted_in_the_database(self):
        self.load()
        from django.db import connection
        with connection.cursor() as c:
            c.execute("select name_enc, phone_enc, phone_idx from guardians_guardian")
            raw = " ".join(" ".join(r) for r in c.fetchall())
        for secret in ("Mama Amina", "Baba Zawadi", "712345678", "755123456"):
            self.assertNotIn(secret, raw)
        self.assertEqual(sorted(g.name for g in Guardian.objects.all()), ["Baba Zawadi", "Mama Amina"])
        self.assertEqual(crypto.decrypt("not-a-token"), "")

    def test_list_masks_numbers_and_reveal_is_audited(self):
        self.load()
        d = self.a.get("/api/guardians/").json()
        self.assertEqual(d["total"], 2)
        self.assertNotIn("712345678", str(d))
        g = d["results"][0]
        self.assertRegex(g["phone"], r"^\+255 \d•• ••• \d{3}$")
        r = self.a.get(f"/api/guardians/{g['id']}/reveal/").json()
        self.assertTrue(r["phone"].startswith("+255"))
        self.assertTrue(AuditLog.objects.filter(action="guardian.reveal").exists())
        self.assertNotIn(r["phone"], str(list(AuditLog.objects.values_list("detail", "target"))))

    def test_only_admins_can_use_it(self):
        t = self.client_for(self.teacher)
        s = self.client_for(self.amina)
        for url in ("/api/guardians/", "/api/guardians/summary/", "/api/guardians/jobs/", "/api/guardians/devices/", "/api/guardians/config/"):
            self.assertEqual(t.get(url).status_code, 403, url)
            self.assertIn(s.get(url).status_code, (401, 403), url)
        self.assertEqual(t.post("/api/guardians/send/", {"scope": "all"}, format="json").status_code, 403)

    def test_search_edit_link_unlink(self):
        self.load()
        g = self.a.get("/api/guardians/?q=0712345").json()["results"]
        self.assertEqual([x["name"] for x in g], ["Mama Amina"])
        gid = g[0]["id"]
        self.assertEqual(self.a.patch(f"/api/guardians/{gid}/", {"phone": "0699111222", "relationship": "aunt"}, format="json").status_code, 200)
        self.assertEqual(self.a.patch(f"/api/guardians/{gid}/", {"phone": "0755123456"}, format="json").status_code, 409)  # belongs to Baba Zawadi
        self.assertEqual(self.a.post(f"/api/guardians/{gid}/links/", {"student_index": "S101"}, format="json").status_code, 200)
        self.assertEqual(self.a.delete(f"/api/guardians/{gid}/links/?student={self.amina.pk}").status_code, 200)
        self.assertEqual(Guardian.objects.get(pk=gid).links.count(), 1)

    def test_summary_lists_students_without_a_parent(self):
        self.load()
        d = self.a.get("/api/guardians/summary/").json()
        self.assertEqual((d["parents"], d["phone_online"]), (2, False))
        self.assertTrue(d["students_waiting_first_login"] >= 2)


class SendTests(GuardianBase):
    def test_dry_run_changes_nothing_and_a_web_address_is_required(self):
        self.load(public_url="")
        old = User.objects.get(pk=self.amina.pk).password
        r = self.a.post("/api/guardians/send/", {"scope": "all"}, format="json").json()
        self.assertEqual((r["dry_run"], r["messages"], r["students"]), (True, 2, 3))
        self.assertEqual(User.objects.get(pk=self.amina.pk).password, old)
        self.assertEqual(SmsJob.objects.count(), 0)
        self.assertEqual(self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json").status_code, 400)

    def test_queue_gives_new_random_passwords_and_one_message_per_parent(self):
        self.load()
        r = self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        self.assertEqual((r.status_code, r.json()["queued"]), (201, 2))
        self.assertEqual(SmsJob.objects.count(), 2)
        job = [j for j in SmsJob.objects.all() if len(j.students) == 2][0]  # Baba Zawadi has both daughters
        body = crypto.decrypt(job.body_enc)
        self.assertLessEqual(len(body.split("\n")), 5)
        self.assertIn("amani.example", body)
        # the password in the text really works, and must be changed at first login
        line = [l for l in body.split("\n") if self.zawadi.username in l][0]
        pw = line.split("password ")[1].strip().rstrip(",")
        self.zawadi.refresh_from_db()
        self.assertTrue(self.zawadi.check_password(pw))
        self.assertTrue(self.zawadi.must_change_password)
        self.assertNotIn("S100", job.summary + body)  # index numbers never travel in the SMS
        self.assertNotIn(pw, job.summary)

    def test_second_send_skips_those_already_sent_or_logged_in(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        r = self.a.post("/api/guardians/send/", {"scope": "all"}, format="json").json()
        self.assertEqual((r["messages"], r["skipped"]["already_sent"]), (0, 3))
        User.objects.filter(pk=self.zawadi.pk).update(must_change_password=False)
        SmsJob.objects.all().delete()
        r = self.a.post("/api/guardians/send/", {"scope": "all"}, format="json").json()
        self.assertEqual((r["messages"], r["students"], r["skipped"]["already_logged_in"]), (2, 2, 1))  # Amina (two parents) is still waiting; Zawadi is not
        r = self.a.post("/api/guardians/send/", {"scope": "all", "resend": True}, format="json").json()
        self.assertEqual(r["students"], 3)  # resend ignores the logged-in rule

    def test_send_to_one_class_only(self):
        self.load()
        r = self.a.post("/api/guardians/send/", {"scope": "class", "class_id": self.amina.school_class_id}, format="json").json()
        self.assertEqual((r["messages"], r["students"]), (2, 2))  # Amina's two parents
        b = self.a.post("/api/guardians/send/", {"scope": "class", "class_id": self.zawadi.school_class_id}, format="json").json()
        self.assertEqual((b["messages"], b["students"]), (1, 1))  # only Baba Zawadi, for Zawadi

    def test_a_student_with_two_parents_gets_the_same_working_password_in_both_messages(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        pws = set()
        for j in SmsJob.objects.all():
            for line in crypto.decrypt(j.body_enc).split("\n"):
                if line.startswith("Amina Test"):
                    pws.add(re.search(r"(?:password|nenosiri) (\S+?),?$", line).group(1))
        self.assertEqual(len(pws), 1)
        self.amina.refresh_from_db()
        self.assertTrue(self.amina.check_password(pws.pop()))


class PhoneAppTests(GuardianBase):
    def pair(self):
        r = self.a.post("/api/guardians/devices/", {"name": "School phone"}, format="json")
        self.assertEqual(r.status_code, 201)
        tok = r.json()["token"]
        self.assertNotIn("token", self.a.get("/api/guardians/devices/").json()[0])  # shown only once
        return tok, {"HTTP_X_DEVICE_TOKEN": tok}

    def test_full_cycle_pull_send_report_and_erase_password(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        tok, h = self.pair()
        from rest_framework.test import APIClient
        phone = APIClient()
        self.assertEqual(phone.get("/api/sms/pull/").status_code, 401)
        self.assertEqual(phone.get("/api/sms/pull/", HTTP_X_DEVICE_TOKEN="wrong").status_code, 401)
        r = phone.get("/api/sms/pull/?limit=1", **h).json()
        self.assertEqual(len(r["jobs"]), 1)
        job = r["jobs"][0]
        self.assertRegex(job["to"], r"^\+255[67]\d{8}$")
        self.assertRegex(job["body"], r"(password|nenosiri) \w{8}")
        self.assertEqual(r["config"]["seconds_between"], 8)
        self.assertEqual(SmsJob.objects.get(pk=job["id"]).status, "sending")
        self.assertEqual(phone.get("/api/sms/pull/?limit=5", **h).json()["jobs"][0]["id"] != job["id"], True)  # leased ones are not handed out twice
        ok = phone.post("/api/sms/report/", {"id": job["id"], "status": "sent"}, format="json", **h).json()
        self.assertTrue(ok["ok"])
        j = SmsJob.objects.get(pk=job["id"])
        self.assertEqual((j.status, j.body_enc), ("sent", ""))  # passwords erased once sent
        self.assertTrue(phone.post("/api/sms/report/", {"id": job["id"], "status": "delivered"}, format="json", **h).json()["ok"])
        self.assertEqual(SmsJob.objects.get(pk=job["id"]).status, "delivered")
        self.assertTrue(self.a.get("/api/guardians/summary/").json()["phone_online"])

    def test_failure_retry_and_lease_expiry(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        tok, h = self.pair()
        from rest_framework.test import APIClient
        phone = APIClient()
        jobs = phone.get("/api/sms/pull/?limit=2", **h).json()["jobs"]
        self.assertEqual(len(jobs), 2)
        phone.post("/api/sms/report/", {"id": jobs[0]["id"], "status": "failed", "error": "No signal"}, format="json", **h)
        self.assertEqual(SmsJob.objects.get(pk=jobs[0]["id"]).status, "failed")
        self.assertEqual(self.a.post(f"/api/guardians/jobs/{jobs[0]['id']}/retry/").json()["requeued"], 1)
        self.assertEqual(SmsJob.objects.get(pk=jobs[0]["id"]).status, "queued")
        # phone vanishes: the other lease expires and the message is offered again
        SmsJob.objects.filter(pk=jobs[1]["id"]).update(leased_until=timezone.now() - timedelta(minutes=1))
        again = {j["id"] for j in phone.get("/api/sms/pull/?limit=5", **h).json()["jobs"]}
        self.assertEqual(again, {jobs[0]["id"], jobs[1]["id"]})
        # after three tries it stops and shows as failed instead of repeating forever
        SmsJob.objects.filter(pk=jobs[1]["id"]).update(leased_until=timezone.now() - timedelta(minutes=1), attempts=3)
        phone.get("/api/sms/pull/", **h)
        self.assertEqual(SmsJob.objects.get(pk=jobs[1]["id"]).status, "failed")

    def test_revoked_phone_stops_working_and_cancel_clears_the_queue(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        tok, h = self.pair()
        from rest_framework.test import APIClient
        phone = APIClient()
        did = self.a.get("/api/guardians/devices/").json()[0]["id"]
        self.assertEqual(self.a.delete(f"/api/guardians/devices/{did}/").status_code, 204)
        self.assertEqual(phone.get("/api/sms/pull/", **h).status_code, 401)
        self.assertEqual(self.a.post("/api/guardians/jobs/cancel-queued/").json()["cancelled"], 2)
        j = SmsJob.objects.first()
        self.assertEqual((j.status, j.body_enc), ("cancelled", ""))
        self.assertEqual(self.a.post("/api/guardians/jobs/retry/").json()["requeued"], 0)  # only failed ones
        self.assertEqual(self.a.post(f"/api/guardians/jobs/{j.pk}/retry/").json()["requeued"], 1)  # cancelled can be remade with new passwords

    def test_another_phone_cannot_report_someone_elses_job(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        t1, h1 = self.pair()
        t2, h2 = self.pair()
        from rest_framework.test import APIClient
        phone = APIClient()
        job = phone.get("/api/sms/pull/?limit=1", **h1).json()["jobs"][0]
        self.assertFalse(phone.post("/api/sms/report/", {"id": job["id"], "status": "sent"}, format="json", **h2).json()["ok"])

    def test_ping_checks_the_code_without_taking_messages(self):
        self.load()
        self.a.post("/api/guardians/send/", {"scope": "all", "dry_run": False}, format="json")
        tok, h = self.pair()
        from rest_framework.test import APIClient
        phone = APIClient()
        self.assertEqual(phone.get("/api/sms/ping/").status_code, 401)
        r = phone.get("/api/sms/ping/", **h).json()
        self.assertEqual((r["ok"], r["name"], r["waiting"]), (True, "School phone", 2))
        self.assertEqual(SmsJob.objects.filter(status="queued").count(), 2)  # nothing was leased

    def test_config_is_validated(self):
        self.assertEqual(self.a.patch("/api/guardians/config/", {"public_url": "https://amani.example/", "seconds_between": 10}, format="json").json()["public_url"], "amani.example")
        self.assertEqual(self.a.patch("/api/guardians/config/", {"seconds_between": 1}, format="json").status_code, 400)
