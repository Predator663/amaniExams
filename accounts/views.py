import csv
import logging
from datetime import timedelta

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import SchoolClass
from core import reports
from core.models import SchoolSettings, audit
from notifications.services import notify_password_changed
from .hashers import InitialPasswordHasher
from .models import THEMES, BulkUploadBatch, User
from .permissions import IsAdminRole, IsSuperAdmin
from . import temp_password
from .services import (TEMPLATE_COLUMNS, create_students, generate_password, parse_upload, validate_rows,
                       validate_staff_password)

MAX_FAILED = 5
LOCK_MINUTES = 15
FRIENDLY_FAIL = "Wrong username or password. Please check and try again."


def user_payload(u):
    return {
        "id": u.pk, "username": u.username, "first_name": u.first_name, "last_name": u.last_name,
        "role": u.role, "class": str(u.school_class) if u.school_class else None,
        "must_change_password": u.must_change_password, "language": u.language, "theme": u.theme,
        "accessibility": {
            "text_size": u.text_size, "line_spacing": u.line_spacing, "dyslexia_font": u.dyslexia_font,
            "reduce_motion": u.reduce_motion, "read_aloud": u.read_aloud,
        },
    }


class _FakeLock:
    """Same lock-out behaviour for user names that do not exist, kept in the cache (SECURITY: otherwise only real names ever
    produce the "too many attempts" message and an attacker can list which names exist)."""

    def __init__(self, username):
        self.key = "login-fake:" + username.strip().lower()[:80]
        self.state = cache.get(self.key) or {"n": 0, "until": 0}

    def locked(self, now):
        return self.state["until"] > now.timestamp()

    def minutes_left(self, now):
        return int((self.state["until"] - now.timestamp()) // 60) + 1

    def fail(self, now):
        self.state["n"] += 1
        if self.state["n"] >= MAX_FAILED:
            self.state = {"n": 0, "until": now.timestamp() + LOCK_MINUTES * 60}
        cache.set(self.key, self.state, LOCK_MINUTES * 60 + 60)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = User.objects.filter(username__iexact=username).first() if username else None
        now = timezone.now()
        if user and user.locked_until and user.locked_until > now:
            mins = int((user.locked_until - now).total_seconds() // 60) + 1
            return Response({"detail": f"Too many wrong attempts. Please try again in {mins} minute(s)."}, status=429)
        fake = None if user or not username else _FakeLock(username)
        if fake and fake.locked(now):  # a name that does not exist is "locked" too, so the message never shows which names are real
            return Response({"detail": f"Too many wrong attempts. Please try again in {fake.minutes_left(now)} minute(s)."}, status=429)
        authed = authenticate(request, username=user.username, password=password) if user else None
        if not authed:
            if fake:
                fake.fail(now)
            if user:
                user.failed_logins += 1
                if user.failed_logins >= MAX_FAILED:
                    user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                    user.failed_logins = 0
                    audit(user, "login.locked", user.pk)
                user.save(update_fields=["failed_logins", "locked_until"])
            return Response({"detail": FRIENDLY_FAIL}, status=400)
        if authed.is_archived:
            return Response({"detail": FRIENDLY_FAIL}, status=400)
        if temp_password.expired(authed, now):  # a starting password nobody used in time stops working; the office issues a new one
            return Response({"detail": "Your starting password has expired. Please ask the school office for a new one."}, status=400)
        authed.failed_logins, authed.locked_until = 0, None
        authed.save(update_fields=["failed_logins", "locked_until"])
        # AUTH-09: one active session. A new login replaces the old token, ending the first session.
        Token.objects.filter(user=authed).delete()
        token = Token.objects.create(user=authed)
        audit(authed, "login", authed.pk)
        try:  # a student logging in again while an exam attempt runs is recorded for the anti-cheat review; it must never block a login
            from proctoring import services as proctoring
            proctoring.note_login(authed, ip=proctoring.client_ip(request), ua=request.META.get("HTTP_USER_AGENT", "")[:300])
        except Exception:
            logging.getLogger(__name__).exception("could not record the login for the integrity review")
        return Response({"token": token.key, "user": user_payload(authed)})


@api_view(["POST"])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response({"ok": True})


class ChangePasswordView(APIView):
    allow_forced_password_change = True

    def post(self, request):
        u = request.user
        old, new = request.data.get("old_password", ""), request.data.get("new_password", "")
        if not u.check_password(old):
            return Response({"detail": "Your current password is not correct."}, status=400)
        if new == old:
            return Response({"detail": "Please choose a different password."}, status=400)
        try:
            validate_password(new, u)
        except DjangoValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=400)
        u.set_password(new)
        u.must_change_password = False
        u.save()
        audit(u, "password.change", u.pk)
        notify_password_changed(u)  # NOT-01
        return Response({"ok": True})


class MeView(APIView):
    allow_forced_password_change = True

    def get(self, request):
        return Response(user_payload(request.user))

    def patch(self, request):
        """Language, theme and accessibility choices are remembered per user (ACC-01, ACC-02, ACC-06)."""
        u, d = request.user, request.data
        for f, allowed in (("language", {"en", "sw"}), ("theme", THEMES)):
            if f in d and d[f] in allowed:
                setattr(u, f, d[f])
        if "text_size" in d:
            try:
                u.text_size = max(100, min(200, int(d["text_size"])))
            except (TypeError, ValueError):
                raise ValidationError({"text_size": "Choose a size from 100 to 200 percent."})
        if "line_spacing" in d:
            try:
                u.line_spacing = max(1.0, min(2.5, float(d["line_spacing"])))
            except (TypeError, ValueError):
                raise ValidationError({"line_spacing": "Choose a line spacing from 1.0 to 2.5."})
        for f in ("dyslexia_font", "reduce_motion", "read_aloud"):
            if f in d:
                setattr(u, f, d[f] if isinstance(d[f], bool) else str(d[f]).lower() in ("1", "true", "yes", "on"))
        u.save(update_fields=["language", "theme", "text_size", "line_spacing", "dyslexia_font",
                              "reduce_motion", "read_aloud"])
        return Response(user_payload(u))


class StudentSerializer(serializers.ModelSerializer):
    school_class_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "index_number", "school_class",
                  "school_class_name", "is_active", "is_archived", "graduated"]
        read_only_fields = ["username", "is_archived", "graduated"]

    def get_school_class_name(self, o):
        return str(o.school_class) if o.school_class else None


