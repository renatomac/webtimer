import re

from django import forms

from .models import Preset

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
