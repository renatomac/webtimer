from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("d/<str:token>/", views.display, name="display"),
    path("d/<str:token>/state/", views.display_state, name="display_state"),
    path("s/<slug:slug>/", views.control, name="control"),
    path("s/<slug:slug>/state/", views.state, name="state"),
    path("s/<slug:slug>/command/<str:name>/", views.command, name="command"),
    path("s/<slug:slug>/select/", views.select_preset, name="select_preset"),
    path("s/<slug:slug>/display-link/regenerate/", views.regenerate_link, name="regenerate_link"),
    path("s/<slug:slug>/presets/", views.preset_list, name="preset_list"),
    path("s/<slug:slug>/presets/new/", views.preset_edit, name="preset_new"),
    path("s/<slug:slug>/presets/<int:pk>/edit/", views.preset_edit, name="preset_edit"),
    path("s/<slug:slug>/presets/<int:pk>/delete/", views.preset_delete, name="preset_delete"),
    path("s/<slug:slug>/spotify/connect/", views.spotify_connect, name="spotify_connect"),
    path("spotify/callback/", views.spotify_callback, name="spotify_callback"),
    path("s/<slug:slug>/spotify/disconnect/", views.spotify_disconnect, name="spotify_disconnect"),
    path("s/<slug:slug>/spotify/status/", views.spotify_status, name="spotify_status"),
    path("s/<slug:slug>/spotify/<str:kind>/", views.spotify_data, name="spotify_data"),
    path("s/<slug:slug>/spotify/control/", views.spotify_control, name="spotify_control"),
]
