"""Creating notifications. Heavy imports of the exams app are done inside functions so that
`accounts` and `exams` can import this module without circular imports."""
import logging
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from core.i18n import LANGS, fmt_when, lang_of, t
from .models import Notification
from .push import send_push

log = logging.getLogger(__name__)


def notify(users, kind, title, body="", key="", data=None, push=True):
    """Create one notification per user. With a `key`, a user who already has it is skipped.
    Returns the number of users notified."""
    ids = {u.pk if hasattr(u, "pk") else int(u) for u in users}
    if key and ids:
        ids -= set(Notification.objects.filter(key=key, user_id__in=ids).values_list("user_id", flat=True))
    if not ids:
        return 0
    Notification.objects.bulk_create(
        [Notification(user_id=i, kind=kind, title=title, body=body, key=key, data=data or {}) for i in ids],
        ignore_conflicts=True,
    )
    if push:
        send_push(ids, title, body)
    return len(ids)


def notify_i18n(users, kind, title_key, body_key, params, key="", data=None, push=True):
    """Like notify(), but every student gets the text in her own language (English or Swahili, ACC-08).
    `params` fill the {placeholders}; a `when_dt` datetime is formatted per language as {when}.
    Returns the number of users notified."""
    ids = [u.pk if hasattr(u, "pk") else int(u) for u in users]
    langs = dict(User.objects.filter(pk__in=ids).values_list("pk", "language"))
    groups = defaultdict(list)
    for uid in ids:
        lang = langs.get(uid, "en")
        groups[lang if lang in LANGS else "en"].append(uid)
    sent = 0
    for lang, group in groups.items():
        p = {k: v for k, v in params.items() if k != "when_dt"}
        if params.get("when_dt") is not None:
            p["when"] = fmt_when(timezone.localtime(params["when_dt"]), lang)
        sent += notify(group, kind, t(title_key, lang, **p), t(body_key, lang, **p), key=key, data=data, push=push)
    return sent


def notify_password_changed(user, by_admin=False):
    lang = lang_of(user)
    notify([user], "password_changed", t("password.title", lang), t("password.reset" if by_admin else "password.changed", lang))


def due_messages(exam, now):
    """Which exam notifications are due at `now`, as (key, kind, title_key, body_key, params, data). At most
    one is returned, so a student who logs in 30 minutes before the exam gets the 1-hour reminder, not two."""
    if not (exam.start_at and exam.end_at):
        return []
    s, e = exam.start_at, exam.end_at
    p = {"subject": exam.subject.name, "title": exam.title, "when_dt": s}
    data = {"exam_id": exam.pk}
    if s - timedelta(hours=24) <= now < s - timedelta(hours=1):
        return [(f"exam1d:{exam.pk}", "exam_reminder", "exam.1d.title", "exam.1d.body", p, data)]
    if s - timedelta(hours=1) <= now < s:
        return [(f"exam1h:{exam.pk}", "exam_reminder", "exam.1h.title", "exam.1h.body", p, data)]
    if s <= now <= e:
        return [(f"examstart:{exam.pk}", "exam_start", "exam.start.title", "exam.start.body", p, data)]
    return []


def due_specs(exam, now):
    """The same as due_messages, with the English text filled in: (key, kind, title, body, data)."""
    out = []
    for key, kind, title_key, body_key, params, data in due_messages(exam, now):
        p = {k: v for k, v in params.items() if k != "when_dt"}
        p["when"] = fmt_when(timezone.localtime(params["when_dt"]), "en")
        out.append((key, kind, t(title_key, "en", **p), t(body_key, "en", **p), data))
    return out


def run_exam_notifications(now=None):
    """Scheduler entry point: reminders and start notices for every eligible student."""
    from exams.models import Exam
    from exams.services import eligible_students

    now, sent = now or timezone.now(), 0
    for exam in Exam.objects.filter(status__in=[Exam.SCHEDULED, Exam.LIVE]).select_related("subject"):
        msgs = due_messages(exam, now)
        if msgs:
            students = list(eligible_students(exam).values_list("pk", flat=True))
            for key, kind, title_key, body_key, params, data in msgs:
                sent += notify_i18n(students, kind, title_key, body_key, params, key=key, data=data)
    return sent


def ensure_for_student(student, now=None):
    """Same rules, for one student, called when she opens her notifications. A missed cron run
    therefore never means a missed reminder."""
    from exams.models import Exam
    from exams.services import exams_for_student

    now = now or timezone.now()
    qs = exams_for_student(student).filter(status__in=[Exam.SCHEDULED, Exam.LIVE]).select_related("subject")
    for exam in qs:
        for key, kind, title_key, body_key, params, data in due_messages(exam, now):
            notify_i18n([student], kind, title_key, body_key, params, key=key, data=data, push=False)


def results_ready(exam):
    """RES-02: tell every student who sat the exam that her results are ready."""
    ids = list(exam.attempts.values_list("student_id", flat=True).distinct())
    return notify_i18n(ids, "results_ready", "results.title", "results.body", {"title": exam.title},
                       key=f"results:{exam.pk}", data={"exam_id": exam.pk})


def audience_students(audience, target):
    qs = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False)
    if audience == "class":
        qs = qs.filter(school_class_id__in=target.get("class_ids", []))
    elif audience == "stream":
        qs = qs.filter(school_class__stream__iexact=str(target.get("stream", "")).strip())
        if target.get("form_level"):
            qs = qs.filter(school_class__form_level=target["form_level"])
    return qs
