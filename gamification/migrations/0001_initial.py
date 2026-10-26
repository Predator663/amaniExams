import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("academics", "0002_initial"),
        ("exams", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GamificationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("xp_values", models.JSONField(blank=True, default=dict)),
                ("levels", models.JSONField(blank=True, default=list)),
                ("badge_tiers", models.JSONField(blank=True, default=dict)),
                ("freezes_per_month", models.PositiveSmallIntegerField(default=2)),
                ("practice_daily_xp_quizzes", models.PositiveSmallIntegerField(default=5)),
            ],
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("avatar", models.CharField(default="owl", max_length=20)),
                ("display_name", models.CharField(blank=True, max_length=30)),
                ("hide_from_leaderboard", models.BooleanField(default=False)),
                ("last_seen_level", models.PositiveSmallIntegerField(default=1)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="gamification", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="XPEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=20)),
                ("points", models.IntegerField()),
                ("key", models.CharField(max_length=80)),
                ("exam_id", models.PositiveIntegerField(blank=True, null=True)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="xp_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ActivityDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("source", models.CharField(max_length=10)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_days", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ExamRewardMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exam_id", models.PositiveIntegerField()),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                ("badges", models.JSONField(blank=True, default=list)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reward_marks", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="BadgeAward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("scope", models.CharField(blank=True, default="", max_length=20)),
                ("tier", models.PositiveSmallIntegerField(default=1)),
                ("awarded_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("seen", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="badges", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ReviewProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seen", models.JSONField(blank=True, default=list)),
                ("completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("attempt", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="review_progress", to="exams.attempt")),
            ],
        ),
        migrations.CreateModel(
            name="PracticeSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("items", models.JSONField(default=list)),
                ("answers", models.JSONField(blank=True, default=list)),
                ("seed", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(default="in_progress", max_length=12)),
                ("question_count", models.PositiveSmallIntegerField(default=0)),
                ("correct_score", models.FloatField(default=0)),
                ("xp_awarded", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="practice_sessions", to="academics.subject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="practice_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="xpevent",
            index=models.Index(fields=["user", "-created_at"], name="gam_xp_user_time"),
        ),
        migrations.AddConstraint(
            model_name="xpevent",
            constraint=models.UniqueConstraint(fields=("user", "key"), name="gam_xp_once"),
        ),
        migrations.AddConstraint(
            model_name="activityday",
            constraint=models.UniqueConstraint(fields=("user", "day"), name="gam_one_day"),
        ),
        migrations.AddConstraint(
            model_name="examrewardmark",
            constraint=models.UniqueConstraint(fields=("user", "exam_id"), name="gam_mark_once"),
        ),
        migrations.AddConstraint(
            model_name="badgeaward",
            constraint=models.UniqueConstraint(fields=("user", "code", "scope"), name="gam_badge_once"),
        ),
        migrations.AddIndex(
            model_name="practicesession",
            index=models.Index(fields=["user", "status"], name="gam_prac_user_status"),
        ),
    ]
