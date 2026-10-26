from django.urls import path

from . import views

urlpatterns = [
    path("guardians/", views.guardians),
    path("guardians/summary/", views.summary),
    path("guardians/template/", views.template),
    path("guardians/upload/", views.upload),
    path("guardians/send/", views.send),
    path("guardians/jobs/", views.jobs),
    path("guardians/jobs/retry/", views.job_retry),
    path("guardians/jobs/<int:pk>/retry/", views.job_retry),
    path("guardians/jobs/cancel-queued/", views.job_cancel_queued),
    path("guardians/devices/", views.devices),
    path("guardians/devices/<int:pk>/", views.device_detail),
    path("guardians/config/", views.config),
    path("guardians/<int:pk>/", views.guardian_detail),
    path("guardians/<int:pk>/reveal/", views.guardian_reveal),
    path("guardians/<int:pk>/links/", views.guardian_links),
    path("sms/ping/", views.sms_ping),
    path("sms/pull/", views.sms_pull),
    path("sms/report/", views.sms_report),
]
