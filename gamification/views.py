"""Gamification API (SRS section 5). All student endpoints answer only about the logged-in student
(BR-07). Nothing here shows exam marks of another student, and nothing here changes a mark (BR-10)."""
import logging

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from academics.models import Subject, TeacherAssignment
from accounts.permissions import IsAdminRole, IsAnyUser, IsStaffUser, IsStudent
from core.i18n import lang_of
from core.models import audit
from core.pagination import envelope, page_params, paginate, wants_page
from exams.views import _visible_result_or_404
from questions.models import Question
from . import catalog, rules, services
from .models import AVATARS, GamificationSettings

log = logging.getLogger(__name__)


def _err(e):
    return Response({"detail": e.message, "code": e.code}, status=e.status)


def _safe_reward(student):
    """Hand out any rewards that are due. A problem here must never stop the page loading."""
    try:
        services.reward_pending_for(student)
    except Exception:
        log.exception("reward_pending_for failed for user %s", student.pk)


# ---------------------------------------------------------------- student: home, badges, xp, profile

@api_view(["GET"])
@permission_classes([IsStudent])
def my_summary(request):
    """HOME-03: streak, XP, level and recent badges at a glance, plus the level-up and badge celebrations."""
    _safe_reward(request.user)
    return Response(services.student_summary(request.user))


@api_view(["POST"])
@permission_classes([IsStudent])
def acknowledge(request):
    """The student has seen her celebrations, so they are not shown again."""
    services.acknowledge(request.user)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsStudent])
def my_badges(request):
    """SRS 5.4: the badge cabinet with progress towards the next tier."""
    _safe_reward(request.user)
    return Response(services.badge_cabinet(request.user, services.config(), lang_of(request.user)))


