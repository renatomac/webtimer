(function () {
  "use strict";
  var cfg = JSON.parse(document.getElementById("display-config").textContent);
  var clock = new WebTimer.Clock(cfg.state);
  var audio = null;

  function beep(freq, start, dur, gain) {
    var o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = freq;
    g.gain.setValueAtTime(gain, start);
    g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
    o.connect(g); g.connect(audio.destination);
    o.start(start); o.stop(start + dur);
  }

  function play(type) {
    if (!audio || audio.state !== "running") { return; }
    var t = audio.currentTime;
    if (type === "beep") { beep(880, t, 0.15, 0.4); }
    else { beep(523, t, 1.6, 0.6); beep(1046, t, 1.2, 0.3); beep(1568, t, 0.8, 0.15); }
  }

  var tracker = new WebTimer.CueTracker(play);
  tracker.sync(cfg.state, clock.elapsed());

  var el = {
    digits: document.getElementById("digits"), phase: document.getElementById("phase"),
    status: document.getElementById("status"), date: document.getElementById("date"),
    time: document.getElementById("time"), sound: document.getElementById("sound"),
    round: document.getElementById("round"), pills: document.getElementById("round-pills"),
    progress: document.getElementById("progress"), fullscreen: document.getElementById("fullscreen"),
    wakeLock: document.getElementById("wake-lock")
  };

  var dateFmt, timeFmt;
  try {
    dateFmt = new Intl.DateTimeFormat(undefined, { timeZone: cfg.timezone, weekday: "long", year: "numeric", month: "long", day: "numeric" });
    timeFmt = new Intl.DateTimeFormat(undefined, { timeZone: cfg.timezone, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch (e) {
    dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "full" });
    timeFmt = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });
  }

  function render() {
    var v = clock.view();
    el.digits.textContent = v.digits;
    el.phase.textContent = v.phase;
    el.status.textContent = v.status || "";
    el.status.hidden = !v.status;
    document.body.dataset.status = v.status ? v.status.toLowerCase() : "running";
    var stateClass = v.status ? "state-" + v.status.toLowerCase() : (v.phase.indexOf("Rest") === 0 ? "state-rest" : "state-work");
    document.body.classList.remove("state-ready", "state-running", "state-rest", "state-paused", "state-stopped", "state-finished", "state-work");
    document.body.classList.add(stateClass);
    var phase = clock.state.phases && clock.state.phases.find(function (p) {
      var elapsed = clock.elapsed(); return elapsed >= p[2] && elapsed < p[2] + p[3];
    });
    if (!phase && clock.state.phases) { phase = clock.state.phases[clock.state.phases.length - 1]; }
    if (clock.state.preset && phase) {
      var elapsedInPhase = Math.max(0, Math.min(phase[3], clock.elapsed() - phase[2]));
      el.round.textContent = "Round " + phase[1] + " of " + clock.state.preset.rounds;
      el.progress.style.width = Math.max(0, Math.min(100, (clock.state.preset.direction === "down" ? 1 - elapsedInPhase / phase[3] : elapsedInPhase / phase[3]) * 100)) + "%";
      el.pills.replaceChildren();
      for (var i = 1; i <= clock.state.preset.rounds; i++) {
        var dot = document.createElement("span"); dot.className = "round-dot";
        if (i < phase[1]) { dot.classList.add("completed"); }
        if (i === phase[1] && !v.status) { dot.classList.add("current"); }
        el.pills.appendChild(dot);
      }
    }
    var now = new Date();
    el.date.textContent = dateFmt.format(now);
    el.time.textContent = timeFmt.format(now);
    tracker.tick(clock.state.state === "running" || clock.state.state === "finished", clock.elapsed());
  }

  el.sound.addEventListener("click", function () {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { el.sound.textContent = "Sound unsupported"; return; }
    audio = audio || new AC();
    audio.resume().then(function () {
      el.sound.textContent = "Sound on";
      el.sound.classList.add("on");
      el.sound.setAttribute("aria-pressed", "true");
      beep(880, audio.currentTime, 0.1, 0.2);
    });
  });

  if (el.fullscreen) {
    el.fullscreen.addEventListener("click", function () {
      if (document.fullscreenElement) { document.exitFullscreen(); }
      else if (document.documentElement.requestFullscreen) { document.documentElement.requestFullscreen(); }
    });
  }
  var wakeLock = null;
  function updateWakeLock() {
    el.wakeLock.setAttribute("aria-pressed", String(!!wakeLock));
    el.wakeLock.textContent = wakeLock ? "Screen awake" : "Keep awake";
  }
  if (el.wakeLock) {
    el.wakeLock.addEventListener("click", function () {
      if (wakeLock) { wakeLock.release(); wakeLock = null; updateWakeLock(); return; }
      if (!navigator.wakeLock) { el.wakeLock.textContent = "Not supported"; return; }
      navigator.wakeLock.request("screen").then(function (lock) {
        wakeLock = lock; lock.addEventListener("release", function () { wakeLock = null; updateWakeLock(); }); updateWakeLock();
      }).catch(function () { el.wakeLock.textContent = "Unavailable"; });
    });
  }

  WebTimer.poll(cfg.stateUrl, function (s) {
    clock.apply(s);
    tracker.sync(s, clock.elapsed());
  }, 1000);

  setInterval(render, 100);
  render();
})();
