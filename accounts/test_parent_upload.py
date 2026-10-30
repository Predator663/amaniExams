"""Students uploaded from the template are linked to their parents.  Run:  python manage.py test accounts.test_parent_upload"""
import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from openpyxl import Workbook

from accounts.models import BulkUploadBatch, User
from analytics.tests import AnalyticsBase
from guardians import crypto, services as gsvc
from guardians.models import Guardian, GuardianLink

HEAD = "first name,last name,index number,class or form,stream,parent name,parent phone,parent relationship,parent 2 name,parent 2 phone,parent 2 relationship\n"


def csv_file(body, head=HEAD, name="students.csv"):
    return SimpleUploadedFile(name, (head + body).encode(), content_type="text/csv")


class ParentUploadTests(AnalyticsBase):
    def setUp(self):
        super().setUp()
        self.a = self.client_for(self.admin)

    def validate(self, body, **kw):
        return self.a.post("/api/students/bulk-upload/validate/", {"file": csv_file(body, **kw)}, format="multipart")

    def confirm(self, batch_id):
        return self.a.post(f"/api/students/bulk-upload/{batch_id}/confirm/", {"skip_invalid": True}, format="json")

    def upload(self, body, **kw):
        r = self.validate(body, **kw)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json(), self.confirm(r.json()["batch_id"])

    def kids(self, phone):
        g = Guardian.objects.get(phone_idx=crypto.blind_index(phone))
        return g, sorted(User.objects.get(pk=l.student_id).first_name for l in g.links.all())

    # ---- the main case: siblings share one parent
    def test_one_parent_with_several_students_becomes_one_guardian(self):
        rep, r = self.upload(
            "Neema,Juma,N1,Form 2,A,Baba Neema,0755123456,father,,,\n"
            "Rehema,Juma,N2,Form 4,B,Baba Neema,+255 755 123 456,father,,,\n"
            "Zuri,Juma,N3,Form 1,A,baba neema,255755123456,,,,\n")
        self.assertEqual(rep["valid_rows"], 3)
        self.assertEqual(rep["parents"], {"rows_with_parents": 3, "parents_new": 1, "parents_existing": 0, "links": 3,
                                          "parents_with_several_students": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["created"], 3)
        self.assertEqual(r.json()["parents"], {"parents_created": 1, "parents_updated": 0, "links_created": 3})
        self.assertEqual(Guardian.objects.count(), 1)
        g, kids = self.kids("+255755123456")
        self.assertEqual((g.name, g.relationship, kids), ("Baba Neema", "father", ["Neema", "Rehema", "Zuri"]))

    def test_a_parent_already_registered_is_reused_for_a_new_sibling(self):
        self.upload("Neema,Juma,N1,Form 2,A,Baba Neema,0755123456,father,,,\n")
        rep, r = self.upload("Rehema,Juma,N2,Form 2,A,,0755123456,,,,\n")  # name left empty: the registered parent supplies it
        self.assertEqual(rep["valid_rows"], 1)
        self.assertEqual((rep["parents"]["parents_new"], rep["parents"]["parents_existing"]), (0, 1))
        self.assertEqual(r.json()["parents"], {"parents_created": 0, "parents_updated": 0, "links_created": 1})
        self.assertEqual(Guardian.objects.count(), 1)
        self.assertEqual(self.kids("+255755123456")[1], ["Neema", "Rehema"])

    def test_two_parents_for_one_student_and_each_parent_keeps_other_children(self):
        self.upload(
            "Amina,Said,A1,Form 1,A,Mama Amina,0712345678,mother,Baba Amina,0713000111,father\n"
            "Bakari,Said,A2,Form 3,A,Mama Amina,0712345678,mother,,,\n")
        self.assertEqual(Guardian.objects.count(), 2)
        self.assertEqual(self.kids("+255712345678")[1], ["Amina", "Bakari"])
        self.assertEqual(self.kids("+255713000111")[1], ["Amina"])

    def test_old_template_without_parent_columns_works_exactly_as_before(self):
        head = "first name,last name,index number,class or form,stream\n"
        rep, r = self.upload("Neema,Juma,N1,Form 2,A\n", head=head)
        self.assertEqual((rep["valid_rows"], rep["invalid_rows"], rep["warnings"]), (1, 0, []))
        self.assertEqual(rep["parents"]["links"], 0)
        self.assertEqual(r.json()["created"], 1)
        self.assertNotIn("parents", r.json())
        self.assertEqual(Guardian.objects.count(), 0)

    def test_rows_with_no_parent_details_are_fine_in_a_file_that_has_the_columns(self):
        rep, r = self.upload("Neema,Juma,N1,Form 2,A,,,,,,\nRehema,Juma,N2,Form 2,A,Baba,0755123456,,,,\n")
        self.assertEqual((rep["valid_rows"], rep["parents"]["rows_with_parents"]), (2, 1))
        self.assertEqual(GuardianLink.objects.count(), 1)

    # ---- bad data is reported, never half-saved
    def test_bad_parent_rows_are_errors_and_those_students_are_not_created(self):
        rep, r = self.upload(
            "Ok,Kid,K1,Form 1,A,Mama Ok,0712345678,,,,\n"
            "BadPhone,Kid,K2,Form 1,A,Mama Bad,12345,,,,\n"
            "NoPhone,Kid,K3,Form 1,A,Mama NoPhone,,,,,\n"
            "NoName,Kid,K4,Form 1,A,,0788111222,,,,\n"
            "SecondBad,Kid,K5,Form 1,A,Mama,0712999000,,Baba,abc,\n")
        self.assertEqual((rep["valid_rows"], rep["invalid_rows"]), (1, 4))
        self.assertEqual([e["row"] for e in rep["errors"]], [3, 4, 5, 6])
        self.assertIn("not a valid Tanzanian mobile number", rep["errors"][0]["problems"][0])
        self.assertIn("phone number is missing", rep["errors"][1]["problems"][0])
        self.assertIn("name is missing", rep["errors"][2]["problems"][0])
        self.assertIn("Parent 2", rep["errors"][3]["problems"][0])
        self.assertEqual(r.json()["created"], 1)
        self.assertEqual(list(User.objects.filter(index_number__startswith="K").values_list("index_number", flat=True)), ["K1"])
        self.assertEqual(Guardian.objects.count(), 1)

    def test_name_can_come_from_a_sibling_row(self):
        rep, _ = self.upload("A,X,X1,Form 1,A,,0712345678,,,,\nB,X,X2,Form 1,A,Mama X,0712 345 678,,,,\n")
        self.assertEqual((rep["valid_rows"], rep["invalid_rows"]), (2, 0))
        self.assertEqual(self.kids("+255712345678")[0].name, "Mama X")

    def test_same_number_with_different_names_is_one_parent_and_a_warning(self):
        rep, _ = self.upload("A,X,X1,Form 1,A,Mama X,0712345678,,,,\nB,X,X2,Form 1,A,Mrs Totally Other,0712345678,,,,\n")
        self.assertEqual(rep["valid_rows"], 2)
        self.assertEqual([w["row"] for w in rep["warnings"]], [3])
        self.assertIn("Mama X", rep["warnings"][0]["problems"][0])
        self.assertEqual(Guardian.objects.count(), 1)
        self.assertNotIn("0712345678", str(rep))  # reports only ever show a masked number

    def test_same_number_for_both_parents_on_a_row_counts_once(self):
        rep, _ = self.upload("A,X,X1,Form 1,A,Mama X,0712345678,,Baba X,0712345678,\n")
        self.assertEqual(rep["parents"]["links"], 1)
        self.assertEqual(len(rep["warnings"]), 1)
        self.assertEqual(GuardianLink.objects.count(), 1)

    def test_excel_numbers_work(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["first name", "last name", "index number", "class or form", "stream", "parent name", "parent phone"])
        ws.append(["A", "X", "X1", "Form 1", "A", "Mama X", 712345678])      # Excel dropped the leading 0
        ws.append(["B", "X", "X2", "Form 1", "A", "Mama X", 712345678.0])
        ws.append(["C", "X", "X3", "Form 1", "A", "Mama X", "712345678.0"])
        buf = io.BytesIO()
        wb.save(buf)
        r = self.a.post("/api/students/bulk-upload/validate/", {"file": SimpleUploadedFile("s.xlsx", buf.getvalue())}, format="multipart")
        self.assertEqual((r.status_code, r.json()["valid_rows"]), (200, 3), r.content)
        self.assertEqual(self.confirm(r.json()["batch_id"]).status_code, 200)
        self.assertEqual(self.kids("+255712345678")[1], ["A", "B", "C"])

    # ---- privacy and safety
    def test_nothing_is_saved_by_the_check_and_waiting_rows_hold_no_plain_phone_number(self):
        r = self.validate("A,X,X1,Form 1,A,Mama X,0712345678,mother,,,\n")
        self.assertEqual((Guardian.objects.count(), User.objects.filter(index_number="X1").count()), (0, 0))
        batch = BulkUploadBatch.objects.get(pk=r.json()["batch_id"])
        self.assertNotIn("712345678", str(batch.rows))
        self.assertNotIn("Mama X", str(batch.rows) + str(batch.report))
        self.confirm(batch.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.rows, [])

    def test_a_batch_saved_before_this_update_still_confirms(self):
        batch = BulkUploadBatch.objects.create(created_by=self.admin, report={"invalid_rows": 0}, rows=[
            {"first_name": "Old", "last_name": "Batch", "index_number": "O1", "class": "Form 1", "stream": "A"}])
        self.assertEqual(self.confirm(batch.pk).status_code, 200)
        self.assertTrue(User.objects.filter(index_number="O1").exists())

    def test_if_linking_fails_no_student_is_created(self):
        r = self.validate("A,X,X1,Form 1,A,Mama X,0712345678,,,,\nB,X,X2,Form 1,A,Mama X,0712345678,,,,\n")
        self.a.raise_request_exception = False  # let the test see the 500 instead of the exception
        with mock.patch("guardians.services.commit_rows", side_effect=RuntimeError("boom")):
            c = self.a.post(f"/api/students/bulk-upload/{r.json()['batch_id']}/confirm/", {"skip_invalid": True}, format="json")
        self.assertEqual(c.status_code, 500)
        self.assertEqual(User.objects.filter(index_number__in=["X1", "X2"]).count(), 0)
        self.assertEqual(BulkUploadBatch.objects.get(pk=r.json()["batch_id"]).status, BulkUploadBatch.PENDING)

    @override_settings(GUARDIAN_KEY="", DEBUG=False, TESTING=False)
    def test_missing_guardian_key_gives_a_clear_message_only_when_parents_are_in_the_file(self):
        r = self.validate("A,X,X1,Form 1,A,Mama X,0712345678,,,,\n")
        self.assertEqual(r.status_code, 400)
        self.assertIn("GUARDIAN_KEY", r.json()["detail"])
        plain = self.validate("A,X,X1,Form 1,A,,,,,,\n")
        self.assertEqual((plain.status_code, plain.json()["valid_rows"]), (200, 1))

    def test_only_admins_and_the_template_lists_the_new_columns(self):
        self.assertEqual(self.client_for(self.teacher).post("/api/students/bulk-upload/validate/", {"file": csv_file("")}, format="multipart").status_code, 403)
        t = self.a.get("/api/students/bulk-upload/template/")
        first = t.content.decode().splitlines()[0]
        self.assertTrue(first.startswith("First Name,Last Name,Index Number,Class Or Form,Stream,Parent Name,Parent Phone"))

    # ---- it all works together with the login-details SMS
    def test_brothers_and_sisters_get_one_sms_to_the_one_parent(self):
        self.upload("Neema,Juma,N1,Form 2,A,Baba Neema,0755123456,,,,\nRehema,Juma,N2,Form 4,B,Baba Neema,0755123456,,,,\n")
        items, skipped = gsvc.plan_send("all")
        self.assertEqual(len(items), 1)
        self.assertEqual(sorted(s.first_name for s in items[0][1]), ["Neema", "Rehema"])
