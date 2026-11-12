import secrets
from zoneinfo import available_timezones

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def timezone_choices():
    return [(name, name) for name in sorted(available_timezones())]


def validate_timezone(value):
    if value not in available_timezones():
        raise ValidationError("Unknown timezone.")


def new_display_token():
    return secrets.token_urlsafe(24)


class Studio(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    logo = models.ImageField(upload_to="logos/", blank=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    display_token = models.CharField(max_length=64, unique=True, default=new_display_token, editable=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def regenerate_display_token(self):
        self.display_token = new_display_token()
        self.save(update_fields=["display_token"])


class StudioMembership(models.Model):
    """Grants a user administrator access to exactly one studio."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="studio_memberships")
    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        unique_together = [("user", "studio")]

    def __str__(self):
        return f"{self.user} @ {self.studio}"


class Preset(models.Model):
    UP = "up"
    DOWN = "down"
    DIRECTIONS = [(UP, "Count up"), (DOWN, "Count down")]

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="presets")
    name = models.CharField(max_length=100)
    rounds = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99)])
    round_seconds = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rest_seconds = models.PositiveIntegerField(default=0)
    direction = models.CharField(max_length=4, choices=DIRECTIONS, default=DOWN)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def round_display(self):
        return f"{self.round_seconds // 60:02d}:{self.round_seconds % 60:02d}"

    @property
    def rest_display(self):
        return f"{self.rest_seconds // 60:02d}:{self.rest_seconds % 60:02d}"


class TimerSession(models.Model):
    READY, RUNNING, PAUSED, STOPPED, FINISHED = "ready", "running", "paused", "stopped", "finished"
    STATES = [(s, s.title()) for s in (READY, RUNNING, PAUSED, STOPPED, FINISHED)]

    studio = models.OneToOneField(Studio, on_delete=models.CASCADE, related_name="session")
    selected_preset = models.ForeignKey(Preset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    state = models.CharField(max_length=10, choices=STATES, default=READY)
    run = models.PositiveIntegerField(default=0)
    # Snapshot of the preset taken at Start so later edits only affect future runs.
    name = models.CharField(max_length=100, blank=True)
    rounds = models.PositiveSmallIntegerField(default=1)
    round_seconds = models.PositiveIntegerField(default=1)
    rest_seconds = models.PositiveIntegerField(default=0)
    direction = models.CharField(max_length=4, choices=Preset.DIRECTIONS, default=Preset.DOWN)
    elapsed_ms = models.BigIntegerField(default=0)
    running_since = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.studio}: {self.state}"


class SpotifyAccount(models.Model):
    """A controller user's Spotify OAuth tokens and last-used playback choices."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spotify_account")
    spotify_user_id = models.CharField(max_length=255, blank=True, default="")
    display_name = models.CharField(max_length=255, blank=True, default="")
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    last_playlist_uri = models.CharField(max_length=255, blank=True, default="")
    last_device_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at


class Timer(models.Model):
    DIRECTION_CHOICES = [
        ("UP", "Count Up"),
        ("DOWN", "Count Down"),
    ]

    STATUS_CHOICES = [
        ("READY", "Ready"),
        ("RUNNING", "Running"),
        ("PAUSED", "Paused"),
        ("DONE", "Done"),
    ]

    STATE_CHOICES = [
        ("WORK", "Work"),
        ("REST", "Rest"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="timers")
    name = models.CharField(max_length=255)
    rounds = models.PositiveIntegerField(default=3, help_text="Number of rounds")
    duration = models.PositiveIntegerField(default=180, help_text="Duration per round in seconds")
    interval = models.PositiveIntegerField(default=60, help_text="Rest interval between rounds in seconds")
    direction = models.CharField(max_length=4, choices=DIRECTION_CHOICES, default="DOWN")
    sound_file = models.FileField(
        upload_to="timer_sounds/",
        null=True,
        blank=True,
        help_text="Optional audio file (.mp3, .wav) to play at the end of the timer",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="READY")
    current_round = models.PositiveIntegerField(default=1)
    current_state = models.CharField(max_length=10, choices=STATE_CHOICES, default="WORK")
    time_remaining = models.PositiveIntegerField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.rounds}x{self.duration}s)"

    @property
    def work_label(self):
        from .time_utils import seconds_to_hms
        return seconds_to_hms(self.duration)

    @property
    def rest_label(self):
        from .time_utils import seconds_to_hms
        return seconds_to_hms(self.interval)

    @property
    def total_label(self):
        from .time_utils import seconds_to_hms
        return seconds_to_hms(self.rounds * self.duration + max(0, self.rounds - 1) * self.interval)

    def save(self, *args, **kwargs):
        if self.time_remaining is None:
            self.time_remaining = self.duration

        if not kwargs.get("update_fields") and self.status == "READY":
            self.time_remaining = self.duration
            self.current_round = 1
            self.current_state = "WORK"
            self.last_started_at = None
        super().save(*args, **kwargs)

    def get_current_timer_state(self, now=None):
        if self.status != "RUNNING" or not self.last_started_at:
            return self.status, self.current_state, self.current_round, self.time_remaining

        from django.utils import timezone

        elapsed = int(((now or timezone.now()) - self.last_started_at).total_seconds())
        if elapsed <= 0:
            return self.status, self.current_state, self.current_round, self.time_remaining

        status = self.status
        current_state = self.current_state
        current_round = self.current_round
        time_remaining = self.time_remaining

        while elapsed > 0:
            if elapsed < time_remaining:
                time_remaining -= elapsed
                elapsed = 0
            else:
                elapsed -= time_remaining
                if current_state == "WORK":
                    if current_round < self.rounds:
                        current_state = "REST"
                        time_remaining = self.interval
                    else:
                        status = "DONE"
                        current_state = "WORK"
                        time_remaining = 0
                        elapsed = 0
                else:
                    current_state = "WORK"
                    current_round += 1
                    time_remaining = self.duration

        return status, current_state, current_round, time_remaining

    def sync_state(self, save=True):
        from django.utils import timezone

        now = timezone.now()
        new_status, new_state, new_round, new_remaining = self.get_current_timer_state(now)
        # A read must not move the running clock. Only normalize at phase boundaries.
        if new_status == "RUNNING" and (new_state, new_round) == (self.current_state, self.current_round):
            return
        if (self.status, self.current_state, self.current_round, self.time_remaining) == (
            new_status, new_state, new_round, new_remaining
        ):
            return

        self.status = new_status
        self.current_state = new_state
        self.current_round = new_round
        if new_status == "RUNNING":
            duration = self.duration if new_state == "WORK" else self.interval
            passed = duration - new_remaining
            elapsed = int((now - self.last_started_at).total_seconds())
            self.last_started_at += timezone.timedelta(seconds=elapsed - passed)
            self.time_remaining = duration
        else:
            self.time_remaining = new_remaining
            self.last_started_at = None

        if save:
            self.save(update_fields=[
                "status", "current_state", "current_round", "time_remaining", "last_started_at", "updated_at"
            ])

    def to_dict(self):
        from django.utils import timezone

        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "current_state": self.current_state,
            "current_round": self.current_round,
            "time_remaining": self.time_remaining,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "duration": self.duration,
            "interval": self.interval,
            "rounds": self.rounds,
            "direction": self.direction,
            "sound_file_url": self.sound_file.url if self.sound_file else None,
            "server_time": timezone.now().isoformat(),
        }
