// Atelier web app. Progressive enhancement only: every page works without this file.
"use strict";
document.addEventListener("submit", function (ev) {
  var btn = ev.submitter;
  var msg = btn && btn.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) {
    ev.preventDefault();
    return;
  }
});
