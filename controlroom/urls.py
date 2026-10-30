from django.urls import path

from . import views

app_name = "controlroom"
urlpatterns = [
    path("", views.home, name="home"),
    path("maintenance/on/", views.enable_maintenance, name="on"),
    path("maintenance/off/", views.disable_maintenance, name="off"),
    path("eye/", views.god_eye, name="eye"),
    path("eye/data/", views.eye_data, name="eye_data"),
    path("eye/tables/", views.models_index, name="tables"),
    path("eye/tables/<str:label>/", views.model_rows, name="rows"),
]
