from django.urls import path

from . import timer_views

app_name = "timers"

urlpatterns = [
    path("", timer_views.TimerListView.as_view(), name="list"),
    path("create/", timer_views.TimerCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", timer_views.TimerUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", timer_views.TimerDeleteView.as_view(), name="delete"),
    path("<int:pk>/run/", timer_views.TimerRunView.as_view(), name="run"),
    path("active-state/", timer_views.active_timer_state, name="active_state"),
    path("<int:pk>/state/", timer_views.timer_state, name="state"),
    path("<int:pk>/action/", timer_views.timer_action, name="action"),
    path("spotify/connect/", timer_views.spotify_connect, name="spotify_connect"),
    path("spotify/callback/", timer_views.spotify_callback, name="spotify_callback"),
    path("spotify/disconnect/", timer_views.spotify_disconnect, name="spotify_disconnect"),
    path("spotify/status/", timer_views.spotify_status, name="spotify_status"),
    path("spotify/playlists/", timer_views.spotify_playlists, name="spotify_playlists"),
    path("spotify/devices/", timer_views.spotify_devices, name="spotify_devices"),
    path("spotify/playback-state/", timer_views.spotify_playback_state, name="spotify_playback_state"),
    path("spotify/control/", timer_views.spotify_control, name="spotify_control"),
]
