(function () {
  "use strict";
  var cfg = JSON.parse(document.getElementById("control-config").textContent);
  var clock = new WebTimer.Clock(cfg.state);
  var csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
  var ENABLED = {
    start: ["ready", "stopped", "finished"], stop: ["running", "paused"], pause: ["running"],
    resume: ["paused"], reset: ["running", "paused", "stopped", "finished"]
  };
  var digits = document.getElementById("digits"), phase = document.getElementById("phase"),
      status = document.getElementById("status"), message = document.getElementById("message"),
      select = document.getElementById("preset-select"), card = document.getElementById("timer-card"),
      round = document.getElementById("round"), pills = document.getElementById("round-pills"),
      progress = document.getElementById("progress");

  function currentState() {
    var v = clock.view();
    return v.status === "Finished" ? "finished" : clock.state.state;
  }

  function render() {
    var v = clock.view(), st = currentState();
    digits.textContent = v.digits;
    phase.textContent = v.phase;
    status.textContent = v.status || "Running";
    var phaseInfo = clock.state.phases && clock.state.phases.find(function (p) { var e = clock.elapsed(); return e >= p[2] && e < p[2] + p[3]; });
    if (!phaseInfo && clock.state.phases) { phaseInfo = clock.state.phases[clock.state.phases.length - 1]; }
    var visualState = v.status ? (v.status.toLowerCase() === "finished" ? "done" : v.status.toLowerCase()) : (phaseInfo && phaseInfo[0] === "rest" ? "rest" : "work");
    card.classList.remove("state-ready", "state-running", "state-rest", "state-paused", "state-stopped", "state-finished", "state-work", "state-done");
    card.classList.add("state-" + visualState);
    status.className = "crm-phase-badge state-" + visualState;
    if (clock.state.preset && phaseInfo) {
      var phaseElapsed = Math.max(0, Math.min(phaseInfo[3], clock.elapsed() - phaseInfo[2]));
      round.textContent = "Round " + phaseInfo[1] + " of " + clock.state.preset.rounds;
      progress.style.width = Math.max(0, Math.min(100, (clock.state.preset.direction === "down" ? 1 - phaseElapsed / phaseInfo[3] : phaseElapsed / phaseInfo[3]) * 100)) + "%";
      pills.replaceChildren();
      for (var i = 1; i <= clock.state.preset.rounds; i++) {
        var dot = document.createElement("span"); dot.className = "round-dot";
        if (i < phaseInfo[1]) { dot.classList.add("completed"); }
        if (i === phaseInfo[1] && !v.status) { dot.classList.add("current"); }
        pills.appendChild(dot);
      }
    }
    document.querySelectorAll("button[data-cmd]").forEach(function (b) {
      b.disabled = ENABLED[b.dataset.cmd].indexOf(st) === -1 || (b.dataset.cmd === "start" && !clock.state.preset);
    });
    select.disabled = st === "running" || st === "paused";
  }

  function apply(s) {
    clock.apply(s);
    if (s.selected_preset_id) { select.value = String(s.selected_preset_id); }
    render();
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded" },
      body: body || ""
    }).then(function (r) {
      return r.json().then(function (data) {
        if (r.ok) { message.textContent = ""; apply(data); }
        else { message.textContent = data.error || "Request failed."; if (data.state) { apply(data.state); } }
      });
    }).catch(function () { message.textContent = "Network error."; });
  }

  document.querySelectorAll("button[data-cmd]").forEach(function (b) {
    b.addEventListener("click", function () { post(cfg.commandUrl.replace("CMD", b.dataset.cmd)); });
  });
  select.addEventListener("change", function () {
    post(cfg.selectUrl, "preset=" + encodeURIComponent(select.value));
  });

  document.addEventListener("keydown", function (event) {
    if (event.repeat || ["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"].indexOf(event.target.tagName) !== -1) { return; }
    if (event.code === "Space") {
      event.preventDefault();
      var command = currentState() === "running" ? "pause" : currentState() === "paused" ? "resume" : "start";
      if (ENABLED[command].indexOf(currentState()) !== -1) { post(cfg.commandUrl.replace("CMD", command)); }
    } else if (event.key.toLowerCase() === "r" && ENABLED.reset.indexOf(currentState()) !== -1) {
      event.preventDefault(); post(cfg.commandUrl.replace("CMD", "reset"));
    }
  });

  var wakeButton = document.getElementById("wake-lock"), wakeLock = null;
  function updateWakeLock() {
    if (!wakeButton) { return; }
    wakeButton.setAttribute("aria-pressed", String(!!wakeLock));
    wakeButton.querySelector("span").textContent = wakeLock ? "Screen awake" : "Screen normal";
  }
  function toggleWakeLock() {
    if (wakeLock) { wakeLock.release(); wakeLock = null; updateWakeLock(); return; }
    if (!navigator.wakeLock) { if (wakeButton) { wakeButton.querySelector("span").textContent = "Not supported"; } return; }
    navigator.wakeLock.request("screen").then(function (lock) {
      wakeLock = lock;
      lock.addEventListener("release", function () { wakeLock = null; updateWakeLock(); });
      updateWakeLock();
    }).catch(function () { if (wakeButton) { wakeButton.querySelector("span").textContent = "Unavailable"; } });
  }
  if (wakeButton) {
    wakeButton.addEventListener("click", toggleWakeLock);
    wakeButton.addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggleWakeLock(); } });
  }

  /* Spotify controls copied into the standalone timer: the server keeps OAuth
     tokens private; this browser only receives playback metadata. */
  var spotifyPanel = document.getElementById("spotify-controls"), spotifyMessage = document.getElementById("spotify-message"), spotifyConnect = document.getElementById("spotify-connect"), spotifyPlaylist = document.getElementById("spotify-playlist"), spotifyDevice = document.getElementById("spotify-device"), spotifyTrack = document.getElementById("spotify-track"), spotifyVolume = document.getElementById("spotify-volume"), spotifySeek = document.getElementById("spotify-seek"), repeatMode = "off";
  function spotifyUrl(kind) { return cfg.spotifyDataUrl.replace("KIND", kind); }
  function spotifyFetch(url, options) { return fetch(url, options).then(function (r) { return r.json().then(function (d) { if (!r.ok) { throw new Error(d.error || "Spotify request failed"); } return d; }); }); }
  function fillSpotify(selectEl, items, label) { selectEl.innerHTML = '<option value="">Choose a ' + label + '</option>'; items.forEach(function (item) { var option = document.createElement("option"); option.value = item.uri || item.id || ""; option.textContent = item.name + (item.type ? " (" + item.type + ")" : ""); selectEl.appendChild(option); }); }
  function refreshPlayback() { if (!spotifyPanel.hidden) spotifyFetch(spotifyUrl("playback")).then(function (d) { spotifyTrack.textContent = d.active ? d.track_name + " — " + d.artists : "No active track"; if (typeof d.volume_percent === "number") { spotifyVolume.value = d.volume_percent; } spotifySeek.max = d.duration_ms || 0; spotifySeek.value = d.progress_ms || 0; repeatMode = d.repeat_state || "off"; }).catch(function (e) { spotifyMessage.textContent = e.message; }); }
  function spotifyAction(action, extra) { return spotifyFetch(cfg.spotifyControlUrl, {method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf},body:JSON.stringify(Object.assign({action:action,playlist_uri:spotifyPlaylist.value,device_id:spotifyDevice.value},extra || {}))}).then(refreshPlayback).catch(function (e) { spotifyMessage.textContent = e.message; }); }
  if (spotifyPanel) {
    spotifyFetch(cfg.spotifyStatusUrl).then(function (statusData) {
      if (!statusData.configured) { spotifyMessage.textContent = "Spotify is not configured on this server."; spotifyConnect.hidden = true; return; }
      if (!statusData.connected) { spotifyMessage.textContent = "Connect Spotify Premium to use music controls."; return; }
      spotifyConnect.hidden = true; spotifyPanel.hidden = false; spotifyMessage.textContent = "Connected as " + statusData.display_name;
      Promise.all([spotifyFetch(spotifyUrl("playlists")), spotifyFetch(spotifyUrl("devices"))]).then(function (data) { fillSpotify(spotifyPlaylist, data[0].playlists, "playlist"); fillSpotify(spotifyDevice, data[1].devices, "device"); spotifyPlaylist.value = statusData.last_playlist_uri; spotifyDevice.value = statusData.last_device_id; refreshPlayback(); });
    }).catch(function (e) { spotifyMessage.textContent = e.message; });
    document.querySelectorAll("[data-spotify]").forEach(function (button) { button.addEventListener("click", function () { if (button.dataset.spotify === "repeat") { var modes=["off","context","track"]; spotifyAction("repeat", {state:modes[(modes.indexOf(repeatMode)+1)%3]}); } else if (button.dataset.spotify === "shuffle") { spotifyAction("shuffle", {state:true}); } else { spotifyAction(button.dataset.spotify); } }); });
    spotifySeek.addEventListener("change", function () { spotifyAction("seek", {position_ms:Number(spotifySeek.value)}); });
    spotifyVolume.addEventListener("change", function () { spotifyAction("volume", {volume_percent:Number(spotifyVolume.value)}); });
    setInterval(refreshPlayback, 5000);
  }

  WebTimer.poll(cfg.stateUrl, apply, 1000);
  setInterval(render, 100);
  apply(cfg.state);
})();
