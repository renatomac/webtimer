from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("timerapp", "0001_initial")]
    operations = [migrations.CreateModel(name="SpotifyAccount", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("spotify_user_id", models.CharField(blank=True, default="", max_length=255)),
        ("display_name", models.CharField(blank=True, default="", max_length=255)),
        ("access_token", models.TextField()), ("refresh_token", models.TextField()),
        ("expires_at", models.DateTimeField()),
        ("last_playlist_uri", models.CharField(blank=True, default="", max_length=255)),
        ("last_device_id", models.CharField(blank=True, default="", max_length=255)),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="spotify_account", to=settings.AUTH_USER_MODEL)),
    ])]
