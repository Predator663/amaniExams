from django.urls import path

from . import views

urlpatterns = [
    path("proctoring/config/", views.config),
    path("attempts/<int:attempt_id>/location/", views.report_location),
    path("proctoring/exams/<int:exam_id>/", views.exam_board),
    path("proctoring/place/", views.place),
    path("proctoring/alerts/<int:alert_id>/ack/", views.ack_alert),
    path("proctoring/alerts/<int:alert_id>/unlock/", views.unlock_alert),
    path("proctoring/flags/<int:flag_id>/ack/", views.ack_flag),
    path("proctoring/relations/", views.relations),
    path("proctoring/relations/<int:relation_id>/", views.relation_delete),
    path("proctoring/exams/<int:exam_id>/unlock-all/", views.unlock_exam),
]
