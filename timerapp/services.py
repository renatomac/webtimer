"""Server-authoritative timer state and command handling."""
from django.db import transaction
from django.utils import timezone

from . import engine
from .models import Preset, TimerSession

START, STOP, PAUSE, RESUME, RESET = "start", "stop", "pause", "resume", "reset"

ALLOWED = {
    START: {TimerSession.READY, TimerSession.STOPPED, TimerSession.FINISHED},
    STOP: {TimerSession.RUNNING, TimerSession.PAUSED},
    PAUSE: {TimerSession.RUNNING},
    RESUME: {TimerSession.PAUSED},
    RESET: {TimerSession.RUNNING, TimerSession.PAUSED, TimerSession.STOPPED, TimerSession.FINISHED},
}


class InvalidCommand(Exception):
    pass


def now():
    return timezone.now()


def _config(session):
    """Timer parameters: live selected preset while Ready, snapshot otherwise."""
    if session.state == TimerSession.READY:
        p = session.selected_preset
        if p is None:
            return None
        return dict(name=p.name, rounds=p.rounds, round_seconds=p.round_seconds,
                    rest_seconds=p.rest_seconds, direction=p.direction)
    return dict(name=session.name, rounds=session.rounds, round_seconds=session.round_seconds,
                rest_seconds=session.rest_seconds, direction=session.direction)


def current_elapsed_ms(session, at=None):
    elapsed = session.elapsed_ms
    if session.state == TimerSession.RUNNING and session.running_since:
        elapsed += int(((at or now()) - session.running_since).total_seconds() * 1000)
    return max(elapsed, 0)


def _settle(session):
    """Persist the Finished state once a running session has passed its end."""
    if session.state != TimerSession.RUNNING:
        return
    cfg = _config(session)
    phases = engine.build_phases(cfg["rounds"], cfg["round_seconds"], cfg["rest_seconds"])
    total = engine.total_ms(phases)
    if current_elapsed_ms(session) >= total:
        session.state = TimerSession.FINISHED
        session.elapsed_ms = total
        session.running_since = None
        session.save()


def get_session(studio, lock=False):
    """Return the studio's session, creating it on first use. Must run inside a transaction when lock=True."""
    TimerSession.objects.get_or_create(studio=studio)
    qs = TimerSession.objects.select_related("selected_preset")
    if lock:
        qs = qs.select_for_update()
    return qs.get(studio=studio)


def snapshot(studio):
    with transaction.atomic():
        session = get_session(studio, lock=True)
        _settle(session)
        return serialize(session)


def serialize(session):
    cfg = _config(session)
    data = {"state": session.state, "run": session.run, "server_time_ms": int(now().timestamp() * 1000),
            "preset": None, "selected_preset_id": session.selected_preset_id}
    if cfg is None:
        return data
    phases = engine.build_phases(cfg["rounds"], cfg["round_seconds"], cfg["rest_seconds"])
    elapsed = 0 if session.state == TimerSession.READY else current_elapsed_ms(session)
    data.update(
        preset=cfg,
        elapsed_ms=min(elapsed, engine.total_ms(phases)),
        total_ms=engine.total_ms(phases),
        phases=[list(p) for p in phases],
    )
    return data


def apply_command(studio, command):
    if command not in ALLOWED:
        raise InvalidCommand("Unknown command.")
    with transaction.atomic():
        session = get_session(studio, lock=True)
        _settle(session)
        if session.state not in ALLOWED[command]:
            raise InvalidCommand(f"Cannot {command} while {session.state}.")
        t = now()
        if command == START:
            p = session.selected_preset
            if p is None:
                raise InvalidCommand("Select a preset first.")
            session.name, session.rounds, session.round_seconds = p.name, p.rounds, p.round_seconds
            session.rest_seconds, session.direction = p.rest_seconds, p.direction
            session.state, session.elapsed_ms, session.running_since = TimerSession.RUNNING, 0, t
            session.run += 1
        elif command == PAUSE:
            session.elapsed_ms = current_elapsed_ms(session, t)
            session.state, session.running_since = TimerSession.PAUSED, None
        elif command == RESUME:
            session.state, session.running_since = TimerSession.RUNNING, t
        elif command == STOP:
            session.elapsed_ms = current_elapsed_ms(session, t)
            session.state, session.running_since = TimerSession.STOPPED, None
        elif command == RESET:
            session.state, session.elapsed_ms, session.running_since = TimerSession.READY, 0, None
            session.run += 1
        session.save()
        return serialize(session)


def select_preset(studio, preset):
    """Select a preset; only allowed while no run is in progress. Returns Ready state."""
    with transaction.atomic():
        session = get_session(studio, lock=True)
        _settle(session)
        if session.state in (TimerSession.RUNNING, TimerSession.PAUSED):
            raise InvalidCommand("Stop the timer before changing the preset.")
        if preset.studio_id != studio.id:
            raise InvalidCommand("Unknown preset.")
        session.selected_preset = preset
        session.state, session.elapsed_ms, session.running_since = TimerSession.READY, 0, None
        session.run += 1
        session.save()
        return serialize(session)
