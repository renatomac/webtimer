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
