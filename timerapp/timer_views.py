import json
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import spotify_client
from .forms import TimerForm
from .models import SpotifyAccount, Timer


@login_required
def timer_home(request):
    timers = Timer.objects.filter(user=request.user)
    timer = timers.filter(last_used_at__isnull=False).order_by("-last_used_at", "-pk").first()
    if timer is None:
        timer = timers.order_by("-created_at", "-pk").first()
    if timer is None:
        messages.info(request, "Create a timer setup to get started.")
        return redirect("timers:create")
    return redirect("timers:run", pk=timer.pk)


class TimerListView(LoginRequiredMixin, ListView):
    model = Timer
    template_name = "timerapp/timer_list.html"
    context_object_name = "timers"

    def get_queryset(self):
        return Timer.objects.filter(user=self.request.user).order_by("-created_at")


class TimerCreateView(LoginRequiredMixin, CreateView):
    model = Timer
    form_class = TimerForm
    template_name = "timerapp/timer_form.html"
    success_url = reverse_lazy("timers:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("timers:run", args=[self.object.pk])


class TimerUpdateView(LoginRequiredMixin, UpdateView):
    model = Timer
    form_class = TimerForm
    template_name = "timerapp/timer_form.html"
    success_url = reverse_lazy("timers:list")

    def get_queryset(self):
        return Timer.objects.filter(user=self.request.user)


class TimerDeleteView(LoginRequiredMixin, DeleteView):
    model = Timer
    template_name = "timerapp/timer_confirm_delete.html"
    success_url = reverse_lazy("timers:list")

    def get_queryset(self):
        return Timer.objects.filter(user=self.request.user)


class TimerRunView(LoginRequiredMixin, DetailView):
    model = Timer
    template_name = "timerapp/timer_run.html"
    context_object_name = "timer"

    def get_queryset(self):
        return Timer.objects.filter(user=self.request.user)

    def get_object(self, queryset=None):
        timer = super().get_object(queryset)
        Timer.objects.filter(pk=timer.pk).update(last_used_at=timezone.now())
        timer.sync_state()
        return timer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["spotify_configured"] = spotify_client.is_configured()
        context["available_timers"] = Timer.objects.filter(user=self.request.user).order_by("name", "pk")
        return context


@login_required
@require_GET
def active_timer_state(request):
    timer = Timer.objects.filter(user=request.user, status__in=["RUNNING", "PAUSED"]).order_by("pk").first()
    if timer is None:
        return JsonResponse({"active": False})
    timer.sync_state()
    return JsonResponse(dict(timer.to_dict(), active=True))


@login_required
@require_GET
def timer_state(request, pk):
    timer = get_object_or_404(Timer, pk=pk, user=request.user)
    timer.sync_state()
    return JsonResponse(timer.to_dict())


@login_required
@require_POST
def timer_action(request, pk):
    timer = get_object_or_404(Timer, pk=pk, user=request.user)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        data = request.POST
    if not hasattr(data, "get"):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    action = data.get("action")
    if action not in ("start", "pause", "reset", "complete"):
        return JsonResponse({"error": "Invalid or missing action."}, status=400)

    if action == "complete":
        if timer.status == "READY":
            return JsonResponse(timer.to_dict())
        if timer.get_current_timer_state()[0] != "DONE":
            return JsonResponse({"error": "This workout has not finished."}, status=409)
        action = "reset"
        data = dict(data, confirmed_reset=True)

    if action == "start":
        other_timers = list(
            Timer.objects.filter(user=request.user, status__in=["RUNNING", "PAUSED"])
            .exclude(pk=timer.pk)
            .order_by("pk")
        )
        other_ids = [other.pk for other in other_timers]
        if other_ids and data.get("confirmed_reset_timer_ids") != other_ids:
            return JsonResponse({
                "confirmation_required": True,
                "message": "Starting this timer will reset these active timers and erase their progress: "
                           + ", ".join(other.name for other in other_timers) + ". Continue?",
                "confirmation": {"confirmed_reset_timer_ids": other_ids},
            }, status=409)
        for other in other_timers:
            other.status = "READY"
            other.time_remaining = other.duration
            other.current_round = 1
            other.current_state = "WORK"
            other.last_started_at = None
            other.save(update_fields=[
                "status", "time_remaining", "current_round", "current_state", "last_started_at"
            ])

        if timer.status in ("READY", "DONE"):
            timer.status = "RUNNING"
            timer.current_round = 1
            timer.current_state = "WORK"
            timer.time_remaining = timer.duration
            timer.last_started_at = timezone.now()
        elif timer.status == "PAUSED":
            timer.status = "RUNNING"
            timer.last_started_at = timezone.now()

    elif action == "pause":
        timer.sync_state(save=False)
        if timer.status == "RUNNING":
            _, _, _, remaining = timer.get_current_timer_state()
            timer.status = "PAUSED"
            timer.time_remaining = remaining
            timer.last_started_at = None

    elif action == "reset":
        if timer.status in ("RUNNING", "PAUSED") and data.get("confirmed_reset") is not True:
            return JsonResponse({
                "confirmation_required": True,
                "message": "Reset this timer? Current workout progress will be lost.",
                "confirmation": {"confirmed_reset": True},
            }, status=409)
        timer.status = "READY"
        timer.current_round = 1
        timer.current_state = "WORK"
        timer.time_remaining = timer.duration
        timer.last_started_at = None

    timer.save(update_fields=["status", "current_round", "current_state", "time_remaining", "last_started_at"])
    return JsonResponse(timer.to_dict())


@login_required
def spotify_connect(request):
    if not spotify_client.is_configured():
        messages.error(request, "Spotify integration is not configured. Contact an administrator.")
        return redirect("timers:list")
    state = secrets.token_urlsafe(24)
    request.session["spotify_oauth_state"] = state
    next_url = request.GET.get("next", "")
    request.session["spotify_return_to"] = (
        next_url if url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ) else reverse("timers:list")
    )
    return redirect(spotify_client.build_authorize_url(state))


