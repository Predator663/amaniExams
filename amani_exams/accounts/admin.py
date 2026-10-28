from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AmaniUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("School", {"fields": ("role", "index_number", "school_class", "must_change_password", "is_archived")}),
    )
    list_display = ("username", "first_name", "last_name", "role", "school_class", "is_active")
    list_filter = ("role", "school_class", "is_active")
