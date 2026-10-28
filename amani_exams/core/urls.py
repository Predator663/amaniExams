from django.urls import path

from . import views

urlpatterns = [
    path("presence/", views.presence),
    path("settings/", views.school_settings),
    path("settings/logo/", views.settings_logo),
    path("audit-log/", views.audit_log),
    path("i18n/<str:lang>/", views.i18n_catalog),
]
