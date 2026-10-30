from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0002_proximity_settings")]

    operations = [
        migrations.AddField(model_name="schoolsettings", name="leave_lock_enabled", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="schoolsettings", name="leave_lock_limit", field=models.PositiveSmallIntegerField(default=3)),
    ]
