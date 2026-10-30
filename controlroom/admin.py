"""Django admin for the control room.

* SiteControl  -> the 'Control room' entry in the sidebar opens the real control room page.
* ControlEvent -> read-only history of every switch (who, what, when, from which address).
* EVERY other model of the project that is not already registered gets a generic admin from autoregister(), which
  ControlRoomConfig.ready() calls once all apps' admin.py files have been imported. A model added later is picked up
  automatically, no admin.py needed.

All of these are for the owner only (state.is_owner). Password, token, encrypted and similar fields are never shown or editable
(same rule as God's Eye, eye.HIDE).
"""
from django.contrib import admin
from django.db import models as dj
from django.shortcuts import redirect

from . import eye, state
from .models import ControlEvent, SiteControl

MAX_COLUMNS = 6
# Never put these in the admin: a login token's key and a session's key ARE the credential (and would end up in the page address).
SKIP = {"authtoken.token", "sessions.session"}
# Shown, but never editable: they are written by Django itself.
ALWAYS_READ_ONLY = {"admin.logentry", "contenttypes.contenttype", "auth.permission"}


class OwnerReadOnlyAdmin(admin.ModelAdmin):
    """Owner may look, nobody may add, change or delete. Note has_view_permission takes `obj`: Django passes it when a row is opened."""
    list_per_page = 50
    show_full_result_count = False

    def has_module_permission(self, request):
        return state.is_owner(request.user)

    def has_view_permission(self, request, obj=None):
        return state.is_owner(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OwnerModelAdmin(OwnerReadOnlyAdmin):
    """Owner may do everything, nobody else may even see it."""
    can_add = True

    def has_change_permission(self, request, obj=None):
        return state.is_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return state.is_owner(request.user)

    def has_add_permission(self, request):
        return self.can_add and state.is_owner(request.user)


@admin.register(SiteControl)
class SiteControlAdmin(OwnerReadOnlyAdmin):
    """The row itself is never edited here: the sidebar entry opens the control room."""

    def changelist_view(self, request, extra_context=None):
        return redirect("controlroom:home")


def _short(text, n=80):
    text = "" if text is None else str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


@admin.register(ControlEvent)
class ControlEventAdmin(OwnerReadOnlyAdmin):
    list_display = ("at", "who", "action", "short_detail", "ip")
    list_filter = ("action", "at")
    search_fields = ("who", "action", "detail", "ip")
    readonly_fields = ("at", "who", "action", "detail", "ip")

    @admin.display(description="Detail")
    def short_detail(self, obj):
        return _short(obj.detail)


def _build(m):
    """A safe generic admin class for model m."""
    label = m._meta.label_lower
    fields = [f for f in m._meta.concrete_fields]
    hidden = {f.name for f in fields if eye.HIDE.search(f.name) or isinstance(f, dj.BinaryField)} - {m._meta.pk.name}
    visible = [f for f in fields if f.name not in hidden and not f.primary_key]

    attrs = {
        "exclude": tuple(sorted(hidden)),
        "can_add": not hidden,  # a row with hidden (encrypted / secret) columns cannot be created by hand
        "list_display_links": ("col_id",),
    }

    def col_id(self, obj):
        return obj.pk
    col_id.short_description = "ID"
    col_id.admin_order_field = "pk"
    attrs["col_id"] = col_id

    display = ["col_id"]
    for f in visible[:MAX_COLUMNS]:
        if isinstance(f, dj.TextField):  # long text would stretch the page: show the start only
            def col(self, obj, _n=f.name):
                return _short(getattr(obj, _n, ""))
            col.short_description = f.verbose_name
            attrs["col_" + f.name] = col
            display.append("col_" + f.name)
        else:
            display.append(f.name)
    attrs["list_display"] = tuple(display)

    attrs["list_filter"] = tuple(
        f.name for f in visible
        if isinstance(f, (dj.BooleanField, dj.DateTimeField)) or (f.choices and not f.is_relation)
    )[:5]
    attrs["search_fields"] = tuple(n for n in eye.text_fields(m) if n not in hidden)[:6]
    attrs["raw_id_fields"] = tuple(  # a drop-down with every student would be huge
        [f.name for f in visible if f.many_to_one or f.one_to_one]
        + [f.name for f in m._meta.many_to_many if f.remote_field.through._meta.auto_created and f.name not in hidden]
    )
    attrs["readonly_fields"] = tuple(f.name for f in visible if not f.editable)

    base = OwnerReadOnlyAdmin if label in ALWAYS_READ_ONLY else OwnerModelAdmin
    return type(f"{m.__name__}OwnerAdmin", (base,), attrs)


def autoregister():
    """Register every model that has no admin yet. Safe to call twice."""
    for m in eye.all_models():
        if m._meta.label_lower in SKIP or admin.site.is_registered(m):
            continue
        admin.site.register(m, _build(m))
