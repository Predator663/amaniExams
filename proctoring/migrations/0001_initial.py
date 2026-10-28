import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('exams', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalAcceptance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=20)),
                ('accepted_at', models.DateTimeField(auto_now_add=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='exams.exam')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='legal_acceptances', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['user', 'exam'], name='pr_accept_user_exam')],
            },
        ),
        migrations.CreateModel(
            name='LiveLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lat', models.FloatField()),
                ('lng', models.FloatField()),
                ('accuracy', models.FloatField(default=0)),
                ('speed', models.FloatField(blank=True, null=True)),
                ('heading', models.FloatField(blank=True, null=True)),
                ('anchor_lat', models.FloatField(blank=True, null=True)),
                ('anchor_lng', models.FloatField(blank=True, null=True)),
                ('moving_until', models.DateTimeField(blank=True, null=True)),
                ('moving_source', models.CharField(blank=True, max_length=10)),
                ('sensors', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('attempt', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='live_location', to='exams.attempt')),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='exams.exam')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['exam', 'updated_at'], name='pr_loc_exam_upd'), models.Index(fields=['lat', 'lng'], name='pr_loc_latlng')],
            },
        ),
        migrations.CreateModel(
            name='ProximityAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_seen', models.DateTimeField()),
                ('last_seen', models.DateTimeField()),
                ('min_distance', models.FloatField()),
                ('last_distance', models.FloatField()),
                ('confidence', models.CharField(default='possible', max_length=10)),
                ('active', models.BooleanField(default=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('snapshot', models.JSONField(blank=True, default=dict)),
                ('a', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('acknowledged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('b', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proximity_alerts', to='exams.exam')),
            ],
            options={
                'ordering': ['-last_seen'],
                'indexes': [models.Index(fields=['exam', 'active'], name='pr_alert_exam_active')],
            },
        ),
    ]