@api_view(["GET"])
@permission_classes([IsStudent])
def my_xp(request):
    if wants_page(request):
        page, size = page_params(request, 15)
        data = services.xp_history(request.user, size, (page - 1) * size)
        if page > 1 and not data["results"]:  # the page is past the end: show the last one
            page = max(1, -(-data["count"] // size))
            data = services.xp_history(request.user, size, (page - 1) * size)
        rows = data.pop("results")
        return Response(envelope(data.pop("count"), page, size, rows, **data))
    try:
        limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
        offset = max(0, int(request.query_params.get("offset", 0)))
    except ValueError:
        limit, offset = 50, 0
    return Response(services.xp_history(request.user, limit, offset))


@api_view(["GET", "PATCH"])
@permission_classes([IsStudent])
def my_profile(request):
    """SRS 5.6: preset avatar, display name for classmates, and the choice to hide from the leaderboard."""
    profile = services.get_profile(request.user)
    if request.method == "PATCH":
        d = request.data
        if "avatar" in d:
            if d["avatar"] not in AVATARS:
                raise ValidationError({"avatar": "Choose one of the avatars in the list."})
            profile.avatar = d["avatar"]
        if "display_name" in d:
            name = " ".join(str(d["display_name"]).split())
            if len(name) > 30:
                raise ValidationError({"display_name": "Use up to 30 characters."})
            profile.display_name = name
        if "hide_from_leaderboard" in d:
            if not isinstance(d["hide_from_leaderboard"], bool):
                raise ValidationError({"hide_from_leaderboard": "Must be true or false."})
            profile.hide_from_leaderboard = d["hide_from_leaderboard"]
        profile.save()
    return Response(services.profile_payload(profile))


@api_view(["GET"])
@permission_classes([IsStudent])
def leaderboard(request):
    """SRS 5.6: class ranking by XP (never by marks). ?period=weekly (default) or all."""
    period = request.query_params.get("period", "weekly")
    if not wants_page(request):
        return Response(services.leaderboard(request.user, period))
    data = services.leaderboard(request.user, period, limit=1000)  # whole class, then one page of it
    if not data.get("enabled"):
        return Response(data)
    pg = paginate(request, data.pop("entries"), default=10)
    return Response({**data, "entries": pg.pop("results"), **pg})


@api_view(["GET"])
@permission_classes([IsAnyUser])
def badge_catalog(request):
    """Every badge, its targets and its text in the user's language, so the app can draw the cabinet."""
    lang, cfg = lang_of(request.user), services.config()
    return Response({
        "levels": [{"level": lv["level"], "name": lv["name_sw"] if lang == "sw" and lv.get("name_sw") else lv["name"], "xp": lv["xp"]}
                   for lv in services.level_table(cfg)],
        "badges": [{"code": b["code"], "name": catalog.badge_name(b["code"], lang), "description": catalog.badge_desc(b["code"], lang),
                    "unit": catalog.badge_unit(b["code"], lang), "per_subject": bool(b.get("per_subject")),
                    "tiers": [{"tier": k, "label": catalog.tier_label(i, lang), "target": th}
                              for i, (k, th) in enumerate(zip(rules.TIER_NAMES, cfg["tiers"][b["code"]]), start=1)]}
                   for b in catalog.BADGES],
    })


# ---------------------------------------------------------------- review mode progress (Mistake Master)

@api_view(["GET", "POST"])
@permission_classes([IsStudent])
def review_seen(request, attempt_id):
    """The app tells us which question numbers she has looked at in review mode. Only after publish (RES-05)."""
    attempt, err = _visible_result_or_404(request, attempt_id)
    if err:
        return err
    if request.method == "GET":
        return Response(services.review_progress(attempt, lang_of(request.user)))
    numbers = request.data.get("numbers")
    if not isinstance(numbers, list) or len(numbers) > 500:
        raise ValidationError({"numbers": "Send a list of question numbers you have viewed."})
    result = services.mark_reviewed(attempt, numbers)
    _safe_reward(request.user)
    return Response(result)


# ---------------------------------------------------------------- practice mode (SRS 5.5)

@api_view(["GET"])
@permission_classes([IsStudent])
def practice_subjects(request):
    return Response(services.practice_subjects(request.user))


@api_view(["POST"])
@permission_classes([IsStudent])
def practice_start(request):
    """Start (or resume) a practice quiz: {"subject_id": 3, "count": 10, "topic": "...", "difficulty": "easy"}."""
    d = request.data
    try:
        session = services.start_practice(
            request.user, d.get("subject_id"), d.get("count", services.PRACTICE_DEFAULT), d.get("topic") or None,
            d.get("difficulty") or None, restart=d.get("restart") is True)
    except services.GamificationError as e:
        return _err(e)
    return Response(services.practice_state(session), status=201)


def _own_session(request, session_id):
    from .models import PracticeSession

    return get_object_or_404(PracticeSession.objects.select_related("subject"), pk=session_id, user=request.user)


@api_view(["GET"])
@permission_classes([IsStudent])
def practice_current(request, session_id):
    return Response(services.practice_state(_own_session(request, session_id)))


@api_view(["POST"])
@permission_classes([IsStudent])
def practice_answer(request, session_id):
    """Instant, automatic marking: returns the feedback for this answer and the next question."""
    session = _own_session(request, session_id)
    try:
        out = services.answer_practice(session.pk, request.user, request.data.get("question_id"), request.data.get("response"))
    except services.GamificationError as e:
        return _err(e)
    return Response(out)


@api_view(["POST"])
@permission_classes([IsStaffUser])
def practice_toggle_subject(request, subject_id):
    """Teachers (for their own subjects) and admins switch practice on or off for a subject."""
    subject = get_object_or_404(Subject, pk=subject_id)
    if not (request.user.is_admin_role
            or TeacherAssignment.objects.filter(teacher=request.user, subject=subject).exists()):
        raise PermissionDenied("You can only change practice for your assigned subjects.")
    enabled = request.data.get("enabled")
    if not isinstance(enabled, bool):
        raise ValidationError({"enabled": "Send true or false."})
    subject.practice_enabled = enabled
    subject.save(update_fields=["practice_enabled"])
    audit(request.user, "practice.toggle", subject.pk, enabled=enabled)
    return Response({"subject": subject.name, "practice_enabled": enabled})


@api_view(["POST"])
@permission_classes([IsStaffUser])
def practice_mark_eligible(request):
    """Mark many questions 'practice eligible' (or not) in one go: {"question_ids": [1, 2], "eligible": true}.
    A teacher can only change questions of her own subjects."""
    ids, eligible = request.data.get("question_ids"), request.data.get("eligible")
    if not isinstance(ids, list) or not ids or len(ids) > 1000 or not all(isinstance(i, int) for i in ids):
        raise ValidationError({"question_ids": "Send a list of question ids."})
    if not isinstance(eligible, bool):
        raise ValidationError({"eligible": "Send true or false."})
    qs = Question.objects.filter(pk__in=ids)
    if not request.user.is_admin_role:
        qs = qs.filter(subject__in=TeacherAssignment.objects.filter(teacher=request.user).values("subject"))
    updated = qs.update(practice_eligible=eligible)
    audit(request.user, "practice.mark_eligible", len(ids), eligible=eligible, updated=updated)
    return Response({"updated": updated, "skipped": len(set(ids)) - updated})


# ---------------------------------------------------------------- admin settings (ADM-09)

def _settings_payload(s):
    cfg = services.config()
    return {"xp_values": cfg["xp"], "levels": services.level_table(cfg), "badge_tiers": cfg["tiers"],
            "freezes_per_month": s.freezes_per_month, "practice_daily_xp_quizzes": s.practice_daily_xp_quizzes,
            "defaults": {"xp_values": rules.DEFAULT_XP, "levels": rules.DEFAULT_LEVELS,
                         "badge_tiers": {b["code"]: b["tiers"] for b in catalog.BADGES}}}


@api_view(["GET", "PATCH"])
@permission_classes([IsAdminRole])
def gamification_settings(request):
    """Admins edit XP values, levels, badge targets, the monthly streak freezes and the daily practice XP limit.
    Send only what changes. Send {"reset": true} to go back to the SRS defaults.
    (Leaderboard on/off and class position on/off live in /api/settings/.)"""
    s = GamificationSettings.load()
    if request.method == "PATCH":
        d, errors = request.data, {}
        if d.get("reset") is True:
            s.xp_values, s.levels, s.badge_tiers = {}, [], {}
            s.freezes_per_month, s.practice_daily_xp_quizzes = 2, 5
            s.save()
            audit(request.user, "gamification.reset", 1)
            return Response(_settings_payload(s))
        if "xp_values" in d:
            clean, problems = rules.validate_xp(d["xp_values"])
            if problems:
                errors["xp_values"] = problems
            else:
                s.xp_values = {**(s.xp_values or {}), **clean}
        if "levels" in d:
            clean, problems = rules.validate_levels(d["levels"])
            if problems:
                errors["levels"] = problems
            else:
                s.levels = clean
        if "badge_tiers" in d:
            clean, problems = rules.validate_tiers(d["badge_tiers"], set(catalog.BY_CODE))
            if problems:
                errors["badge_tiers"] = problems
            else:
                s.badge_tiers = {**(s.badge_tiers or {}), **clean}
        for name, lo, hi in (("freezes_per_month", 0, 10), ("practice_daily_xp_quizzes", 1, 50)):
            if name in d:
                v = d[name]
                if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                    errors[name] = f"Enter a whole number from {lo} to {hi}."
                else:
                    setattr(s, name, v)
        if errors:
            return Response({"detail": "Some settings are not valid.", "errors": errors}, status=400)
        s.save()
        audit(request.user, "gamification.update", 1, fields=sorted(k for k in d if k != "reset"))
    return Response(_settings_payload(s))
