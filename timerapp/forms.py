import re

from django import forms

from .models import Preset, Timer
from .time_utils import seconds_to_hms

TIME_RE = re.compile(r"^(\d{1,3}):(\d{2})$")


def parse_mmss(value):
    match = TIME_RE.match((value or "").strip())
    if not match:
        raise forms.ValidationError("Enter time as mm:ss, e.g. 05:00.")
    minutes, seconds = int(match.group(1)), int(match.group(2))
    if seconds > 59:
        raise forms.ValidationError("Seconds must be 59 or less.")
    return minutes * 60 + seconds


def format_mmss(total):
    return f"{total // 60:02d}:{total % 60:02d}"


class PresetForm(forms.Form):
    name = forms.CharField(max_length=100)
    rounds = forms.IntegerField(min_value=1, max_value=99)
    round_duration = forms.CharField(label="Round duration (mm:ss)", max_length=7)
    rest_duration = forms.CharField(label="Rest interval (mm:ss)", max_length=7, initial="00:00")
    direction = forms.ChoiceField(choices=Preset.DIRECTIONS)

    def __init__(self, *args, instance=None, **kwargs):
        if instance is not None and not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "name": instance.name, "rounds": instance.rounds, "direction": instance.direction,
                "round_duration": format_mmss(instance.round_seconds),
                "rest_duration": format_mmss(instance.rest_seconds),
            }
        super().__init__(*args, **kwargs)

    def clean_round_duration(self):
        seconds = parse_mmss(self.cleaned_data["round_duration"])
        if seconds <= 0:
            raise forms.ValidationError("Round duration must be greater than zero.")
        return seconds

    def clean_rest_duration(self):
        return parse_mmss(self.cleaned_data["rest_duration"])

    def save(self, studio, instance=None):
        preset = instance or Preset(studio=studio)
        d = self.cleaned_data
        preset.name, preset.rounds, preset.direction = d["name"], d["rounds"], d["direction"]
        preset.round_seconds, preset.rest_seconds = d["round_duration"], d["rest_duration"]
        preset.save()
        return preset


def parse_timer_time(value):
    value = (value or "").strip()
    if not re.fullmatch(r"\d+(?::\d+){0,2}", value):
        raise forms.ValidationError("Use H:mm:ss, mm:ss, or seconds.")

    parts = [int(part) for part in value.split(":")]
    if len(parts) == 1:
        return parts[0]
    if parts[-1] > 59 or (len(parts) == 3 and parts[-2] > 59):
        raise forms.ValidationError("Minutes and seconds must be 59 or less.")
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


class TimerForm(forms.ModelForm):
    rounds = forms.IntegerField(min_value=1)
    duration_str = forms.CharField(label="Duration (H:mm:ss or mm:ss)", initial="3:00")
    interval_str = forms.CharField(label="Rest interval (H:mm:ss or mm:ss)", initial="1:00")

    class Meta:
        model = Timer
        fields = ["name", "rounds", "duration_str", "interval_str", "direction", "sound_file"]
        widgets = {"rounds": forms.NumberInput(attrs={"min": 1})}

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        initial = kwargs.get("initial", {}).copy()
        if instance:
            initial.setdefault("duration_str", seconds_to_hms(instance.duration))
            initial.setdefault("interval_str", seconds_to_hms(instance.interval))
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

    def clean_duration_str(self):
        duration = parse_timer_time(self.cleaned_data["duration_str"])
        if duration <= 0:
            raise forms.ValidationError("Duration must be greater than zero.")
        return duration

    def clean_interval_str(self):
        return parse_timer_time(self.cleaned_data["interval_str"])

    def save(self, commit=True):
        timer = super().save(commit=False)
        timer.duration = self.cleaned_data["duration_str"]
        timer.interval = self.cleaned_data["interval_str"]
        if commit:
            timer.save()
        return timer