class StudentViewSet(viewsets.ModelViewSet):
    """Admin student management (ADM-01). 'Delete' archives; only a super admin purges."""

    permission_classes = [IsAdminRole]
    serializer_class = StudentSerializer

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.STUDENT).select_related("school_class").order_by("school_class", "last_name")
        p = self.request.query_params
        if p.get("archived") == "1":
            qs = qs.filter(is_archived=True)
        elif self.action == "list":
            qs = qs.filter(is_archived=False)
        if p.get("graduated") == "1":
            qs = qs.filter(graduated=True)
        if p.get("active") in ("0", "1"):
            qs = qs.filter(is_active=p["active"] == "1")
        if p.get("class"):
            qs = qs.filter(school_class_id=p["class"])
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q) | Q(index_number__icontains=q))
        return qs

    def perform_create(self, serializer):
        from .services import make_username
        from django.contrib.auth.hashers import make_password

        d = serializer.validated_data
        taken = set(User.objects.values_list("username", flat=True))
        obj = serializer.save(username=make_username(d["first_name"], taken), role=User.Role.STUDENT, must_change_password=True)
        temp_password.issue(obj)  # random starting password, printed on the credentials sheet (never the index number)
        audit(self.request.user, "student.create", obj.pk)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request.user, "student.edit", obj.pk)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if request.query_params.get("permanent") == "1":
            if not IsSuperAdmin().has_permission(request, self):
                return Response({"detail": "Only a Super Admin can delete permanently."}, status=403)
            audit(request.user, "student.purge", obj.pk)
            obj.delete()
            return Response(status=204)
        obj.is_archived, obj.is_active = True, False
        obj.save(update_fields=["is_archived", "is_active"])
        Token.objects.filter(user=obj).delete()
        audit(request.user, "student.archive", obj.pk)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        obj = User.objects.get(pk=pk, role=User.Role.STUDENT)
        obj.is_archived, obj.is_active = False, True
        obj.save(update_fields=["is_archived", "is_active"])
        audit(request.user, "student.restore", obj.pk)
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        obj = self.get_object()
        code = temp_password.issue(obj)
        Token.objects.filter(user=obj).delete()
        audit(request.user, "password.reset", obj.pk)
        notify_password_changed(obj, by_admin=True)
        # shown once here and on the credentials sheet; she must choose her own password at the first login
        return Response({"ok": True, "temporary_password": code,
                         "detail": "A new starting password was issued (it is on the credentials sheet); she must choose a new one."})

    def _set_state(self, request, pk, label, **fields):
        obj = self.get_object()
        for k, v in fields.items():
            setattr(obj, k, v)
        obj.save(update_fields=list(fields))
        if fields.get("is_active") is False:
            Token.objects.filter(user=obj).delete()  # she is logged out straight away
        audit(request.user, f"student.{label}", obj.pk)
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self._set_state(request, pk, "deactivate", is_active=False)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._set_state(request, pk, "activate", is_active=True, graduated=False)

    @action(detail=True, methods=["post"])
    def graduate(self, request, pk=None):
        return self._set_state(request, pk, "graduate", is_active=False, graduated=True)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """ADM-01: move to another class."""
        klass = SchoolClass.objects.filter(pk=request.data.get("school_class")).first()
        if not klass:
            raise ValidationError({"school_class": "Choose a class."})
        return self._set_state(request, pk, "move", school_class=klass)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def upload_template(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="students_template.csv"'
    csv.writer(resp).writerow([c.title() for c in TEMPLATE_COLUMNS])
    return resp


@api_view(["POST"])
@permission_classes([IsAdminRole])
def bulk_validate(request):
    """Step 1: validate only. Nothing is created yet (AUTH-03)."""
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "Please choose a file."}, status=400)
    try:
        rows = parse_upload(f)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    except Exception:
        return Response({"detail": "We could not read that file. Please use the template."}, status=400)
    try:
        clean, report = validate_rows(rows)
    except ValueError as e:  # e.g. parents named in the file but GUARDIAN_KEY is not set
        return Response({"detail": str(e)}, status=400)
    batch = BulkUploadBatch.objects.create(created_by=request.user, rows=clean, report=report)
    return Response({"batch_id": batch.pk, **report})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def bulk_confirm(request, batch_id):
    """Step 2: admin confirms, accounts are created (AUTH-04, AUTH-05)."""
    try:
        batch = BulkUploadBatch.objects.get(pk=batch_id, created_by=request.user)
    except BulkUploadBatch.DoesNotExist:
        return Response({"detail": "Upload not found."}, status=404)
    if batch.status != BulkUploadBatch.PENDING:
        return Response({"detail": "This upload was already confirmed."}, status=409)
    if batch.report.get("invalid_rows") and not request.data.get("skip_invalid"):
        return Response({"detail": "Some rows are invalid. Fix the file, or confirm with skip_invalid to create only the valid rows."}, status=400)
    ids = create_students(batch, request.user)
    out = {"created": len(ids), "credentials_url": f"/api/students/bulk-upload/{batch.pk}/credentials/"}
    if batch.report.get("parents_result"):
        out["parents"] = batch.report["parents_result"]
    return Response(out)


