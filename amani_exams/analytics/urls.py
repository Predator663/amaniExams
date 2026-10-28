from django.urls import path

from . import views

urlpatterns = [
    path("analytics/subjects/", views.subject_list),
    path("analytics/subjects/<int:subject_id>/", views.subject_dashboard),
    path("analytics/subjects/<int:subject_id>/students/", views.subject_students),
    path("analytics/subjects/<int:subject_id>/students/<int:student_id>/", views.subject_student_profile),
    path("analytics/subjects/<int:subject_id>/heatmap/", views.subject_heatmap),
    path("analytics/subjects/<int:subject_id>/export/", views.subject_export),
    path("analytics/exams/<int:exam_id>/questions/", views.exam_question_analysis),
    path("analytics/exams/<int:exam_id>/integrity/", views.exam_integrity),
    path("analytics/school/", views.school_analytics),
    path("student/analytics/", views.student_analytics),
    path("student/report-card/", views.student_report_card),
    path("results/<int:attempt_id>/slip/", views.my_slip),
    path("exports/slip/<int:attempt_id>/", views.admin_slip),
    path("exports/exams/<int:exam_id>/results/", views.exam_results_export),
    path("exports/students/", views.students_export),
]
