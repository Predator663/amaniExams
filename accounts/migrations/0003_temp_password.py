from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_manager")]

    operations = [
        migrations.AddField(model_name="user", name="temp_serial", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="user", name="temp_issued_at", field=models.DateTimeField(blank=True, null=True)),
    ]
