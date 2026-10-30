from django.contrib import admin
from django.shortcuts import redirect

from . import state
from .models import ControlEvent, SiteControl


@admin.register(SiteControl)
class SiteControlAdmin(admin.ModelAdmin):
    """The 'Control room' entry in the admin sidebar opens the real control room. The row itself is never edited here."""

    def has_module_permission(self, request):
        return state.is_owner(request.user)

    def has_view_permission(self, request, obj=None):
        return state.is_owner(request.user)

    has_add_permission = has_change_permission = has_delete_permission = lambda self, request, obj=None: False

    def changelist_view(self, request, extra_context=None):
        return redirect("controlroom:home")


@admin.register(ControlEvent)
class ControlEventAdmin(admin.ModelAdmin):
    list_display = ("at", "who", "action", "detail", "ip")
    readonly_fields = [f.name for f in ControlEvent._meta.fields]

    def has_module_permission(self, request):
        return state.is_owner(request.user)

    has_view_permission = has_module_permission
    has_add_permission = has_change_permission = has_delete_permission = lambda self, request, obj=None: False
