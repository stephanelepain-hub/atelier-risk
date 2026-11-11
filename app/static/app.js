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

// "Open a saved file" (public mode): read the chosen study file here and send its text as the form field `study`.
(function () {
  var box = document.querySelector("[data-open-file]");
  if (!box) { return; }
  var form = box.querySelector("form");
  var input = box.querySelector("input[type=file]");
  var field = box.querySelector("input[name=study]");
  var msg = box.querySelector("[data-open-msg]");
  var MAX = 512 * 1024;
  box.hidden = false;
  function say(text) { msg.textContent = text; }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    say("");
    var file = input.files && input.files[0];
    if (!file) { say(form.getAttribute("data-bad")); return; }
    if (file.size > MAX) { say(form.getAttribute("data-big")); return; }
    var reader = new FileReader();
    reader.onload = function () {
      field.value = String(reader.result);
      form.submit();
    };
    reader.onerror = function () { say(form.getAttribute("data-bad")); };
    reader.readAsText(file);
  });
})();
