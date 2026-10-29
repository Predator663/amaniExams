from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guardians", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="smsjob",
            name="note",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
