"""Pure timer schedule logic (no Django dependencies)."""

ROLLING = "rolling"
REST = "rest"


def build_phases(rounds, round_seconds, rest_seconds):
    """Return a list of (kind, round_number, start_ms, duration_ms).

    Rest phases only occur between rounds; nothing follows the final round.
    """
    phases = []
    start = 0
    for number in range(1, rounds + 1):
        duration = round_seconds * 1000
        phases.append((ROLLING, number, start, duration))
        start += duration
        if number < rounds and rest_seconds > 0:
            duration = rest_seconds * 1000
            phases.append((REST, number, start, duration))
            start += duration
    return phases


def total_ms(phases):
    kind, number, start, duration = phases[-1]
    return start + duration


def locate(phases, elapsed_ms):
    """Return (index, phase_elapsed_ms, finished) for an elapsed time.

    Phases are half-open [start, end); at or beyond the total the final phase
    is reported with its full duration elapsed and finished=True.
    """
    if elapsed_ms >= total_ms(phases):
        kind, number, start, duration = phases[-1]
        return len(phases) - 1, duration, True
    elapsed_ms = max(elapsed_ms, 0)
    for index, (kind, number, start, duration) in enumerate(phases):
        if start <= elapsed_ms < start + duration:
            return index, elapsed_ms - start, False
    raise AssertionError("unreachable")


def displayed_seconds(direction, duration_ms, phase_elapsed_ms):
    """Whole seconds shown for a phase. Down counts remaining (ceil), up counts elapsed (floor)."""
    if direction == "down":
        return -(-(duration_ms - phase_elapsed_ms) // 1000)
    return phase_elapsed_ms // 1000
