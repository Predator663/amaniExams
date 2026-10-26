from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("questions", views.QuestionViewSet, basename="question")

urlpatterns = [path("question-images/", views.upload_image)] + router.urls
