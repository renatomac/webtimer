import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import TimerForm
from .models import Timer


class TimerFormTests(TestCase):
    def test_duration_and_interval_are_parsed(self):
        form = TimerForm(data={
            "name": "Sparring",
            "rounds": "3",
            "duration_str": "2:30",
            "interval_str": "1:15",
            "direction": "UP",
        })
        self.assertTrue(form.is_valid(), form.errors)
        timer = form.save(commit=False)
        self.assertEqual((timer.duration, timer.interval), (150, 75))

    def test_rejects_invalid_time_and_zero_duration(self):
        data = {
            "name": "Sparring",
            "rounds": "3",
            "duration_str": "0:00",
            "interval_str": "1:60",
            "direction": "DOWN",
        }
        form = TimerForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("duration_str", form.errors)
        self.assertIn("interval_str", form.errors)

    def test_round_count_must_be_positive(self):
        form = TimerForm(data={
            "name": "Sparring",
            "rounds": "0",
            "duration_str": "1:00",
            "interval_str": "0:00",
            "direction": "DOWN",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("rounds", form.errors)


class TimerWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="timer-owner", password="test-pass-123")
        self.client.force_login(self.user)
        self.timer = Timer.objects.create(
            user=self.user, name="Sparring", rounds=2, duration=10, interval=5,
        )

    def action(self, timer=None, **data):
        return self.client.post(
            reverse("timers:action", args=[(timer or self.timer).pk]),
            json.dumps(data),
            content_type="application/json",
        )

    def test_library_and_run_page_render(self):
        self.assertRedirects(self.client.get("/"), reverse("timers:list"))
        self.assertEqual(self.client.get(reverse("timers:list")).status_code, 200)
        response = self.client.get(reverse("timers:run", args=[self.timer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "spotifyPanel")
        self.assertContains(response, "const CUSTOM_APP_ID = '480DA752';")
        self.assertContains(response, "Spotify controls are unavailable")

    def test_cast_receiver_renders(self):
        response = self.client.get(reverse("cast_receiver"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "receiver-logo")
        self.assertContains(response, "12:00:00 AM")
        self.assertIn("no-store", response.headers["Cache-Control"])

    @override_settings(
        SPOTIFY_CLIENT_ID="test-id",
        SPOTIFY_CLIENT_SECRET="test-secret",
        SPOTIFY_REDIRECT_URI="https://example.com/timers/spotify/callback/",
    )
    def test_configured_spotify_controls_render(self):
        response = self.client.get(reverse("timers:run", args=[self.timer.pk]))
        self.assertContains(response, "btnSpotifyPlay")
        self.assertContains(response, "spotifyPlaylistSelect")

    def test_timer_action_lifecycle(self):
        self.assertEqual(self.action(action="start").status_code, 200)
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.status, "RUNNING")

        self.assertEqual(self.action(action="pause").status_code, 200)
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.status, "PAUSED")

        self.assertEqual(self.action(action="start").status_code, 200)
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.status, "RUNNING")

        self.assertEqual(self.action(action="reset", confirmed_reset=True).status_code, 200)
        self.timer.refresh_from_db()
        self.assertEqual((self.timer.status, self.timer.current_round, self.timer.time_remaining),
                         ("READY", 1, self.timer.duration))

    def test_reset_requires_confirmation_while_active(self):
        self.action(action="start")
        response = self.action(action="reset")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["confirmation_required"])
        self.assertEqual(self.action(action="reset", confirmed_reset=True).status_code, 200)

    def test_second_active_timer_requires_explicit_reset_confirmation(self):
        other = Timer.objects.create(user=self.user, name="Technique")
        self.action(action="start")
        response = self.action(timer=other, action="start")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["confirmation"]["confirmed_reset_timer_ids"], [self.timer.pk])

        response = self.action(timer=other, action="start", confirmed_reset_timer_ids=[self.timer.pk])
        self.assertEqual(response.status_code, 200)
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.status, "READY")

    def test_state_and_timer_data_are_private(self):
        other_user = get_user_model().objects.create_user(username="other-timer-owner")
        other_timer = Timer.objects.create(user=other_user, name="Private timer")
        self.assertEqual(self.client.get(reverse("timers:run", args=[other_timer.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("timers:state", args=[other_timer.pk])).status_code, 404)
        self.assertEqual(self.action(timer=other_timer, action="start").status_code, 404)
        response = self.client.get(reverse("timers:list"))
        self.assertContains(response, self.timer.name)
        self.assertNotContains(response, other_timer.name)

    def test_state_sync_advances_into_rest(self):
        self.timer.status = "RUNNING"
        self.timer.last_started_at = timezone.now() - timedelta(seconds=11)
        self.timer.save(update_fields=["status", "last_started_at"])
        response = self.client.get(reverse("timers:state", args=[self.timer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_state"], "REST")
        self.assertEqual(response.json()["current_round"], 1)
        self.assertEqual(response.json()["time_remaining"], 5)
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.get_current_timer_state()[3], 4)
