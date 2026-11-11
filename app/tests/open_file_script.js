// Run app/static/app.js against a tiny fake DOM and report what it does.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const field = {value: ""}, msg = {textContent: ""};
const fileInput = {files: []};
const formAttrs = {"data-bad": "BAD", "data-big": "BIG"};
let submitted = 0, prevented = 0;
const form = {addEventListener: (t, f) => listeners.form = f, getAttribute: k => formAttrs[k], submit: () => submitted++};
const box = {hidden: true, querySelector: q => ({form: form, "input[type=file]": fileInput, "input[name=study]": field, "[data-open-msg]": msg})[q]};
global.document = {addEventListener: () => {}, querySelector: q => q === "[data-open-file]" ? box : null};
global.window = {confirm: () => true};
let text = "";
global.FileReader = function () { this.readAsText = () => { this.result = text; this.onload(); }; };
eval(src);
const out = {};
out.unhidden = box.hidden === false;
const ev = () => ({preventDefault: () => prevented++});
listeners.form(ev());                       // no file chosen
out.noFile = msg.textContent; out.submittedAfterNoFile = submitted;
fileInput.files = [{size: 600 * 1024}]; listeners.form(ev());
out.big = msg.textContent; out.submittedAfterBig = submitted;
fileInput.files = [{size: 1000}]; text = '{"a":"b"}'; listeners.form(ev());
out.fieldValue = field.value; out.submittedAfterOk = submitted; out.msgAfterOk = msg.textContent; out.prevented = prevented;
console.log(JSON.stringify(out));
