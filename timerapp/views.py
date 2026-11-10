import json
import secrets
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import services
from .forms import PresetForm
from .models import Preset, Studio, SpotifyAccount
from . import spotify_client


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
    presets = studio.presets.all()
    # A browser selects the first option visually, but the timer session must
    # also know which preset to load. Make the first preset the real default.
    if initial_state["preset"] is None:
        first_preset = presets.first()
        if first_preset is not None:
            initial_state = services.select_preset(studio, first_preset)
    return render(request, "timerapp/control.html", {
        "studio": studio,
        "presets": presets,
        "initial_state": initial_state,
        "config": {
            "state": initial_state,
            "stateUrl": reverse("state", args=[studio.slug]),
            "commandUrl": reverse("command", args=[studio.slug, "CMD"]),
            "selectUrl": reverse("select_preset", args=[studio.slug]),
            "spotifyStatusUrl": reverse("spotify_status", args=[studio.slug]),
            "spotifyDataUrl": reverse("spotify_data", args=[studio.slug, "KIND"]),
            "spotifyControlUrl": reverse("spotify_control", args=[studio.slug]),
        },
        "display_url": request.build_absolute_uri(reverse("display", args=[studio.display_token])),
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


@login_required
def spotify_connect(request, slug):
    studio_for(request, slug)
    if not spotify_client.is_configured():
        messages.error(request, "Spotify is not configured on this server.")
        return redirect("control", slug=slug)
    state = secrets.token_urlsafe(24)
    request.session["spotify_oauth_state"] = state
    request.session["spotify_return_to"] = reverse("control", args=[slug])
    return redirect(spotify_client.authorize_url(state))


@login_required
def spotify_callback(request):
    return_to = request.session.pop("spotify_return_to", "home")
    if request.GET.get("error") or request.GET.get("state") != request.session.pop("spotify_oauth_state", None) or not request.GET.get("code"):
        messages.error(request, "Spotify authorization was cancelled or could not be verified.")
        return redirect(return_to)
    try:
        data = spotify_client.exchange(request.GET["code"])
        account, _ = SpotifyAccount.objects.get_or_create(user=request.user, defaults={"access_token":"", "refresh_token":"", "expires_at":timezone.now()})
        account.access_token, account.refresh_token = data["access_token"], data.get("refresh_token") or account.refresh_token
        account.expires_at = timezone.now() + timezone.timedelta(seconds=data.get("expires_in", 3600))
        profile = spotify_client.profile(account)
        account.spotify_user_id, account.display_name = profile.get("id", ""), profile.get("display_name") or profile.get("id", "")
        account.save(); messages.success(request, f"Connected to Spotify as {account.display_name}.")
    except Exception as exc:
        messages.error(request, f"Could not connect to Spotify: {exc}")
    return redirect(return_to)


def spotify_account(request, slug):
    studio_for(request, slug)
    return SpotifyAccount.objects.filter(user=request.user).first()


@login_required
def spotify_disconnect(request, slug):
    spotify_account(request, slug)
    SpotifyAccount.objects.filter(user=request.user).delete(); messages.success(request, "Disconnected Spotify.")
    return redirect("control", slug=slug)


@login_required
def spotify_status(request, slug):
    account = spotify_account(request, slug)
    return JsonResponse({"configured": spotify_client.is_configured(), "connected": bool(account), "display_name": account.display_name if account else "", "last_playlist_uri": account.last_playlist_uri if account else "", "last_device_id": account.last_device_id if account else ""})


@login_required
def spotify_data(request, slug, kind):
    account = spotify_account(request, slug)
    if not account: return JsonResponse({"error":"Spotify account not connected"}, status=400)
    try:
        if kind == "playlists": return JsonResponse({"playlists": spotify_client.playlists(account)})
        if kind == "devices": return JsonResponse({"devices": spotify_client.devices(account)})
        if kind == "playback": return JsonResponse(spotify_client.playback(account))
        return JsonResponse({"error":"Unknown Spotify resource"}, status=404)
    except Exception as exc: return JsonResponse({"error":str(exc)}, status=502)


@login_required
@require_POST
def spotify_control(request, slug):
    account = spotify_account(request, slug)
    if not account: return JsonResponse({"error":"Spotify account not connected"}, status=400)
    try: data = json.loads(request.body)
    except (ValueError, TypeError): return JsonResponse({"error":"Invalid request"}, status=400)
    action = data.get("action")
    if action not in ("play","resume","pause","stop","next","previous","shuffle","repeat","seek","volume"): return JsonResponse({"error":"Invalid Spotify action"}, status=400)
    if data.get("playlist_uri"): account.last_playlist_uri = data["playlist_uri"]
    if data.get("device_id"): account.last_device_id = data["device_id"]
    account.save(update_fields=["last_playlist_uri", "last_device_id", "updated_at"])
    try:
        spotify_client.control(account, action, data.get("device_id") or account.last_device_id or None, playlist_uri=data.get("playlist_uri") or account.last_playlist_uri, state=data.get("state"), position_ms=data.get("position_ms"), volume_percent=data.get("volume_percent"))
    except spotify_client.SpotifyPlaybackError as exc: return JsonResponse({"error":str(exc)}, status=409)
    except Exception as exc: return JsonResponse({"error":str(exc)}, status=502)
    return JsonResponse({"status":"ok"})
