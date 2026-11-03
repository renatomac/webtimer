import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import engine, services
from .forms import PresetForm
from .models import Preset, Studio, StudioMembership, TimerSession

PW = "test-pass-123"
T0 = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)


def at(seconds):
    return mock.patch.object(services, "now", return_value=T0 + datetime.timedelta(seconds=seconds))


def make_studio(slug="alpha", **preset_kwargs):
    studio = Studio.objects.create(name=slug.title(), slug=slug)
    kwargs = dict(name="Std", rounds=3, round_seconds=10, rest_seconds=5, direction="down")
    kwargs.update(preset_kwargs)
    preset = Preset.objects.create(studio=studio, **kwargs)
    return studio, preset


def select(studio, preset):
    services.select_preset(studio, preset)


class EngineTests(TestCase):
    def test_rest_only_between_rounds(self):
        phases = engine.build_phases(3, 10, 5)
        self.assertEqual([p[0] for p in phases], ["rolling", "rest", "rolling", "rest", "rolling"])
        self.assertEqual(engine.total_ms(phases), 40000)

    def test_zero_rest_skips_rests(self):
        phases = engine.build_phases(3, 10, 0)
        self.assertEqual([p[0] for p in phases], ["rolling"] * 3)
        self.assertEqual(engine.total_ms(phases), 30000)

    def test_locate_boundaries(self):
        phases = engine.build_phases(2, 10, 5)
        self.assertEqual(engine.locate(phases, 9999), (0, 9999, False))
        self.assertEqual(engine.locate(phases, 10000), (1, 0, False))
        self.assertEqual(engine.locate(phases, 15000), (2, 0, False))
        self.assertEqual(engine.locate(phases, 25000), (2, 10000, True))

    def test_count_directions(self):
        self.assertEqual(engine.displayed_seconds("down", 10000, 0), 10)
        self.assertEqual(engine.displayed_seconds("down", 10000, 10000), 0)
        self.assertEqual(engine.displayed_seconds("down", 10000, 500), 10)
        self.assertEqual(engine.displayed_seconds("up", 10000, 0), 0)
        self.assertEqual(engine.displayed_seconds("up", 10000, 10000), 10)


