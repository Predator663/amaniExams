from django.db import migrations, models


class Migration(migrations.Migration):
    """Two new columns with safe defaults: existing messages stay login messages with the standard wording."""

    dependencies = [("guardians", "0002_smsjob_note")]

    operations = [
        migrations.AddField(model_name="smsjob", name="login", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="smsjob", name="template", field=models.TextField(blank=True, default="")),
    ]
