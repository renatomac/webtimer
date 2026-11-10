import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("timerapp", "0002_spotifyaccount"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Timer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("rounds", models.PositiveIntegerField(default=3, help_text="Number of rounds")),
                ("duration", models.PositiveIntegerField(default=180, help_text="Duration per round in seconds")),
                ("interval", models.PositiveIntegerField(default=60, help_text="Rest interval between rounds in seconds")),
                ("direction", models.CharField(choices=[("UP", "Count Up"), ("DOWN", "Count Down")], default="DOWN", max_length=4)),
                ("sound_file", models.FileField(blank=True, help_text="Optional audio file (.mp3, .wav) to play at the end of the timer", null=True, upload_to="timer_sounds/")),
                ("status", models.CharField(choices=[("READY", "Ready"), ("RUNNING", "Running"), ("PAUSED", "Paused"), ("DONE", "Done")], default="READY", max_length=10)),
                ("current_round", models.PositiveIntegerField(default=1)),
                ("current_state", models.CharField(choices=[("WORK", "Work"), ("REST", "Rest")], default="WORK", max_length=10)),
                ("time_remaining", models.PositiveIntegerField(blank=True, null=True)),
                ("last_started_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="timers", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
