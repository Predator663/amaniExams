from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("exams", views.ExamViewSet, basename="exam")

urlpatterns = [
    path("overview/", views.staff_overview),
    path("student/exams/", views.student_exams),
    path("student/exams/<int:exam_id>/start/", views.student_start),
    path("attempts/<int:attempt_id>/", views.attempt_current),
    path("attempts/<int:attempt_id>/answer/", views.attempt_answer),
    path("attempts/<int:attempt_id>/finish/", views.attempt_finish),
    path("attempts/<int:attempt_id>/event/", views.attempt_event),
    path("results/", views.my_results),
    path("results/pending/", views.my_results_pending),
    path("results/<int:attempt_id>/", views.result_detail),
    path("results/<int:attempt_id>/review/", views.result_review),
] + router.urls
