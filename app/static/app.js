// Atelier web app. Progressive enhancement only: every page works without this file.
"use strict";
document.addEventListener("submit", function (ev) {
  var btn = ev.submitter;
  var msg = btn && btn.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) {
    ev.preventDefault();
    return;
  }
  if (ev.target.matches("form.draft-form") && !ev.defaultPrevented) {
    var status = ev.target.querySelector(".draft-progress");
    if (status) status.hidden = false;
    ev.target.setAttribute("aria-busy", "true");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Drafting...";
    }
  }
});
