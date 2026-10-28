from django.urls import path

from . import views

urlpatterns = [
    path("proctoring/config/", views.config),
    path("attempts/<int:attempt_id>/location/", views.report_location),
    path("proctoring/exams/<int:exam_id>/", views.exam_board),
    path("proctoring/place/", views.place),
    path("proctoring/alerts/<int:alert_id>/ack/", views.ack_alert),
]
