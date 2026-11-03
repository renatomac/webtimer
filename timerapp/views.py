from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import services
from .forms import PresetForm
from .models import Preset, Studio


def user_studios(user):
    if user.is_superuser:
        return Studio.objects.all()
    return Studio.objects.filter(memberships__user=user)


def studio_for(request, slug):
    """Studio the logged-in user may manage; 404 otherwise so other studios stay hidden."""
    return get_object_or_404(user_studios(request.user), slug=slug)


@login_required
def home(request):
    studios = list(user_studios(request.user))
    if len(studios) == 1:
        return redirect("control", slug=studios[0].slug)
    return render(request, "timerapp/home.html", {"studios": studios})


@login_required
def control(request, slug):
    studio = studio_for(request, slug)
    initial_state = services.snapshot(studio)
    return render(request, "timerapp/control.html", {
        "studio": studio,
        "presets": studio.presets.all(),
        "initial_state": initial_state,
        "config": {
            "state": initial_state,
            "stateUrl": reverse("state", args=[studio.slug]),
            "commandUrl": reverse("command", args=[studio.slug, "CMD"]),
            "selectUrl": reverse("select_preset", args=[studio.slug]),
        },
        "display_url": request.build_absolute_uri(f"/d/{studio.display_token}/"),
    })


@login_required
@never_cache
@require_GET
def state(request, slug):
    return JsonResponse(services.snapshot(studio_for(request, slug)))


@login_required
@require_POST
def command(request, slug, name):
    studio = studio_for(request, slug)
    try:
        data = services.apply_command(studio, name)
    except services.InvalidCommand as exc:
        return JsonResponse({"error": str(exc), "state": services.snapshot(studio)}, status=409)
    return JsonResponse(data)


@login_required
@require_POST
def select_preset(request, slug):
    studio = studio_for(request, slug)
    preset = studio.presets.filter(pk=request.POST.get("preset") or 0).first()
    if preset is None:
        return JsonResponse({"error": "Unknown preset.", "state": services.snapshot(studio)}, status=400)
    try:
        data = services.select_preset(studio, preset)
    except services.InvalidCommand as exc:
        return JsonResponse({"error": str(exc), "state": services.snapshot(studio)}, status=409)
    return JsonResponse(data)


@login_required
@require_POST
def regenerate_link(request, slug):
    studio = studio_for(request, slug)
    studio.regenerate_display_token()
    messages.success(request, "Display link regenerated. The old link no longer works.")
    return redirect("control", slug=studio.slug)


@login_required
def preset_list(request, slug):
    studio = studio_for(request, slug)
    return render(request, "timerapp/preset_list.html", {"studio": studio, "presets": studio.presets.all()})


@login_required
def preset_edit(request, slug, pk=None):
    studio = studio_for(request, slug)
    preset = get_object_or_404(studio.presets, pk=pk) if pk else None
    form = PresetForm(request.POST or None, instance=preset)
    if request.method == "POST" and form.is_valid():
        form.save(studio, preset)
        messages.success(request, "Preset saved.")
        return redirect("preset_list", slug=studio.slug)
    return render(request, "timerapp/preset_form.html", {"studio": studio, "form": form, "preset": preset})


@login_required
@require_POST
def preset_delete(request, slug, pk):
    studio = studio_for(request, slug)
    get_object_or_404(studio.presets, pk=pk).delete()
    messages.success(request, "Preset deleted.")
    return redirect("preset_list", slug=studio.slug)


def display_studio(token):
    try:
        return Studio.objects.get(display_token=token)
    except Studio.DoesNotExist:
        raise Http404


@never_cache
def display(request, token):
    studio = display_studio(token)
    config = {
        "state": services.snapshot(studio),
        "stateUrl": reverse("display_state", args=[token]),
        "timezone": studio.timezone,
    }
    return render(request, "timerapp/display.html", {"studio": studio, "config": config})


@never_cache
@require_GET
def display_state(request, token):
    return JsonResponse(services.snapshot(display_studio(token)))