def _credentials_response(users, stub, kind):
    """AUTH-06: printable sheet (PDF, one page group per class) or CSV. Only students who still
    have their starting password are listed, so the sheet never exposes a chosen password."""
    users = list(users)
    kind = "csv" if kind == "csv" else "pdf"
    if kind == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{stub}.csv"'
        w = csv.writer(resp)
        w.writerow(["Class", "Name", "Username", "Starting password"])
        for u in users:
            w.writerow([reports.csv_safe(str(u.school_class)), reports.csv_safe(f"{u.first_name} {u.last_name}"),
                        u.username, reports.csv_safe(temp_password.password_for(u) or "")])
        return resp
    groups = {}
    for u in users:
        groups.setdefault(str(u.school_class) if u.school_class else "No class", []).append(
            (f"{u.first_name} {u.last_name}", u.username, temp_password.password_for(u) or "-"))
    pdf = reports.credentials_pdf(SchoolSettings.load().school_name, list(groups.items()))
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{stub}.pdf"'
    return resp


def _ordered(qs):
    return qs.select_related("school_class").order_by("school_class__form_level", "school_class__name",
                                                      "school_class__stream", "last_name", "first_name")


@api_view(["GET"])
@permission_classes([IsAdminRole])
def bulk_credentials(request, batch_id):
    """Right after an upload: ?file=pdf (default) or ?file=csv."""
    try:
        batch = BulkUploadBatch.objects.get(pk=batch_id, created_by=request.user)
    except BulkUploadBatch.DoesNotExist:
        return Response({"detail": "Upload not found."}, status=404)
    users = _ordered(User.objects.filter(pk__in=batch.created_user_ids, must_change_password=True, temp_issued_at__isnull=False))
    audit(request.user, "credentials.download", batch.pk)
    return _credentials_response(users, f"credentials_{batch.pk}", request.query_params.get("file"))


