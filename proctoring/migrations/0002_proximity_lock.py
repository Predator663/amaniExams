import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("proctoring", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="proximityalert", name="locked", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="proximityalert", name="locked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="proximityalert", name="unlocked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="proximityalert", name="unlocked_by", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
        migrations.AddIndex(model_name="proximityalert", index=models.Index(fields=["exam", "locked"], name="pr_alert_exam_locked")),
    ]
