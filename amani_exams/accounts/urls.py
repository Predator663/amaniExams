from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("teachers", views.TeacherViewSet, basename="teacher")
router.register("admins", views.AdminAccountViewSet, basename="admin-account")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.logout),
    path("auth/change-password/", views.ChangePasswordView.as_view()),
    path("me/", views.MeView.as_view()),
    path("students/bulk-action/", views.students_bulk_action),
    path("students/credentials/", views.class_credentials),
    path("students/bulk-upload/template/", views.upload_template),
    path("students/bulk-upload/validate/", views.bulk_validate),
    path("students/bulk-upload/<int:batch_id>/confirm/", views.bulk_confirm),
    path("students/bulk-upload/<int:batch_id>/credentials/", views.bulk_credentials),
] + router.urls