@api_view(["GET"])
@permission_classes([IsAdminRole])
def class_credentials(request):
    """Sheet for one class at any time: ?class=<id>&file=pdf|csv (students who have not yet changed their password)."""
    users = User.objects.filter(role=User.Role.STUDENT, must_change_password=True, is_archived=False, is_active=True,
                                temp_issued_at__isnull=False)  # students whose password was set by the parents' SMS are not on the sheet
    if request.query_params.get("class"):
        users = users.filter(school_class_id=request.query_params["class"])
    audit(request.user, "credentials.download", request.query_params.get("class", "all"))
    return _credentials_response(_ordered(users), "credentials", request.query_params.get("file"))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def students_bulk_action(request):
    """ADM-02: change_class | reset_passwords | deactivate | graduate for many students at once."""
    ids = request.data.get("ids")
    action_name = request.data.get("action")
    if not isinstance(ids, list) or not ids:
        raise ValidationError({"ids": "Choose at least one student."})
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise ValidationError({"ids": "Student ids must be numbers."})
    qs = User.objects.filter(role=User.Role.STUDENT, pk__in=ids, is_archived=False)
    n = qs.count()
    if action_name == "change_class":
        klass = SchoolClass.objects.filter(pk=request.data.get("school_class")).first()
        if not klass:
            raise ValidationError({"school_class": "Choose a class."})
        qs.update(school_class=klass)
        audit(request.user, "students.bulk.change_class", klass.pk, count=n)
    elif action_name == "reset_passwords":
        users = list(qs)
        for u in users:  # the light starting-password hasher keeps 500 resets fast (see settings)
            temp_password.issue(u, save=False)
        User.objects.bulk_update(users, ["password", "must_change_password", "failed_logins", "locked_until", "temp_serial", "temp_issued_at"])
        Token.objects.filter(user__in=users).delete()
        audit(request.user, "students.bulk.reset_passwords", "", count=n)
    elif action_name in ("deactivate", "graduate"):
        fields = {"is_active": False}
        if action_name == "graduate":
            fields["graduated"] = True
        Token.objects.filter(user__in=list(qs)).delete()
        qs.update(**fields)
        audit(request.user, f"students.bulk.{action_name}", "", count=n)
    else:
        raise ValidationError({"action": "Choose change_class, reset_passwords, deactivate or graduate."})
    return Response({"ok": True, "affected": n})


# ------------------------------------------------------------ teacher and admin accounts (ADM-03, AUTH-07)

class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    assignments = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_active", "password", "assignments"]

    def get_assignments(self, o):
        return [{"id": a.pk, "subject": a.subject_id, "subject_name": a.subject.name, "school_class": a.school_class_id}
                for a in o.assignments.all()]


class StaffAccountViewSet(viewsets.ModelViewSet):
    """Base for teacher and admin accounts. Created by an admin with a strong starting password;
    the person must change it at first login."""

    permission_classes = [IsAdminRole]
    serializer_class = StaffSerializer
    role = User.Role.TEACHER
    label = "teacher"

    def get_queryset(self):
        qs = User.objects.filter(role=self.role).prefetch_related("assignments__subject").order_by("last_name", "username")
        if self.request.query_params.get("q"):
            q = self.request.query_params["q"]
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        pw = data.pop("password", None)
        if not pw:
            raise ValidationError({"password": "Please set a starting password."})
        user = User(role=self.role, must_change_password=True, **data)
        try:
            validate_staff_password(pw, user)
        except DjangoValidationError as e:
            raise ValidationError({"password": e.messages})
        user.set_password(pw)
        user.save()
        audit(request.user, f"{self.label}.create", user.pk)
        return Response(self.get_serializer(user).data, status=201)

    def perform_update(self, serializer):
        serializer.validated_data.pop("password", None)  # passwords change only through reset-password
        obj = serializer.save()
        if not obj.is_active:
            Token.objects.filter(user=obj).delete()
        audit(self.request.user, f"{self.label}.edit", obj.pk)

    def destroy(self, request, *args, **kwargs):
        """Teachers are deactivated (their questions and exams stay)."""
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        Token.objects.filter(user=obj).delete()
        audit(request.user, f"{self.label}.deactivate", obj.pk)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save(update_fields=["is_active"])
        audit(request.user, f"{self.label}.activate", obj.pk)
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """AUTH-07. Send new_password, or leave it out to get a random temporary one (shown once)."""
        obj = self.get_object()
        given = request.data.get("new_password")
        pw = given or generate_password()
        try:
            validate_staff_password(pw, obj)
        except DjangoValidationError as e:
            raise ValidationError({"new_password": e.messages})
        obj.set_password(pw)
        obj.must_change_password, obj.failed_logins, obj.locked_until = True, 0, None
        obj.save()
        Token.objects.filter(user=obj).delete()
        audit(request.user, "password.reset", obj.pk)
        notify_password_changed(obj, by_admin=True)
        return Response({"ok": True, **({} if given else {"temporary_password": pw})})


class TeacherViewSet(StaffAccountViewSet):
    pass


class AdminAccountViewSet(StaffAccountViewSet):
    """Only a Super Admin creates or removes Admin accounts (section 2 of the SRS)."""

    permission_classes = [IsSuperAdmin]
    role = User.Role.ADMIN
    label = "admin"

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.pk == request.user.pk:
            raise ValidationError({"detail": "You cannot remove your own account."})
        audit(request.user, "admin.remove", obj.pk, username=obj.username)
        obj.delete()
        return Response(status=204)
