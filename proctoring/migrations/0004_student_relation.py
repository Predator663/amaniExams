import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("proctoring", "0003_integrity_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentRelation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("twin", "Twins"), ("house", "Same house"), ("room", "Same room")], default="house", max_length=8)),
                ("note", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("a", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("b", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(model_name="studentrelation", constraint=models.UniqueConstraint(fields=("a", "b"), name="pr_relation_pair")),
        migrations.AddConstraint(model_name="studentrelation", constraint=models.CheckConstraint(condition=models.Q(("a__lt", models.F("b"))), name="pr_relation_ordered")),
    ]
