// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: red; icon-glyph: check;

/*
 * Clear Todo — a Clear-style to-do list for Scriptable.
 *
 * Run it in the Scriptable app to open the list. Add it as a Scriptable
 * home-screen widget to see the "Today" list at a glance.
 *
 * Gestures (in the app):
 *   Pull down .............. create an item at the top
 *   Tap empty space ........ create an item at the bottom
 *   Tap an item ............ edit it (empty it to delete it)
 *   Swipe right ............ complete / un-complete
 *   Swipe left ............. delete
 *   Touch and hold, drag ... reorder
 *
 * Data lives in iCloud Drive at Scriptable/ClearTodo/data.json (or local
 * storage if iCloud is off). The data model already holds multiple lists;
 * the widget always shows the list whose id is WIDGET_LIST_ID.
 */

const WIDGET_LIST_ID = "today";
const APP_LIST_ID = "today"; // the one list the app edits for now
const DATA_DIR = "ClearTodo";
const DATA_FILE = "data.json";
// Set to "small", "medium" or "large" to preview the widget when running in the app.
const PREVIEW_WIDGET = false;

// ---------- colours (shared with the web view) ----------

// Clear's "heat map": the top item is red, fading to amber further down.
function heatColor(i, n) {
  var t = Math.min(1, i / Math.max(n - 1, 6));
  var h = (354 + 52 * t) % 360;
  var s = 0.86, l = 0.47 + 0.06 * t;
  var a = s * Math.min(l, 1 - l);
  function f(k0) {
    var k = (k0 + h / 30) % 12;
    var c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return ("0" + Math.round(c * 255).toString(16)).slice(-2);
  }
  return "#" + f(0) + f(8) + f(4);
}

// ---------- storage ----------

function fileManager() {
  try { return FileManager.iCloud(); } catch (e) { return FileManager.local(); }
}
const fm = fileManager();
const dataDir = fm.joinPath(fm.documentsDirectory(), DATA_DIR);
const dataPath = fm.joinPath(dataDir, DATA_FILE);

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function defaultData() {
  const tips = [
    "Pull down to add an item",
    "Tap an item to edit it",
    "Swipe right to complete",
    "Swipe left to delete",
    "Hold and drag to reorder",
  ];
  return {
    version: 1,
    lists: [{
      id: "today",
      name: "Today",
      items: tips.map((title) => ({ id: uid(), title, done: false })),
    }],
  };
}

function normalize(d) {
  const lists = (d && Array.isArray(d.lists) ? d.lists : [])
    .filter((l) => l && typeof l.id === "string")
    .map((l) => {
      const items = (Array.isArray(l.items) ? l.items : [])
        .filter((it) => it && typeof it.title === "string" && it.title.trim())
        .map((it) => ({ id: String(it.id || uid()), title: it.title, done: !!it.done }));
      // Keep the invariant the UI relies on: open items first, then completed ones.
      return {
        id: l.id,
        name: typeof l.name === "string" ? l.name : l.id,
        items: items.filter((it) => !it.done).concat(items.filter((it) => it.done)),
      };
    });
  if (!lists.some((l) => l.id === "today")) lists.unshift({ id: "today", name: "Today", items: [] });
  return { version: 1, lists };
}

async function loadData() {
  if (!fm.fileExists(dataPath)) return defaultData();
  if (fm.isFileStoredIniCloud(dataPath) && !fm.isFileDownloaded(dataPath)) {
    await fm.downloadFileFromiCloud(dataPath);
  }
  try {
    return normalize(JSON.parse(fm.readString(dataPath)));
  } catch (e) {
    // Keep the unreadable file so nothing is lost, then start fresh.
    fm.copy(dataPath, fm.joinPath(dataDir, "data.corrupt-" + Date.now() + ".json"));
    return defaultData();
  }
}

