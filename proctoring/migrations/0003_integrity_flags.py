import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exams", "0001_initial"),
        ("proctoring", "0002_proximity_lock"),
    ]

    operations = [
        migrations.AddField(model_name="livelocation", name="devices", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="livelocation", name="spoof", field=models.JSONField(blank=True, default=dict)),
        migrations.CreateModel(
            name="IntegrityFlag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("device_changed", "Device changed"), ("login_during_exam", "Logged in again"), ("teleport", "Position jumped"), ("frozen_fix", "Position never moves"), ("perfect_accuracy", "Impossible accuracy"), ("rounded_coords", "Typed-in coordinates")], max_length=24)),
                ("severity", models.CharField(choices=[("info", "Info"), ("warning", "Warning"), ("high", "High")], default="warning", max_length=8)),
                ("count", models.PositiveIntegerField(default=1)),
                ("first_seen", models.DateTimeField()),
                ("last_seen", models.DateTimeField()),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="integrity_flags", to="exams.attempt")),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="integrity_flags", to="exams.exam")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="integrityflag", constraint=models.UniqueConstraint(fields=("attempt", "kind"), name="pr_flag_attempt_kind")),
        migrations.AddIndex(model_name="integrityflag", index=models.Index(fields=["exam", "acknowledged_at"], name="pr_flag_exam_ack")),
    ]
