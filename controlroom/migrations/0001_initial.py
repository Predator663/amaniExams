from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="SiteControl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("maintenance", models.BooleanField(default=False)),
                ("message", models.TextField(blank=True, default="")),
                ("back_at", models.CharField(blank=True, default="", help_text="Free text, e.g. 'around 18:00'", max_length=80)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("started_by", models.CharField(blank=True, default="", max_length=150)),
            ],
            options={"verbose_name": "Control room", "verbose_name_plural": "Control room"},
        ),
        migrations.CreateModel(
            name="ControlEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("who", models.CharField(max_length=150)),
                ("action", models.CharField(max_length=40)),
                ("detail", models.TextField(blank=True, default="")),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
            ],
            options={"ordering": ["-at", "-id"]},
        ),
    ]
