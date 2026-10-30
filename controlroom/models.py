from django.db import models


class SiteControl(models.Model):
    """One row only (pk=1): is the whole site in maintenance mode?"""
    maintenance = models.BooleanField(default=False)
    message = models.TextField(blank=True, default="")
    back_at = models.CharField(max_length=80, blank=True, default="", help_text="Free text, e.g. 'around 18:00'")
    started_at = models.DateTimeField(null=True, blank=True)
    started_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        verbose_name = "Control room"
        verbose_name_plural = "Control room"

    def __str__(self):
        return "Maintenance ON" if self.maintenance else "Site online"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ControlEvent(models.Model):
    """Who switched what, and when. Never edited from the admin."""
    at = models.DateTimeField(auto_now_add=True)
    who = models.CharField(max_length=150)
    action = models.CharField(max_length=40)
    detail = models.TextField(blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.who} {self.action}"
