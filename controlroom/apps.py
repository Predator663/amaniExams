from django.apps import AppConfig


class ControlRoomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "controlroom"
    verbose_name = "Control room"

    def ready(self):
        # Runs after django.contrib.admin has imported every app's admin.py, so only models without an admin of their own are added.
        from .admin import autoregister
        autoregister()
