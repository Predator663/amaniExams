from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("classes", views.SchoolClassViewSet, basename="class")
router.register("subjects", views.SubjectViewSet, basename="subject")
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("academic-years", views.AcademicYearViewSet, basename="academic-year")
router.register("terms", views.TermViewSet, basename="term")

urlpatterns = router.urls
