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
    time: document.getElementById("time"), sound: document.getElementById("sound")
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
      beep(880, audio.currentTime, 0.1, 0.2);
    });
  });

  WebTimer.poll(cfg.stateUrl, function (s) {
    clock.apply(s);
    tracker.sync(s, clock.elapsed());
  }, 1000);

  setInterval(render, 100);
  render();
})();