function saveData(d) {
  if (!fm.fileExists(dataDir)) fm.createDirectory(dataDir, true);
  fm.writeString(dataPath, JSON.stringify(d));
}

// ---------- widget ----------

function buildWidget(data, family) {
  const list = data.lists.find((l) => l.id === WIDGET_LIST_ID) || data.lists[0];
  const open = list.items.filter((it) => !it.done);
  const w = new ListWidget();
  w.backgroundColor = new Color("#000000");
  w.url = "scriptable:///run/" + encodeURIComponent(Script.name());
  w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);

  if (family === "accessoryInline") {
    w.addText(open.length ? open.length + " · " + open[0].title : list.name + " done");
    return w;
  }
  if (family === "accessoryCircular") {
    const t = w.addText(String(open.length));
    t.font = Font.boldSystemFont(22);
    t.centerAlignText();
    return w;
  }
  if (family === "accessoryRectangular") {
    const h = w.addText(list.name);
    h.font = Font.boldSystemFont(13);
    open.slice(0, 3).forEach((it) => {
      const t = w.addText(it.title);
      t.font = Font.systemFont(12);
      t.lineLimit = 1;
    });
    if (!open.length) w.addText("All done").font = Font.systemFont(12);
    return w;
  }

  const size = {
    small: { rows: 4, font: 12, h: 24 },
    medium: { rows: 4, font: 14, h: 26 },
    large: { rows: 10, font: 15, h: 26 },
    extraLarge: { rows: 10, font: 15, h: 26 },
  }[family] || { rows: 4, font: 14, h: 26 };

  w.setPadding(12, 12, 12, 12);

  const header = w.addStack();
  header.centerAlignContent();
  const title = header.addText(list.name);
  title.font = Font.heavySystemFont(size.font + 3);
  title.textColor = Color.white();
  header.addSpacer();
  const count = header.addText(open.length ? String(open.length) : "");
  count.font = Font.semiboldSystemFont(size.font);
  count.textColor = new Color("#8e8e93");
  w.addSpacer(8);

  if (!open.length) {
    const t = w.addText("All done");
    t.font = Font.semiboldSystemFont(size.font);
    t.textColor = new Color("#636366");
  }

  const shown = open.slice(0, size.rows);
  shown.forEach((it, i) => {
    const row = w.addStack();
    row.size = new Size(0, size.h);
    row.backgroundColor = new Color(heatColor(i, open.length));
    row.cornerRadius = 5;
    row.setPadding(0, 8, 0, 8);
    row.centerAlignContent();
    const t = row.addText(it.title);
    t.font = Font.boldSystemFont(size.font);
    t.textColor = Color.white();
    t.lineLimit = 1;
    row.addSpacer();
    if (i < shown.length - 1) w.addSpacer(3);
  });
  if (open.length > shown.length) {
    w.addSpacer(4);
    const more = w.addText("+" + (open.length - shown.length) + " more");
    more.font = Font.semiboldSystemFont(11);
    more.textColor = new Color("#8e8e93");
  }
  w.addSpacer();
  return w;
}

// ---------- app ----------

async function runApp(data) {
  const wv = new WebView();
  await wv.loadHTML(appHTML(data, APP_LIST_ID, true));
  let open = true;
  const closed = wv.present(true).then(() => { open = false; return null; });
  // The page hands back the full state after every change; write it to disk.
  while (open) {
    let json;
    try {
      json = await Promise.race([
        wv.evaluateJavaScript("window.__waitForChange(completion)", true),
        closed,
      ]);
    } catch (e) {
      console.error(e);
      break;
    }
    if (json) {
      try { saveData(normalize(JSON.parse(json))); } catch (e) { console.error(e); }
    }
  }
}

function appHTML(data, listId, bridge) {
  const boot = JSON.stringify({ data, listId, bridge }).replace(/</g, "\\u003c");
  return APP_TEMPLATE
    .replace("__BOOT__", () => boot)
    .replace("__HEAT__", () => heatColor.toString());
}

