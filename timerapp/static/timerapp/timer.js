/* Shared client-side timer rendering. The server is authoritative; the client
   only interpolates between polls using a monotonic local clock. */
(function (global) {
  "use strict";

  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function mmss(totalSeconds) {
    totalSeconds = Math.max(0, totalSeconds);
    return pad(Math.floor(totalSeconds / 60)) + ":" + pad(totalSeconds % 60);
  }

  function Clock(state) { this.apply(state); }

  Clock.prototype.apply = function (state) {
    this.state = state;
    this.received = performance.now();
  };

  Clock.prototype.elapsed = function () {
    var s = this.state;
    if (!s.preset) { return 0; }
    var e = s.elapsed_ms;
    if (s.state === "running") { e += performance.now() - this.received; }
    return Math.min(e, s.total_ms);
  };

  /* Describe what should be shown right now. */
  Clock.prototype.view = function () {
    var s = this.state;
    if (!s.preset) {
      return { digits: "--:--", phase: "No preset selected", status: "Ready", running: false };
    }
    var elapsed = this.elapsed();
    var phases = s.phases, i = phases.length - 1, finished = elapsed >= s.total_ms;
    if (!finished) {
      for (i = 0; i < phases.length; i++) {
        if (elapsed < phases[i][2] + phases[i][3]) { break; }
      }
    }
    var ph = phases[i], kind = ph[0], number = ph[1], dur = ph[3];
    var pe = finished ? dur : Math.max(0, elapsed - ph[2]);
    var secs = s.preset.direction === "down" ? Math.ceil((dur - pe) / 1000) : Math.floor(pe / 1000);
    var total = s.preset.rounds;
    var phaseText = kind === "rolling"
      ? "Round " + number + " of " + total + " \u00b7 Rolling"
      : "Rest before Round " + (number + 1) + " of " + total;
    var status = null;
    var st = finished ? "finished" : s.state;
    if (st === "ready") { status = "Ready"; }
    else if (st === "paused") { status = "Paused"; }
    else if (st === "stopped") { status = "Stopped"; }
    else if (st === "finished") { status = "Finished"; }
    if (st === "finished") { phaseText = "Finished \u00b7 " + total + " round" + (total === 1 ? "" : "s"); }
    if (st === "ready") { phaseText = "Round 1 of " + total + " \u00b7 " + s.preset.name; }
    return { digits: mmss(secs), phase: phaseText, status: status, running: st === "running" };
  };

  /* Cue times (ms of session elapsed time): beeps at 3,2,1 s remaining in every
     phase, bell at the end of each rolling round (including the last). */
  function cuesFor(state) {
    var out = [];
    if (!state.phases) { return out; }
    state.phases.forEach(function (ph) {
      var start = ph[2], end = ph[2] + ph[3];
      for (var k = 3; k >= 1; k--) {
        if (end - k * 1000 >= start) { out.push({ t: end - k * 1000, type: "beep" }); }
      }
      if (ph[0] === "rolling") { out.push({ t: end, type: "bell" }); }
    });
    return out;
  }

  var MISSED_AFTER_MS = 1500;

  /* Decides which cues to play; never repeats a cue and skips missed ones. */
  function CueTracker(play) {
    this.play = play;
    this.run = null;
    this.played = {};
    this.cues = [];
  }

  CueTracker.prototype.sync = function (state, elapsed) {
    var fresh = state.run !== this.run;
    this.run = state.run;
    this.cues = cuesFor(state);
    if (fresh) {
      this.played = {};
      for (var i = 0; i < this.cues.length; i++) {
        if (this.cues[i].t <= elapsed) { this.played[i] = true; }
      }
    }
  };

  CueTracker.prototype.tick = function (running, elapsed) {
    if (!running) { return; }
    for (var i = 0; i < this.cues.length; i++) {
      var c = this.cues[i];
      if (this.played[i] || c.t > elapsed) { continue; }
      this.played[i] = true;
      if (elapsed - c.t <= MISSED_AFTER_MS) { this.play(c.type); }
    }
  };

  function poll(url, onState, intervalMs) {
    function once() {
      fetch(url, { cache: "no-store", credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (s) { if (s) { onState(s); } })
        .catch(function () {})
        .then(function () { setTimeout(once, intervalMs); });
    }
    setTimeout(once, intervalMs);
  }

  global.WebTimer = { Clock: Clock, CueTracker: CueTracker, cuesFor: cuesFor, poll: poll, mmss: mmss };
})(window);
