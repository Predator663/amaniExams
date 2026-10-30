from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("exams", "0002_exam_submission")]

    operations = [
        migrations.AddField(model_name="attempt", name="screen_lock", field=models.CharField(blank=True, default="", max_length=10)),
        migrations.AddField(model_name="attempt", name="screen_locked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="attempt", name="leaves_forgiven", field=models.PositiveIntegerField(default=0)),
    ]
