import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Timer
from .realtime import publish_timer_update


@override_settings(ABLY_API_KEY="app.key:test-secret")
class RealtimeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="realtime-owner")
        self.client.force_login(self.user)

    def test_token_is_signed_private_and_subscribe_only(self):
        response = self.client.get(reverse("timers:ably_token"), {"clientId": "other", "capability": "*"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clientId"], str(self.user.pk))
        self.assertEqual(json.loads(data["capability"]), {f"user-{self.user.pk}-timer": ["subscribe"]})
        self.assertEqual(data["ttl"], 3600000)
        canonical = "".join(f"{data[field]}\n" for field in (
            "keyName", "ttl", "capability", "clientId", "timestamp", "nonce"
        ))
        expected = base64.b64encode(hmac.new(b"test-secret", canonical.encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(data["mac"], expected)
        self.assertNotContains(response, "test-secret")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertNotEqual(data["nonce"], self.client.get(reverse("timers:ably_token")).json()["nonce"])
        self.client.logout()
        self.assertEqual(self.client.get(reverse("timers:ably_token")).status_code, 302)

    @override_settings(ABLY_API_KEY="")
    def test_missing_key_returns_service_unavailable(self):
        self.assertEqual(self.client.get(reverse("timers:ably_token")).status_code, 503)

    def test_action_clock_timestamps_exclude_slow_publish(self):
        timer = Timer.objects.create(user=self.user, name="Slow publish")
        started = timezone.now()
        clock = [started]

        def slow_publish(*args):
            clock[0] += timedelta(seconds=3)

        with patch("django.utils.timezone.now", side_effect=lambda: clock[0]):
            with patch("timerapp.timer_views.transaction.on_commit", side_effect=lambda fn: fn()):
                with patch("timerapp.realtime.publish_timer_update", side_effect=slow_publish):
                    response = self.client.post(reverse("timers:action", args=[timer.pk]), '{"action":"start"}', content_type="application/json")
        data = response.json()
        self.assertEqual(data["server_received_at"], started.isoformat())
        self.assertEqual(data["server_time"], (started + timedelta(seconds=3)).isoformat())
        self.assertEqual(data["last_started_at"], started.isoformat())

    @patch("timerapp.realtime.requests.post")
    def test_actions_publish_after_commit_and_rejections_do_not(self, post):
        timer = Timer.objects.create(user=self.user, name="Test", duration=10)
        url = reverse("timers:action", args=[timer.pk])
        for action in ("start", "pause", "reset"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, json.dumps({"action": action, "confirmed_reset": True}), content_type="application/json")
                self.assertEqual(response.status_code, 200)
            published = post.call_args.kwargs["json"]["data"]
            self.assertEqual(published["status"], response.json()["status"])
            self.assertEqual(published["last_started_at"], response.json()["last_started_at"])
            self.assertEqual(post.call_args.kwargs["auth"], ("app.key", "test-secret"))
        self.assertEqual(post.call_count, 3)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, '{"action":"invalid"}', content_type="application/json")
        self.assertEqual(post.call_count, 3)

    @patch("timerapp.realtime.requests.post", side_effect=requests.Timeout)
    def test_publish_failure_does_not_break_action(self, post):
        timer = Timer.objects.create(user=self.user, name="Test")
        with self.assertLogs("timerapp.realtime", level="WARNING"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("timers:action", args=[timer.pk]), '{"action":"start"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        timer.refresh_from_db()
        self.assertEqual(timer.status, "RUNNING")

    @override_settings(ABLY_API_KEY="")
    @patch("timerapp.realtime.requests.post")
    def test_unconfigured_publish_skips_network(self, post):
        publish_timer_update(self.user.pk, {})
        post.assert_not_called()