@login_required
def spotify_callback(request):
    return_to = request.session.pop("spotify_return_to", None) or reverse("timers:list")
    expected_state = request.session.pop("spotify_oauth_state", None)
    if request.GET.get("error"):
        messages.error(request, "Spotify authorization was cancelled.")
        return redirect(return_to)
    if not request.GET.get("code") or request.GET.get("state") != expected_state:
        messages.error(request, "Spotify authorization failed verification. Please try again.")
        return redirect(return_to)

    try:
        tokens = spotify_client.exchange_code_for_tokens(request.GET["code"])
        account, _ = SpotifyAccount.objects.get_or_create(
            user=request.user,
            defaults={"access_token": "", "refresh_token": "", "expires_at": timezone.now()},
        )
        account.access_token = tokens["access_token"]
        account.refresh_token = tokens.get("refresh_token") or account.refresh_token
        account.expires_at = timezone.now() + timezone.timedelta(seconds=tokens.get("expires_in", 3600))
        profile = spotify_client.get_current_user(account)
        account.spotify_user_id = profile.get("id", "")
        account.display_name = profile.get("display_name") or profile.get("id", "")
        account.save()
        messages.success(request, f"Connected to Spotify as {account.display_name}.")
    except Exception as exc:
        messages.error(request, f"Could not connect to Spotify: {exc}")
    return redirect(return_to)


@login_required
@require_POST
def spotify_disconnect(request):
    SpotifyAccount.objects.filter(user=request.user).delete()
    messages.success(request, "Disconnected your Spotify account.")
    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = reverse_lazy("timers:list")
    return redirect(next_url)


@login_required
def spotify_status(request):
    account = SpotifyAccount.objects.filter(user=request.user).first()
    return JsonResponse({
        "connected": bool(account),
        "configured": spotify_client.is_configured(),
        "display_name": account.display_name if account else "",
        "last_playlist_uri": account.last_playlist_uri if account else "",
        "last_device_id": account.last_device_id if account else "",
    })


@login_required
def spotify_playlists(request):
    account = SpotifyAccount.objects.filter(user=request.user).first()
    if account is None:
        return JsonResponse({"error": "Spotify account not connected."}, status=400)
    try:
        return JsonResponse({"playlists": spotify_client.get_playlists(account)})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@login_required
def spotify_devices(request):
    account = SpotifyAccount.objects.filter(user=request.user).first()
    if account is None:
        return JsonResponse({"error": "Spotify account not connected."}, status=400)
    try:
        return JsonResponse({"devices": spotify_client.get_devices(account)})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@login_required
@require_POST
def spotify_control(request):
    account = SpotifyAccount.objects.filter(user=request.user).first()
    if account is None:
        return JsonResponse({"error": "Spotify account not connected."}, status=400)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        data = request.POST
    if not hasattr(data, "get"):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    action = data.get("action")
    if action not in ("play", "resume", "pause", "stop", "next", "previous", "shuffle", "repeat", "seek", "volume"):
        return JsonResponse({"error": "Invalid or missing action."}, status=400)
    if action == "shuffle" and not isinstance(data.get("state"), bool):
        return JsonResponse({"error": "Shuffle state must be a boolean."}, status=400)
    if action == "repeat" and data.get("state") not in ("off", "context", "track"):
        return JsonResponse({"error": "Invalid repeat mode."}, status=400)
    if action == "seek":
        position = data.get("position_ms")
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            return JsonResponse({"error": "Seek position must be a nonnegative integer."}, status=400)
    if action == "volume":
        volume = data.get("volume_percent")
        if type(volume) is not int or not 0 <= volume <= 100:
            return JsonResponse({"error": "Volume must be an integer between 0 and 100."}, status=400)

    playlist_uri = data.get("playlist_uri")
    device_id = data.get("device_id")
    if playlist_uri:
        account.last_playlist_uri = playlist_uri
    if device_id:
        account.last_device_id = device_id
    if playlist_uri or device_id:
        account.save(update_fields=["last_playlist_uri", "last_device_id", "updated_at"])
    device_id = device_id or account.last_device_id or None

    try:
        if action == "play":
            spotify_client.start_playback(
                account, playlist_uri=playlist_uri or account.last_playlist_uri, device_id=device_id
            )
        elif action == "resume":
            spotify_client.start_playback(account, device_id=device_id)
        elif action in ("pause", "stop"):
            spotify_client.pause_playback(account, device_id=device_id)
        elif action == "next":
            spotify_client.next_track(account, device_id=device_id)
        elif action == "previous":
            spotify_client.previous_track(account, device_id=device_id)
        elif action == "shuffle":
            spotify_client.set_shuffle(account, data["state"], device_id=device_id)
        elif action == "repeat":
            spotify_client.set_repeat(account, data["state"], device_id=device_id)
        elif action == "seek":
            spotify_client.seek_playback(account, data["position_ms"], device_id=device_id)
        elif action == "volume":
            spotify_client.set_volume(account, data["volume_percent"], device_id=device_id)
    except spotify_client.SpotifyPlaybackError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"status": "ok", "action": action})


@login_required
def spotify_playback_state(request):
    account = SpotifyAccount.objects.filter(user=request.user).first()
    if account is None:
        return JsonResponse({"error": "Spotify account not connected."}, status=400)
    try:
        return JsonResponse(spotify_client.get_playback_state(account))
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)
