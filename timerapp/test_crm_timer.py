import json
from datetime import timedelta
from unittest.mock import patch

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
    def test_polling_preserves_fractional_time_and_phase_anchor(self):
        started = timezone.now()
        self.timer.status = "RUNNING"
        self.timer.last_started_at = started
        self.timer.save(update_fields=["status", "last_started_at"])
        for elapsed in (1.2, 2.7, 4.1, 9.9):
            with patch("django.utils.timezone.now", return_value=started + timedelta(seconds=elapsed)):
                self.timer.sync_state()
                self.timer.refresh_from_db()
                self.assertEqual(self.timer.last_started_at, started)
                self.assertEqual(self.timer.get_current_timer_state()[3], 10 - int(elapsed))
        with patch("django.utils.timezone.now", return_value=started + timedelta(seconds=11.7)):
            self.timer.sync_state()
            self.timer.refresh_from_db()
            self.assertEqual(self.timer.last_started_at, started + timedelta(seconds=10))
            self.assertEqual(self.timer.get_current_timer_state()[3], 4)
        with patch("django.utils.timezone.now", return_value=started + timedelta(seconds=15.1)):
            self.timer.sync_state()
            self.assertEqual(self.timer.last_started_at, started + timedelta(seconds=15))
            self.assertEqual(self.timer.current_round, 2)

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

    @override_settings(SPOTIFY_CLIENT_ID="", SPOTIFY_CLIENT_SECRET="")
    def test_library_and_run_page_render(self):
        self.assertRedirects(self.client.get("/"), reverse("timers:home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("timers:list")).status_code, 200)
        response = self.client.get(reverse("timers:run", args=[self.timer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "spotifyPanel")
        self.assertContains(response, "const CUSTOM_APP_ID = '480DA752';")
        self.assertContains(response, "Spotify controls are unavailable")

    def test_tv_link_opens_private_timer_display(self):
        display_url = reverse("timers:display", args=[self.timer.pk])
        response = self.client.get(reverse("timers:run", args=[self.timer.pk]))
        self.assertContains(response, f'href="{display_url}"')
        response = self.client.get(display_url)
        self.assertTemplateUsed(response, "timerapp/timer_display.html")
        self.assertContains(response, reverse("timers:state", args=[self.timer.pk]))
        self.assertNotContains(response, reverse("timers:active_state"))
        self.assertContains(response, reverse("timers:ably_token"))
        self.assertContains(response, "ably.min-2.js")
        other = get_user_model().objects.create_user(username="display-other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(display_url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(display_url).status_code, 302)

    def test_tv_display_stays_on_selected_ready_timer_when_another_is_running(self):
        other = Timer.objects.create(user=self.user, name="Other workout")
        self.action(timer=other, action="start")
        response = self.client.get(reverse("timers:display", args=[self.timer.pk]))
        self.assertContains(response, f"const timerId = {self.timer.pk};")
        self.assertContains(response, reverse("timers:state", args=[self.timer.pk]))
        self.assertNotContains(response, reverse("timers:state", args=[other.pk]))
        snapshot = self.client.get(reverse("timers:state", args=[self.timer.pk])).json()
        self.assertEqual(snapshot["id"], self.timer.pk)
        self.assertEqual(snapshot["status"], "READY")
        self.assertEqual(snapshot["time_remaining"], self.timer.duration)

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

class TimerLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="returning", password="test-pass-123")
        self.client.force_login(self.user)

    def test_empty_account_prompts_for_setup(self):
        response = self.client.get(reverse("timers:home"), follow=True)
        self.assertContains(response, "Create a timer setup to get started.")
        self.assertEqual(response.resolver_match.url_name, "create")

    def test_last_selected_timer_survives_logout(self):
        first = Timer.objects.create(user=self.user, name="First")
        Timer.objects.create(user=self.user, name="Newer")
        self.client.get(reverse("timers:run", args=[first.pk]))
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "returning", "password": "test-pass-123"})
        self.assertRedirects(response, reverse("timers:home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("timers:home")), reverse("timers:run", args=[first.pk]))

    def test_fallback_ignores_other_users_and_deleted_timers(self):
        timer = Timer.objects.create(user=self.user, name="Mine")
        other = get_user_model().objects.create_user(username="other")
        Timer.objects.create(user=other, name="Other", last_used_at=timezone.now())
        self.assertRedirects(self.client.get(reverse("timers:home")), reverse("timers:run", args=[timer.pk]))
        timer.delete()
        self.assertRedirects(self.client.get(reverse("timers:home")), reverse("timers:create"))