class TransitionTests(TestCase):
    def setUp(self):
        self.studio, self.preset = make_studio()
        select(self.studio, self.preset)

    def cmd(self, name, t):
        with at(t):
            return services.apply_command(self.studio, name)

    def test_full_lifecycle(self):
        self.assertEqual(services.snapshot(self.studio)["state"], "ready")
        s = self.cmd("start", 0)
        self.assertEqual(s["state"], "running")
        with at(4):
            self.assertEqual(services.snapshot(self.studio)["elapsed_ms"], 4000)
        s = self.cmd("pause", 4)
        self.assertEqual((s["state"], s["elapsed_ms"]), ("paused", 4000))
        with at(100):
            self.assertEqual(services.snapshot(self.studio)["elapsed_ms"], 4000)
        s = self.cmd("resume", 100)
        with at(103):
            self.assertEqual(services.snapshot(self.studio)["elapsed_ms"], 7000)
        s = self.cmd("stop", 103)
        self.assertEqual((s["state"], s["elapsed_ms"]), ("stopped", 7000))
        s = self.cmd("reset", 110)
        self.assertEqual((s["state"], s["elapsed_ms"]), ("ready", 0))

    def test_invalid_commands(self):
        for name in ("pause", "resume", "stop", "reset"):
            with self.assertRaises(services.InvalidCommand):
                self.cmd(name, 0)
        self.cmd("start", 0)
        for name in ("start", "resume"):
            with self.assertRaises(services.InvalidCommand):
                self.cmd(name, 1)
        self.cmd("pause", 1)
        for name in ("start", "pause"):
            with self.assertRaises(services.InvalidCommand):
                self.cmd(name, 2)
        with self.assertRaises(services.InvalidCommand):
            self.cmd("explode", 2)

    def test_start_restarts_at_round_one_after_stop(self):
        self.cmd("start", 0)
        self.cmd("stop", 25)
        s = self.cmd("start", 30)
        self.assertEqual(s["elapsed_ms"], 0)

    def test_final_round_completion_without_rest(self):
        self.cmd("start", 0)
        with at(39):
            self.assertEqual(services.snapshot(self.studio)["state"], "running")
        with at(40):
            s = services.snapshot(self.studio)
        self.assertEqual((s["state"], s["elapsed_ms"]), ("finished", 40000))
        with at(500):
            self.assertEqual(services.snapshot(self.studio)["elapsed_ms"], 40000)
        with at(500), self.assertRaises(services.InvalidCommand):
            services.apply_command(self.studio, "pause")
        self.assertEqual(self.cmd("reset", 501)["state"], "ready")

    def test_zero_rest_preset_finishes_after_last_round(self):
        p = Preset.objects.create(studio=self.studio, name="NoRest", rounds=2, round_seconds=10,
                                  rest_seconds=0, direction="up")
        select(self.studio, p)
        s = self.cmd("start", 0)
        self.assertEqual([ph[0] for ph in s["phases"]], ["rolling", "rolling"])
        with at(20):
            self.assertEqual(services.snapshot(self.studio)["state"], "finished")

    def test_count_direction_in_payload(self):
        up = Preset.objects.create(studio=self.studio, name="Up", rounds=1, round_seconds=5,
                                   rest_seconds=0, direction="up")
        select(self.studio, up)
        self.assertEqual(services.snapshot(self.studio)["preset"]["direction"], "up")
        select(self.studio, self.preset)
        self.assertEqual(services.snapshot(self.studio)["preset"]["direction"], "down")

    def test_snapshot_isolates_edits(self):
        self.cmd("start", 0)
        self.preset.rounds = 1
        self.preset.save()
        with at(5):
            self.assertEqual(services.snapshot(self.studio)["preset"]["rounds"], 3)
        self.cmd("stop", 5)
        self.cmd("start", 6)
        with at(6):
            self.assertEqual(services.snapshot(self.studio)["preset"]["rounds"], 1)

    def test_cannot_change_preset_while_running(self):
        self.cmd("start", 0)
        with at(1), self.assertRaises(services.InvalidCommand):
            select(self.studio, self.preset)

    def test_start_without_preset(self):
        studio = Studio.objects.create(name="Empty", slug="empty")
        with self.assertRaises(services.InvalidCommand):
            services.apply_command(studio, "start")

    def test_refresh_recovers_state(self):
        self.cmd("start", 0)
        with at(12):
            a = services.snapshot(self.studio)
        with at(12):
            b = services.snapshot(self.studio)
        self.assertEqual(a["elapsed_ms"], 12000)
        self.assertEqual(a["run"], b["run"])
        idx, pe, fin = engine.locate([tuple(p) for p in a["phases"]], a["elapsed_ms"])
        self.assertEqual((a["phases"][idx][0], pe), ("rest", 2000))


class ViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.a, self.pa = make_studio("alpha")
        self.b, self.pb = make_studio("beta")
        self.ua = User.objects.create_user("ua", password=PW)
        self.ub = User.objects.create_user("ub", password=PW)
        StudioMembership.objects.create(user=self.ua, studio=self.a)
        StudioMembership.objects.create(user=self.ub, studio=self.b)
        self.client.login(username="ua", password=PW)

    def test_login_required(self):
        self.client.logout()
        for url in (reverse("control", args=["alpha"]), reverse("state", args=["alpha"])):
            self.assertEqual(self.client.get(url).status_code, 302)
        r = self.client.post(reverse("command", args=["alpha", "start"]))
        self.assertEqual(r.status_code, 302)

    def test_studio_isolation(self):
        for url in (reverse("control", args=["beta"]), reverse("state", args=["beta"]),
                    reverse("preset_list", args=["beta"]),
                    reverse("preset_edit", args=["beta", self.pb.pk])):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        r = self.client.post(reverse("command", args=["beta", "start"]))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(TimerSession.objects.filter(studio=self.b, state="running").exists())
        self.assertEqual(self.client.post(reverse("preset_delete", args=["beta", self.pb.pk])).status_code, 404)
        self.assertTrue(Preset.objects.filter(pk=self.pb.pk).exists())

    def test_cannot_select_other_studios_preset(self):
        r = self.client.post(reverse("select_preset", args=["alpha"]), {"preset": self.pb.pk})
        self.assertEqual(r.status_code, 400)

    def test_commands_do_not_cross_studios(self):
        self.client.post(reverse("select_preset", args=["alpha"]), {"preset": self.pa.pk})
        services.select_preset(self.b, self.pb)
        r = self.client.post(reverse("command", args=["alpha", "start"]))
        self.assertEqual(r.json()["state"], "running")
        self.assertEqual(services.snapshot(self.b)["state"], "ready")

    def test_invalid_command_returns_409(self):
        self.client.post(reverse("select_preset", args=["alpha"]), {"preset": self.pa.pk})
        r = self.client.post(reverse("command", args=["alpha", "pause"]))
        self.assertEqual(r.status_code, 409)

    def test_display_link_readonly_and_revocable(self):
        url = reverse("display", args=[self.a.display_token])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 200)
        state_url = reverse("display_state", args=[self.a.display_token])
        self.assertEqual(self.client.get(state_url).status_code, 200)
        self.assertEqual(self.client.post(state_url).status_code, 405)
        self.assertEqual(self.client.get(f"/d/{self.a.display_token}/command/start/").status_code, 404)
        old = self.a.display_token
        self.client.login(username="ua", password=PW)
        self.client.post(reverse("regenerate_link", args=["alpha"]))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("display", args=[old])).status_code, 404)

    def test_display_refresh_keeps_session(self):
        self.client.post(reverse("select_preset", args=["alpha"]), {"preset": self.pa.pk})
        self.client.post(reverse("command", args=["alpha", "start"]))
        self.client.logout()
        url = reverse("display_state", args=[self.a.display_token])
        first, second = self.client.get(url).json(), self.client.get(url).json()
        self.assertEqual(first["state"], "running")
        self.assertEqual(first["run"], second["run"])

    def test_preset_crud_scoped(self):
        r = self.client.post(reverse("preset_new", args=["alpha"]), {
            "name": "New", "rounds": 2, "round_duration": "01:30", "rest_duration": "00:00", "direction": "up"})
        self.assertEqual(r.status_code, 302)
        p = Preset.objects.get(name="New")
        self.assertEqual((p.studio, p.round_seconds, p.rest_seconds), (self.a, 90, 0))


    def test_pages_render(self):
        for name, args in (("control", ["alpha"]), ("preset_list", ["alpha"]),
                           ("preset_new", ["alpha"]), ("preset_edit", ["alpha", self.pa.pk])):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)


class PresetFormTests(TestCase):
    def data(self, **kw):
        d = {"name": "X", "rounds": "3", "round_duration": "05:00", "rest_duration": "01:00", "direction": "down"}
        d.update(kw)
        return d

    def test_valid(self):
        f = PresetForm(self.data())
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual((f.cleaned_data["round_duration"], f.cleaned_data["rest_duration"]), (300, 60))

    def test_zero_rest_allowed(self):
        self.assertTrue(PresetForm(self.data(rest_duration="00:00")).is_valid())

    def test_rejections(self):
        for bad in (self.data(rounds="0"), self.data(round_duration="00:00"), self.data(round_duration="5"),
                    self.data(round_duration="05:60"), self.data(round_duration="ab:cd"),
                    self.data(rest_duration="01:75"), self.data(rest_duration="-1:00"),
                    self.data(direction="sideways"), self.data(rounds="")):
            self.assertFalse(PresetForm(bad).is_valid(), bad)
