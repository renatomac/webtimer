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
      select = document.getElementById("preset-select");

  function currentState() {
    var v = clock.view();
    return v.status === "Finished" ? "finished" : clock.state.state;
  }

  function render() {
    var v = clock.view(), st = currentState();
    digits.textContent = v.digits;
    phase.textContent = v.phase;
    status.textContent = v.status || "Running";
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

  WebTimer.poll(cfg.stateUrl, apply, 1000);
  setInterval(render, 100);
  apply(cfg.state);
})();
