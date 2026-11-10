document.addEventListener('DOMContentLoaded', () => {
    const summary = document.getElementById('timerWorkoutPreview');
    if (!summary) return;
    const rounds = document.getElementById('id_rounds');
    const work = document.getElementById('id_duration_str');
    const rest = document.getElementById('id_interval_str');
    function seconds(value) {
        if (!/^\d+(?::\d+){0,2}$/.test(value.trim())) return NaN;
        return value.trim().split(':').reduce((total, part) => total * 60 + Number(part), 0);
    }
    function label(value) {
        const hours = Math.floor(value / 3600);
        const minutes = Math.floor(value % 3600 / 60);
        const secs = String(value % 60).padStart(2, '0');
        return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`;
    }
    function update() {
        const count = Number(rounds.value), duration = seconds(work.value), interval = seconds(rest.value);
        if (!Number.isSafeInteger(count) || count < 1 || !Number.isFinite(duration) || duration <= 0 || !Number.isFinite(interval)) {
            summary.textContent = 'Enter valid rounds, work time and rest time to preview the workout.';
            return;
        }
        summary.textContent = `${count} rounds · ${label(duration)} work · ${label(interval)} rest · ${label(count * duration + (count - 1) * interval)} total (no rest after the final round).`;
    }
    [rounds, work, rest].forEach(field => field.addEventListener('input', update));
    update();
});
