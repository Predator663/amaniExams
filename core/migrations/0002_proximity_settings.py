from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AddField(model_name="schoolsettings", name="proximity_alert_meters", field=models.FloatField(default=20)),
        migrations.AddField(model_name="schoolsettings", name="proximity_lock_enabled", field=models.BooleanField(default=False)),
    ]