const APP_TEMPLATE = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<style>
  :root { --row: 62px; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body { margin: 0; height: 100%; background: #000; overflow: hidden; overscroll-behavior: none; }
  body {
    font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #fff; -webkit-font-smoothing: antialiased;
    -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;
  }
  #app { position: fixed; left: 0; right: 0; top: 0; bottom: 0; display: flex; flex-direction: column; padding-top: env(safe-area-inset-top); }
  #hdr { flex: 0 0 auto; display: flex; align-items: baseline; justify-content: space-between; padding: 14px 18px 10px; }
  #hdr h1 { margin: 0; font-size: 30px; font-weight: 800; letter-spacing: -0.6px; }
  #count { color: #8e8e93; font-size: 15px; font-weight: 600; }
  #scroller { flex: 1 1 auto; position: relative; overflow: hidden; display: flex; flex-direction: column; perspective: 700px; }
  #list, #tail { will-change: transform; }
  #list { position: relative; flex: 0 0 auto; }
  #tail {
    flex: 1 0 160px; display: flex; justify-content: center; padding: 28px 24px calc(28px + env(safe-area-inset-bottom));
    color: #48484a; font-size: 15px; font-weight: 600; text-align: center;
  }
  .row { position: relative; height: var(--row); overflow: hidden; background: #000; transition: opacity .2s; }
  .row.dim { opacity: .3; }
  .under {
    position: absolute; left: 0; right: 0; top: 0; bottom: 0; display: flex; align-items: center; justify-content: space-between;
    padding: 0 22px; font-size: 26px; font-weight: 800; color: #3a3a3c;
  }
  .under .on.ok { color: #4cd964; }
  .under .on.del { color: #ff3b30; }
  .face {
    position: absolute; left: 0; right: 0; top: 0; bottom: 0; display: flex; align-items: center; padding: 0 18px;
    font-size: 20px; font-weight: 700; letter-spacing: -0.2px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.14), inset 0 -1px 0 rgba(0,0,0,.10);
    transition: background-color .3s, color .3s;
  }
  .face.slide { transition: transform .22s cubic-bezier(.2,.8,.2,1), background-color .3s, color .3s; }
  .txt { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row.done .face { background: #1c1c1e; color: #636366; box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
  .row.done .txt { text-decoration: line-through; text-decoration-thickness: 2px; }
  .face.good { background: #4cd964 !important; color: #fff !important; }
  .row.lifted { overflow: visible; z-index: 10; }
  .row.lifted .face { transform: scale(1.04); box-shadow: 0 12px 28px rgba(0,0,0,.7); }
  .row.shift { transition: transform .2s ease, opacity .2s; }
  .edit {
    flex: 1; min-width: 0; margin: 0; padding: 0; border: 0; outline: 0; background: transparent;
    color: inherit; font: inherit; letter-spacing: inherit; caret-color: #fff;
    -webkit-user-select: text; user-select: text;
  }
  #pull {
    position: absolute; left: 0; right: 0; top: 0; height: var(--row); z-index: 1; pointer-events: none;
    display: flex; align-items: center; padding: 0 18px; font-size: 20px; font-weight: 700;
    transform-origin: 50% 100%; transform: translateY(-100%) rotateX(90deg);
  }
</style>
</head>
<body>
<div id="app">
  <header id="hdr"><h1 id="title"></h1><span id="count"></span></header>
  <div id="scroller">
    <div id="pull"></div>
    <div id="list"></div>
    <div id="tail"></div>
  </div>
</div>
<script>
(function () {
  var BOOT = __BOOT__;
  var heatColor = __HEAT__;
  var ROW = 62, SWIPE = 70, LONG_PRESS = 420, SLOP = 8;

  var state = BOOT.data;
  if (!BOOT.bridge) {
    try { var saved = localStorage.getItem("clear-todo"); if (saved) state = JSON.parse(saved); } catch (e) {}
  }
  var list = state.lists.filter(function (l) { return l.id === BOOT.listId; })[0] || state.lists[0];

  var app = document.getElementById("app");
  var scroller = document.getElementById("scroller");
  var listEl = document.getElementById("list");
  var tailEl = document.getElementById("tail");
  var pullEl = document.getElementById("pull");
  document.getElementById("title").textContent = list.name;

  // ---------- persistence ----------
  // In Scriptable, the host script waits on __waitForChange and writes whatever it gets to disk.
  var pending = null, waiter = null, saveTimer = null;
  window.__waitForChange = function (cb) {
    if (pending !== null) { var p = pending; pending = null; cb(p); } else { waiter = cb; }
  };
  function persist() {
    clearTimeout(saveTimer);
    var s = JSON.stringify(state);
    if (BOOT.bridge) {
      if (waiter) { var w = waiter; waiter = null; w(s); } else { pending = s; }
    } else {
      try { localStorage.setItem("clear-todo", s); } catch (e) {}
    }
  }
  function persistSoon() { clearTimeout(saveTimer); saveTimer = setTimeout(persist, 400); }

  // ---------- model ----------
  function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
  function find(id) { return list.items.filter(function (it) { return it.id === id; })[0]; }
  function indexOf(id) { for (var i = 0; i < list.items.length; i++) if (list.items[i].id === id) return i; return -1; }
  function openCount() { return list.items.filter(function (it) { return !it.done; }).length; }

  function toggleDone(id) {
    var i = indexOf(id), it = list.items[i];
    list.items.splice(i, 1);
    it.done = !it.done;
    // Newly completed items go to the top of the done section; restored ones to the bottom of the open section.
    list.items.splice(openCount(), 0, it);
  }
  function removeItem(id) { var i = indexOf(id); if (i >= 0) list.items.splice(i, 1); }
  function moveOpen(from, to) { var it = list.items.splice(from, 1)[0]; list.items.splice(to, 0, it); }

  // ---------- rendering ----------
  var els = {};
  var editingId = null;

  function makeRow(id) {
    var row = document.createElement("div");
    row.className = "row";
    row.dataset.id = id;
    row.innerHTML = '<div class="under"><span class="ok">&#10003;</span><span class="del">&#10005;</span></div><div class="face"></div>';
    return row;
  }

  function render(opts) {
    opts = opts || {};
    var before = {}, id;
    if (opts.flip) for (id in els) before[id] = els[id].getBoundingClientRect().top;

    var n = openCount(), k = 0, seen = {};
    list.items.forEach(function (it, i) {
      var row = els[it.id] || (els[it.id] = makeRow(it.id));
      seen[it.id] = true;
      row.classList.remove("lifted", "shift");
      row.style.transform = "";
      row.classList.toggle("done", it.done);
      row.classList.toggle("dim", editingId !== null && editingId !== it.id);
      row.firstChild.children[0].classList.remove("on");
      row.firstChild.children[1].classList.remove("on");
      var face = row.children[1];
      face.classList.remove("good");
      face.style.transform = "";
      face.style.backgroundColor = it.done ? "" : heatColor(k++, n);

      var input = face.querySelector("input");
      if (editingId === it.id) {
        if (!input) {
          face.innerHTML = "";
          input = document.createElement("input");
          input.className = "edit";
          input.setAttribute("enterkeyhint", "done");
          input.setAttribute("autocapitalize", "sentences");
          input.value = it.title;
          input.addEventListener("input", function () { it.title = input.value; persistSoon(); });
          input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); commitEdit(); } });
          input.addEventListener("blur", commitEdit);
          face.appendChild(input);
        }
      } else {
        if (input || !face.firstChild) face.innerHTML = '<span class="txt"></span>';
        face.firstChild.textContent = it.title;
      }
      if (listEl.children[i] !== row) listEl.insertBefore(row, listEl.children[i] || null);
    });
    for (id in els) if (!seen[id]) { els[id].remove(); delete els[id]; }

    document.getElementById("count").textContent = n ? n + " to do" : "";
    tailEl.textContent = list.items.length ? (n ? "" : "All done. Pull down to add more.")
                                           : "Pull down or tap here to add an item.";

    if (opts.flip) {
      for (id in els) {
        var el = els[id];
        if (before[id] === undefined) {
          if (opts.grow === id) el.animate([{ height: "0px" }, { height: ROW + "px" }], { duration: 220, easing: "ease-out" });
          continue;
        }
        var d = before[id] - el.getBoundingClientRect().top;
        if (Math.abs(d) > 0.5) {
          el.animate([{ transform: "translateY(" + d + "px)" }, { transform: "none" }],
                     { duration: 320, easing: "cubic-bezier(.2,.8,.2,1)" });
        }
      }
    }
  }

  // ---------- editing ----------
  function startEdit(id, grow) {
    editingId = id;
    render({ flip: true, grow: grow });
    var row = els[id], input = row.querySelector("input");
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    revealRow(row);
  }

  function commitEdit() {
    if (editingId === null) return;
    var it = find(editingId);
    editingId = null;
    if (it) {
      it.title = it.title.trim();
      if (!it.title) removeItem(it.id);
    }
    render({ flip: true });
    persist();
  }

  function addItem(atTop) {
    var it = { id: uid(), title: "", done: false };
    list.items.splice(atTop ? 0 : openCount(), 0, it);
    startEdit(it.id, atTop ? null : it.id);
  }

  // Keep the editing row visible above the keyboard.
  function revealRow(row) {
    var r = row.getBoundingClientRect(), s = scroller.getBoundingClientRect();
    if (r.bottom > s.bottom) scroller.scrollTop += r.bottom - s.bottom;
    else if (r.top < s.top) scroller.scrollTop -= s.top - r.top;
  }
  if (window.visualViewport) {
    var fitViewport = function () {
      app.style.top = visualViewport.offsetTop + "px";
      app.style.height = visualViewport.height + "px";
      app.style.bottom = "auto";
      if (editingId !== null && els[editingId]) revealRow(els[editingId]);
    };
    visualViewport.addEventListener("resize", fitViewport);
    visualViewport.addEventListener("scroll", fitViewport);
  }

  // ---------- pull to create ----------
  function setPull(p) {
    var y = p > 0 ? "translateY(" + p + "px)" : "";
    listEl.style.transform = y;
    tailEl.style.transform = y;
    var a = Math.max(0, 1 - p / ROW) * 90;
    pullEl.style.transform = "translateY(" + (p - ROW) + "px) rotateX(" + a + "deg)";
    pullEl.style.backgroundColor = heatColor(0, openCount() + 1);
    pullEl.style.opacity = p > 0 ? String(Math.min(1, 0.4 + p / ROW)) : "0";
    pullEl.textContent = p >= ROW ? "Release to Create Item" : "Pull to Create Item";
  }
  function animatePullBack(from) {
    var start = performance.now();
    (function step(now) {
      var t = Math.min(1, (now - start) / 200), p = from * (1 - t) * (1 - t);
      setPull(p);
      if (t < 1) requestAnimationFrame(step);
    })(start);
  }
  setPull(0);

  // ---------- scrolling with momentum ----------
  var momentum = null;
  function stopMomentum() { var was = momentum !== null; if (momentum) cancelAnimationFrame(momentum); momentum = null; return was; }
  function maxScroll() { return scroller.scrollHeight - scroller.clientHeight; }
  function startMomentum(v) {
    var last = performance.now();
    function step(now) {
      var dt = now - last; last = now;
      scroller.scrollTop += v * dt;
      v *= Math.pow(0.995, dt);
      var top = scroller.scrollTop;
      momentum = (Math.abs(v) > 0.02 && top > 0 && top < maxScroll()) ? requestAnimationFrame(step) : null;
    }
    momentum = requestAnimationFrame(step);
  }
  scroller.addEventListener("wheel", function (e) { e.preventDefault(); scroller.scrollTop += e.deltaY; }, { passive: false });

  // ---------- gestures ----------
  var g = null;

  function onStart(x, y, target) {
    var wasScrolling = stopMomentum();
    if (!scroller.contains(target)) { g = null; return; }
    if (editingId !== null) {
      g = { consumed: true };
      if (!target.closest("input")) commitEdit();
      return;
    }
    var row = target.closest(".row");
    g = { x0: x, y0: y, t0: Date.now(), row: row, id: row && row.dataset.id, mode: null,
          st0: scroller.scrollTop, pull: 0, noTap: wasScrolling, samples: [[Date.now(), y]] };
    if (row && !row.classList.contains("done")) g.timer = setTimeout(startLift, LONG_PRESS);
  }

  function onMove(x, y) {
    if (!g || g.consumed) return;
    var dx = x - g.x0, dy = y - g.y0;
    if (g.mode === "lift") return dragLift(dy);
    if (!g.mode) {
      if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) return;
      clearTimeout(g.timer);
      g.mode = (Math.abs(dx) > Math.abs(dy) && g.row) ? "swipe" : "scroll";
    }
    if (g.mode === "swipe") return dragSwipe(dx);
    // Vertical: scroll the list, and past the top turn it into a pull-to-create.
    var want = g.st0 - dy;
    g.samples.push([Date.now(), y]);
    if (g.samples.length > 6) g.samples.shift();
    if (want < 0) {
      scroller.scrollTop = 0;
      g.pull = -want;
      if (g.pull > ROW) g.pull = ROW + (g.pull - ROW) * 0.4;
    } else {
      g.pull = 0;
      scroller.scrollTop = want;
    }
    setPull(g.pull);
  }

  function onEnd() {
    if (!g) return false;
    var cur = g; g = null;
    clearTimeout(cur.timer);
    if (cur.consumed) return true;
    if (cur.mode === "lift") { endLift(cur); return true; }
    if (cur.mode === "swipe") { endSwipe(cur); return true; }
    if (cur.mode === "scroll") {
      if (cur.pull >= ROW) { setPull(0); addItem(true); }
      else if (cur.pull > 0) animatePullBack(cur.pull);
      else {
        var s = cur.samples, a = s[0], b = s[s.length - 1];
        if (b[0] - a[0] > 0 && Date.now() - b[0] < 80) startMomentum(-(b[1] - a[1]) / (b[0] - a[0]));
      }
      return true;
    }
    // A tap.
    if (cur.noTap || Date.now() - cur.t0 > LONG_PRESS) return true;
    if (!cur.row) addItem(false);
    else if (!cur.row.classList.contains("done")) startEdit(cur.id);
    return true;
  }

  function onCancel() {
    if (!g) return;
    var cur = g; g = null;
    clearTimeout(cur.timer);
    if (cur.mode === "swipe") { cur.dx = 0; endSwipe(cur); }
    else if (cur.mode === "lift") endLift(cur);
    else if (cur.pull > 0) animatePullBack(cur.pull);
  }

  // Swipe right to complete, left to delete.
  function dragSwipe(dx) {
    g.dx = dx;
    var face = g.row.children[1], under = g.row.firstChild;
    face.classList.remove("slide");
    face.style.transform = "translateX(" + dx + "px)";
    face.classList.toggle("good", dx > SWIPE);
    under.children[0].classList.toggle("on", dx > SWIPE);
    under.children[1].classList.toggle("on", dx < -SWIPE);
  }
  function endSwipe(cur) {
    var face = cur.row.children[1], dx = cur.dx || 0;
    face.classList.add("slide");
    if (dx > SWIPE) {
      toggleDone(cur.id);
      render({ flip: true });
      persist();
    } else if (dx < -SWIPE) {
      face.style.transform = "translateX(" + (-cur.row.offsetWidth) + "px)";
      setTimeout(function () {
        cur.row.animate([{ height: ROW + "px" }, { height: "0px" }], { duration: 180, easing: "ease-in" })
          .onfinish = function () { removeItem(cur.id); render({ flip: true }); persist(); };
        cur.row.style.height = "0px";
      }, 180);
    } else {
      face.style.transform = "";
      face.classList.remove("good");
      cur.row.firstChild.children[0].classList.remove("on");
      cur.row.firstChild.children[1].classList.remove("on");
    }
  }

  // Touch and hold, then drag to reorder (open items only).
  function startLift() {
    if (!g || g.mode) return;
    g.mode = "lift";
    g.from = g.to = indexOf(g.id);
    g.n = openCount();
    g.row.classList.add("lifted");
    if (navigator.vibrate) navigator.vibrate(10);
  }
  function dragLift(dy) {
    dy = Math.max(-g.from * ROW, Math.min((g.n - 1 - g.from) * ROW, dy));
    g.row.style.transform = "translateY(" + dy + "px)";
    g.to = g.from + Math.round(dy / ROW);
    for (var k = 0; k < g.n; k++) {
      if (k === g.from) continue;
      var el = els[list.items[k].id], shift = 0;
      if (k > g.from && k <= g.to) shift = -ROW;
      else if (k < g.from && k >= g.to) shift = ROW;
      el.classList.add("shift");
      el.style.transform = shift ? "translateY(" + shift + "px)" : "";
    }
  }
  function endLift(cur) {
    if (cur.to !== cur.from) moveOpen(cur.from, cur.to);
    render({ flip: true });
    if (cur.to !== cur.from) persist();
  }

  // Touch input (the real thing) plus mouse input for trying it in a desktop browser.
  var lastTouch = 0;
  function editingTarget(t) { return editingId !== null && t.closest && t.closest("input"); }
  document.addEventListener("touchstart", function (e) {
    lastTouch = Date.now();
    if (e.touches.length > 1) { onCancel(); return; }
    var t = e.touches[0];
    onStart(t.clientX, t.clientY, e.target);
  }, { passive: false });
  document.addEventListener("touchmove", function (e) {
    lastTouch = Date.now();
    if (editingTarget(e.target)) return;
    e.preventDefault();
    var t = e.touches[0];
    onMove(t.clientX, t.clientY);
  }, { passive: false });
  document.addEventListener("touchend", function (e) {
    lastTouch = Date.now();
    if (editingTarget(e.target)) { g = null; return; }
    if (onEnd()) e.preventDefault();
  }, { passive: false });
  document.addEventListener("touchcancel", onCancel);

  var mouseDown = false;
  function fromMouse() { return Date.now() - lastTouch > 1000; }
  document.addEventListener("mousedown", function (e) {
    if (!fromMouse() || editingTarget(e.target)) return;
    mouseDown = true;
    onStart(e.clientX, e.clientY, e.target);
    if (g) e.preventDefault();
  });
  window.addEventListener("mousemove", function (e) { if (mouseDown && fromMouse()) onMove(e.clientX, e.clientY); });
  window.addEventListener("mouseup", function () { if (mouseDown && fromMouse()) { mouseDown = false; onEnd(); } });

  render();
})();
</script>
</body>
</html>`;

// ---------- entry point ----------

const data = await loadData();
if (config.runsInWidget) {
  Script.setWidget(buildWidget(data, config.widgetFamily));
} else if (PREVIEW_WIDGET) {
  const w = buildWidget(data, PREVIEW_WIDGET);
  await w["present" + PREVIEW_WIDGET[0].toUpperCase() + PREVIEW_WIDGET.slice(1)]();
} else {
  await runApp(data);
}
Script.complete();
