PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fingerprint reader</title>
<style>
:root { --page:#0b0c0e; --surface:#141518; --raised:#1f2024; --line:#25262b; --text:#edeef0; --muted:#9b9da4; --faint:#63656c; --ok:#4cc38a; --warn:#f2c14e; --bad:#ff8a80; }
@media (prefers-color-scheme: light) { :root { --page:#f6f6f7; --surface:#fff; --raised:#f0f0f2; --line:#e4e4e7; --text:#111214; --muted:#55575e; --faint:#8b8d94; --ok:#1f8a5a; --warn:#9a6b00; --bad:#c2352b; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--text); font:15px/1.5 system-ui, -apple-system, "Segoe UI", Inter, sans-serif; }
main { max-width:1080px; margin:0 auto; padding:40px 24px 64px; display:grid; gap:20px; grid-template-columns:1fr 1fr; }
h1 { grid-column:1/-1; margin:0; font-size:15px; font-weight:500; color:var(--muted); }
section { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:22px; min-width:0; }
.wide { grid-column:1/-1; }
h2 { margin:0 0 14px; font-size:14px; font-weight:500; color:var(--muted); }
.big { font-size:40px; font-weight:600; letter-spacing:-1px; line-height:1.1; margin:0 0 6px; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:8px; background:var(--faint); vertical-align:middle; }
.ok .dot, .dot.ok { background:var(--ok); } .bad .dot, .dot.bad { background:var(--bad); } .dot.warn { background:var(--warn); }
ul { list-style:none; margin:0; padding:0; }
li { padding:10px 0; border-top:1px solid var(--line); display:flex; gap:10px; align-items:center; }
li:first-child { border-top:0; }
.grow { flex:1; min-width:0; overflow-wrap:anywhere; }
button { font:inherit; font-weight:600; border:0; border-radius:8px; padding:9px 14px; cursor:pointer; background:var(--text); color:var(--page); }
a.button { display:inline-block; text-decoration:none; font-weight:600; border-radius:8px; padding:9px 14px; background:var(--text); color:var(--page); margin-top:6px; }
a.inline { color:var(--text); font-weight:500; }
button.quiet { background:var(--raised); color:var(--text); font-weight:500; border:1px solid var(--line); }
button:disabled { opacity:.45; cursor:default; }
.test { display:grid; grid-template-columns:200px 1fr; gap:22px; align-items:start; }
.well { width:200px; aspect-ratio:3/4; border-radius:10px; background:var(--raised); display:flex; align-items:center; justify-content:center; overflow:hidden; color:var(--faint); font-size:13px; text-align:center; padding:12px; }
.well img { width:100%; height:100%; object-fit:contain; background:#fff; }
.say { font-size:22px; font-weight:600; margin:0 0 8px; }
.muted { color:var(--muted); } .faint { color:var(--faint); font-size:13px; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; font-size:14px; }
td { padding:8px 8px 8px 0; border-top:1px solid var(--line); vertical-align:top; overflow-wrap:anywhere; }
@media (max-width:760px) { main { grid-template-columns:1fr; } .test { grid-template-columns:1fr; } }
</style>
</head>
<body>
<main>
  <h1>Fingerprint reader · capture agent @VERSION@</h1>

  <section id="reader">
    <h2>Reader</h2>
    <p class="big" id="state">Checking…</p>
    <p class="muted" id="device"></p>
    <p id="todo-action" hidden><a id="todo-link" class="button" href="#"></a></p>
  </section>

  <section>
    <h2>Checks</h2>
    <ul id="checks"><li class="faint">Running checks…</li></ul>
  </section>

  <section class="wide">
    <h2>Test the reader</h2>
    <div class="test">
      <div class="well" id="well">The print shows here</div>
      <div>
        <p class="say" id="say">Press Test, then place a finger on the glass.</p>
        <p class="muted" id="quality"></p>
        <button id="test">Test</button>
        <button id="cancel" class="quiet" hidden>Cancel</button>
      </div>
    </div>
  </section>

  <section>
    <h2>Sites that may use the reader</h2>
    <ul id="sites"></ul>
  </section>

  <section>
    <h2>Recent presses</h2>
    <table><tbody id="log"><tr><td class="faint">Nothing yet.</td></tr></tbody></table>
  </section>
</main>
<script>
const TOKEN = "@TOKEN@";
const $ = (id) => document.getElementById(id);
const say = { waiting: "Place a finger on the glass now.", finger_on: "Hold still…", captured: "Got it · lift your finger.", reading: "Reading…",
  done: "Got it · lift your finger.", timeout: "No finger came. Press Test to try again.", cancelled: "Stopped." };

function li(html) { const el = document.createElement("li"); el.innerHTML = html; return el; }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }

let lastChecks = [];

function headline(s) {
  const todo = lastChecks.find((c) => !c.ok);
  $("reader").className = s.connected ? "ok" : "bad";
  $("todo-action").hidden = true;
  if (s.connected) {
    $("state").innerHTML = '<span class="dot"></span>' + (s.capturing ? "Reading a finger" : "Ready to use");
    $("device").textContent = s.device;
  } else if (todo) {
    $("state").innerHTML = '<span class="dot"></span>One thing to do';
    $("device").textContent = todo.say;
    if (todo.link) {
      $("todo-link").href = todo.link;
      $("todo-link").textContent = todo.link_label || "Open";
      $("todo-action").hidden = false;
    }
  } else {
    $("state").innerHTML = '<span class="dot"></span>Not connected';
    $("device").textContent = "Plug in the U.are.U 4500.";
  }
}

async function status() {
  try {
    headline(await (await fetch("/status")).json());
  } catch { $("state").textContent = "Agent not answering"; }
}

async function checks() {
  lastChecks = await (await fetch("/doctor")).json();
  $("checks").replaceChildren(...lastChecks.map((c) =>
    li(`<span class="dot ${c.ok ? "ok" : "bad"}"></span><span class="grow"><b>${esc(c.name)}</b> · ${esc(c.say)}` +
      (c.link ? ` <a class="inline" href="${esc(c.link)}">${esc(c.link_label || "Open")}</a>` : "") + `</span>`)));
  status();
}

async function site(action, origin) {
  const res = await fetch(`/sites/${action}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Agent-Token": TOKEN },
    body: JSON.stringify({ site: origin }) });
  showSites(await res.json());
}

function showSites(s) {
  const rows = [
    ...s.waiting.map((o) => { const el = li(`<span class="dot warn"></span><span class="grow">${esc(o)}<br><span class="faint">Asked to use the reader</span></span><button>Allow</button>`);
      el.querySelector("button").onclick = () => site("approve", o); return el; }),
    ...s.built_in.map((o) => li(`<span class="dot ok"></span><span class="grow">${esc(o)}<br><span class="faint">Built in</span></span>`)),
    ...s.approved.map((o) => { const el = li(`<span class="dot ok"></span><span class="grow">${esc(o)}<br><span class="faint">Allowed on this PC</span></span><button class="quiet">Remove</button>`);
      el.querySelector("button").onclick = () => site("forget", o); return el; }),
  ];
  $("sites").replaceChildren(...rows);
}

async function sites() { showSites(await (await fetch("/sites")).json()); }

async function log() {
  const rows = await (await fetch("/log")).json();
  if (!rows.length) return;
  $("log").replaceChildren(...rows.slice(0, 12).map((r) => {
    const tr = document.createElement("tr");
    const q = r.ink !== undefined ? `ink ${(r.ink * 100).toFixed(1)}% · area ${(r.coverage * 100).toFixed(0)}%` : (r.detail || "");
    tr.innerHTML = `<td>${esc(r.at.slice(11, 19))}</td><td>${esc(r.result)}</td><td class="muted">${esc(q)}</td><td class="faint">${esc(r.site)}</td>`;
    return tr;
  }));
}

$("test").onclick = async () => {
  $("test").disabled = true; $("cancel").hidden = false; $("quality").textContent = "";
  try {
    const res = await fetch("/capture", { method: "POST" });
    const body = await res.json();
    if (res.ok) {
      $("well").innerHTML = `<img alt="Captured fingerprint" src="data:image/png;base64,${body.image}">`;
      $("quality").textContent = `${body.width} × ${body.height} at ${body.ppi} ppi · ink ${(body.quality.ink * 100).toFixed(1)}% · print area ${(body.quality.coverage * 100).toFixed(0)}% · ${body.attempts} ${body.attempts === 1 ? "press" : "presses"}`;
    } else if (res.status !== 408 && res.status !== 409) {
      $("say").textContent = body.detail;
    }
  } finally {
    $("test").disabled = false; $("cancel").hidden = true; status(); log();
  }
};
$("cancel").onclick = () => fetch("/cancel", { method: "POST" });

const events = new EventSource("/events");
events.onmessage = (m) => {
  const e = JSON.parse(m.data);
  $("say").textContent = e.event === "press_again" ? e.say : e.event === "error" ? e.detail : (say[e.event] || $("say").textContent);
  if (["done", "press_again", "timeout", "cancelled", "error"].includes(e.event)) log();
};

checks(); sites(); log();
setInterval(status, 3000);
setInterval(checks, 15000);
setInterval(sites, 5000);
</script>
</body>
</html>
"""


def render(token: str, version: str) -> str:
    return PAGE.replace("@TOKEN@", token).replace("@VERSION@", version)
