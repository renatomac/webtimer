"""Thin wrapper around the Spotify Web API used for the timer's playback controls."""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE_URL = "https://api.spotify.com/v1"

# Scopes needed to read the user's playlists, see their devices, and control playback.
SCOPES = " ".join([
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
])


def is_configured() -> bool:
    return bool(
        settings.SPOTIFY_CLIENT_ID
        and settings.SPOTIFY_CLIENT_SECRET
        and settings.SPOTIFY_REDIRECT_URI
    )


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _basic_auth_header() -> Dict[str, str]:
    creds = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    return {"Authorization": f"Basic {base64.b64encode(creds).decode('utf-8')}"}


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
        },
        headers=_basic_auth_header(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers=_basic_auth_header(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def ensure_valid_token(account) -> str:
    """Return a valid access token for the account, refreshing it if expired."""
    if account.is_expired:
        data = refresh_access_token(account.refresh_token)
        account.access_token = data["access_token"]
        # Spotify only returns a new refresh_token sometimes; keep the old one otherwise.
        if data.get("refresh_token"):
            account.refresh_token = data["refresh_token"]
        account.expires_at = timezone.now() + timezone.timedelta(seconds=data.get("expires_in", 3600))
        account.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
    return account.access_token


def _auth_headers(account) -> Dict[str, str]:
    token = ensure_valid_token(account)
    return {"Authorization": f"Bearer {token}"}


def get_current_user(account) -> Dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}/me", headers=_auth_headers(account), timeout=15)
    response.raise_for_status()
    return response.json()


def get_playlists(account) -> List[Dict[str, Any]]:
    playlists = []
    url = f"{API_BASE_URL}/me/playlists?limit=50"
    headers = _auth_headers(account)
    while url:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        body = response.json()
        for item in body.get("items", []):
            playlists.append({
                "uri": item.get("uri"),
                "name": item.get("name"),
                "image_url": (item.get("images") or [{}])[0].get("url"),
                "tracks_total": (item.get("tracks") or {}).get("total"),
            })
        url = body.get("next")
    return playlists


def get_devices(account) -> List[Dict[str, Any]]:
    response = requests.get(f"{API_BASE_URL}/me/player/devices", headers=_auth_headers(account), timeout=15)
    response.raise_for_status()
    return response.json().get("devices", [])


def start_playback(account, playlist_uri: Optional[str] = None, device_id: Optional[str] = None) -> None:
    params = {"device_id": device_id} if device_id else {}
    payload: Dict[str, Any] = {}
    if playlist_uri:
        payload["context_uri"] = playlist_uri
    response = requests.put(
        f"{API_BASE_URL}/me/player/play",
        params=params,
        json=payload,
        headers=_auth_headers(account),
        timeout=15,
    )
    _raise_for_playback_error(response)


def pause_playback(account, device_id: Optional[str] = None) -> None:
    params = {"device_id": device_id} if device_id else {}
    response = requests.put(
        f"{API_BASE_URL}/me/player/pause",
        params=params,
        headers=_auth_headers(account),
        timeout=15,
    )
    _raise_for_playback_error(response)


def next_track(account, device_id: Optional[str] = None) -> None:
    params = {"device_id": device_id} if device_id else {}
    response = requests.post(
        f"{API_BASE_URL}/me/player/next",
        params=params,
        headers=_auth_headers(account),
        timeout=15,
    )
    _raise_for_playback_error(response)


def previous_track(account, device_id: Optional[str] = None) -> None:
    params = {"device_id": device_id} if device_id else {}
    response = requests.post(
        f"{API_BASE_URL}/me/player/previous",
        params=params,
        headers=_auth_headers(account),
        timeout=15,
    )
    _raise_for_playback_error(response)


def _raise_for_playback_error(response: requests.Response) -> None:
    if response.status_code == 204 or response.ok:
        return
    if response.status_code == 404:
        raise SpotifyPlaybackError("No active Spotify device found. Open Spotify on a device and try again.")
    if response.status_code == 403:
        raise SpotifyPlaybackError("Playback control requires a Spotify Premium account.")
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except ValueError:
        detail = response.text
    raise SpotifyPlaybackError(f"Spotify request failed: {detail}")


class SpotifyPlaybackError(Exception):
    pass


def get_playback_state(account) -> Dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}/me/player", headers=_auth_headers(account), timeout=15)
    response.raise_for_status()
    if response.status_code == 204:
        return {"active": False}
    body = response.json()
    item = body.get("item") or {}
    device = body.get("device") or {}
    return {
        "active": bool(item), "is_playing": body.get("is_playing", False),
        "progress_ms": body.get("progress_ms") or 0,
        "duration_ms": item.get("duration_ms") or 0,
        "track_name": item.get("name", ""),
        "artists": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "shuffle_state": body.get("shuffle_state", False),
        "repeat_state": body.get("repeat_state", "off"),
        "context_uri": (body.get("context") or {}).get("uri"),
        "device_id": device.get("id"),
        "volume_percent": device.get("volume_percent"),
        "supports_volume": device.get("supports_volume", False) and not device.get("is_restricted", False),
        "disallows": (body.get("actions") or {}).get("disallows", {}),
    }


def set_shuffle(account, state: bool, device_id: Optional[str] = None) -> None:
    params = {"state": str(state).lower()}
    if device_id:
        params["device_id"] = device_id
    response = requests.put(f"{API_BASE_URL}/me/player/shuffle", params=params,
                            headers=_auth_headers(account), timeout=15)
    _raise_for_playback_error(response)


def set_repeat(account, state: str, device_id: Optional[str] = None) -> None:
    params = {"state": state}
    if device_id:
        params["device_id"] = device_id
    response = requests.put(f"{API_BASE_URL}/me/player/repeat", params=params,
                            headers=_auth_headers(account), timeout=15)
    _raise_for_playback_error(response)


def seek_playback(account, position_ms: int, device_id: Optional[str] = None) -> None:
    params = {"position_ms": position_ms}
    if device_id:
        params["device_id"] = device_id
    response = requests.put(f"{API_BASE_URL}/me/player/seek", params=params,
                            headers=_auth_headers(account), timeout=15)
    _raise_for_playback_error(response)


def set_volume(account, volume_percent: int, device_id: Optional[str] = None) -> None:
    params = {"volume_percent": volume_percent}
    if device_id:
        params["device_id"] = device_id
    response = requests.put(f"{API_BASE_URL}/me/player/volume", params=params,
                            headers=_auth_headers(account), timeout=15)
    _raise_for_playback_error(response)
