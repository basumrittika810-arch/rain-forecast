/* Vaanam website (decision D-028). Plain JavaScript, no libraries.
   All rain text (shown amount, IMD label, message) comes from the API (tested in Python); this file only displays it.
   Rain only: no farming advice anywhere. */
"use strict";

const STALE_HOURS = 36;          // D-026: warn when the forecast is older than this
const WAKE_AFTER_MS = 3000;      // show the wake-up note if a request takes longer (Render free tier sleeps)
const TIMEOUT_MS = 90000;

const CATEGORIES = [             // order and words for the legend; colours are in style.css (.cat-...)
  ["no_rain", "No rain"], ["very_light", "Very light"], ["light", "Light"], ["moderate", "Moderate"],
  ["heavy", "Heavy"], ["very_heavy", "Very heavy"], ["extremely_heavy", "Extremely heavy"],
  ["unavailable", "No forecast"],
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SVG_NS = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
  }
  for (const c of children) n.append(c);
  return n;
}

function svg(tag, attrs = {}, text) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}

/* ------------------------------------------------------------------ requests with clear loading / error states */

function showStatus(box, message, { error = false, spinner = false, retry = null } = {}) {
  box.replaceChildren();
  box.classList.toggle("error", error);
  if (spinner) box.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  box.append(document.createTextNode(message));
  if (retry) {
    const b = el("button", { type: "button", class: "btn btn-soft", text: "Try again" });
    b.addEventListener("click", retry);
    box.append(el("br"), b);
  }
}

const clearStatus = (box) => { box.replaceChildren(); box.classList.remove("error"); };

async function getJSON(url, box, loadingText) {
  showStatus(box, loadingText, { spinner: true });
  const wake = setTimeout(() => showStatus(box,
    "Waking up the server, this can take up to a minute…", { spinner: true }), WAKE_AFTER_MS);
  const ctrl = new AbortController();
  const stop = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } });
    let body = null;
    try { body = await r.json(); } catch (_) { /* non-JSON error page */ }
    return { status: r.status, body };
  } catch (e) {
    return { status: 0, body: null, aborted: e.name === "AbortError" };
  } finally {
    clearTimeout(wake);
    clearTimeout(stop);
  }
}

function networkProblem(res) {
  return res.aborted ? "The server did not answer in time. Please try again."
    : "Could not reach the server. Please check your internet connection and try again.";
}

/* ------------------------------------------------------------------ search */

const findStatus = $("find-status");
const results = $("results");
let searchSeq = 0;

function placeText(p) { return `${p.name}, ${p.district} district`; }

async function search(q) {
  q = q.trim();
  results.replaceChildren();
  if (q.replace(/[^A-Za-z0-9]/g, "").length < 2) {
    showStatus(findStatus, "Please type at least 2 letters of the place name.");
    return;
  }
  const seq = ++searchSeq;
  const res = await getJSON(`/api/places?q=${encodeURIComponent(q)}&limit=10`, findStatus, "Searching…");
  if (seq !== searchSeq) return;                       // a newer search has started
  if (res.status !== 200 || !res.body) {
    showStatus(findStatus, res.status === 0 ? networkProblem(res) : "Search is not working right now. Please try again.",
      { error: true, retry: () => search(q) });
    return;
  }
  clearStatus(findStatus);
  const { kind, results: list } = res.body;
  if (kind === "none" || list.length === 0) {
    showStatus(findStatus, "No place found. Try a nearby town or check the spelling.");
    return;
  }
  if (kind === "suggestions") results.append(el("li", { class: "heading", text: "Did you mean…?" }));
  for (const p of list) {
    const b = el("button", { type: "button", class: "result", text: placeText(p) });
    b.addEventListener("click", () => openForecast(p.lat, p.lon, placeText(p), p.name));
    results.append(el("li", {}, b));
  }
}

let typingTimer = null;
$("search-form").addEventListener("submit", (e) => { e.preventDefault(); clearTimeout(typingTimer); search($("q").value); });
$("q").addEventListener("input", () => {
  clearTimeout(typingTimer);
  const q = $("q").value;
  if (q.replace(/[^A-Za-z0-9]/g, "").length >= 2) typingTimer = setTimeout(() => search(q), 400);
});

/* ------------------------------------------------------------------ use my location */

$("locate").addEventListener("click", () => {
  results.replaceChildren();
  if (!("geolocation" in navigator)) {
    showStatus(findStatus, "This phone or browser cannot share its location. Please use the search box above.");
    return;
  }
  showStatus(findStatus, "Finding your location…", { spinner: true });
  navigator.geolocation.getCurrentPosition(
    (pos) => locateDone(pos.coords.latitude, pos.coords.longitude),
    (err) => {
      const msg = {
        1: "Location permission was denied. You can allow it in your browser settings, or use the search box above.",
        2: "Your location is unavailable right now (no GPS signal or network). Please try again or use the search box above.",
        3: "Finding your location took too long. Please try again or use the search box above.",
      }[err.code] || "Your location could not be found. Please use the search box above.";
      showStatus(findStatus, msg, { error: true });
    },
    { enableHighAccuracy: false, timeout: 20000, maximumAge: 600000 });
});

async function locateDone(lat, lon) {
  const res = await getJSON(`/api/places/nearest?lat=${lat}&lon=${lon}`, findStatus, "Finding the nearest place…");
  // never show coordinates: if no name can be found, say "your location"
  const name = res.status === 200 && res.body ? `Near ${placeText(res.body)}` : "Your location";
  const short = res.status === 200 && res.body ? res.body.name : "your location";
  clearStatus(findStatus);
  openForecast(lat, lon, name, short, true);
}

/* ------------------------------------------------------------------ forecast */

const forecastBox = $("forecast");
const forecastStatus = $("forecast-status");

async function openForecast(lat, lon, title, shortName, fromGps = false) {
  forecastBox.hidden = true;
  const res = await getJSON(`/api/forecast?lat=${lat}&lon=${lon}`, forecastStatus, "Loading the forecast…");
  if (res.status === 404 && fromGps) {
    clearStatus(forecastStatus);
    showStatus(findStatus, "Your location seems to be outside Tamil Nadu. This forecast covers Tamil Nadu only. " +
      "Please use the search box above to choose a place in Tamil Nadu.", { error: true });
    return;
  }
  if (res.status !== 200 || !res.body) {
    const msg = res.status === 0 ? networkProblem(res)
      : res.status === 503 ? "No forecast has been published yet. Please try again later."
      : res.status === 404 ? "This place is outside the forecast area (Tamil Nadu). Please choose another place."
      : "The forecast could not be loaded. Please try again.";
    showStatus(forecastStatus, msg, { error: true,
      retry: res.status === 404 ? null : () => openForecast(lat, lon, title, shortName, fromGps) });
    return;
  }
  clearStatus(forecastStatus);
  results.replaceChildren();                           // fold the place list away; the search box stays
  render(res.body, title, shortName);
  forecastBox.hidden = false;
  forecastBox.scrollIntoView({ behavior: "smooth", block: "start" });
}

function fmtIst(iso) {                    // "2026-11-12T05:30+05:30" -> "12 Nov 2026, 05:30 IST" (string is already IST)
  const [d, t] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  return `${day} ${MONTHS[m - 1]} ${y}, ${t.slice(0, 5)} IST`;
}

function dayName(dateStr) {               // "2026-11-13" -> "Fri 13 Nov"
  const [y, m, d] = dateStr.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${WEEKDAYS[wd]} ${d} ${MONTHS[m - 1]}`;
}

function render(f, title, shortName) {
  $("place").textContent = title;
  $("made").textContent = `Forecast made: ${fmtIst(f.run.init_ist)}`;

  const ageH = (Date.now() - Date.parse(f.run.init_utc)) / 3.6e6;
  const stale = $("stale");
  stale.hidden = !(ageH > STALE_HOURS);
  stale.textContent = stale.hidden ? "" : `This forecast is ${Math.floor(ageH)} hours old. A newer one should have ` +
    "arrived by now; the update may be delayed. Please check again later.";

  const now = Date.now();
  const days = f.days.filter((d) => Date.parse(d.end) > now);            // days already over are hidden
  const partialShown = days.some((d) => d.partial);
  $("day-note").textContent = "Each day runs from 23:30 to 23:30 IST." + (partialShown
    ? " The first day is a partial day (18 hours): it starts when the forecast was made." : "");
  $("area-note").textContent = `Average for the area around ${shortName} (~27 km). ` +
    "Rain at your exact spot may be heavier or lighter.";

  drawDayChart(days, now);
  drawLegend();
  drawDayList(days, f.intervals, now);
}

function isToday(d, now) { return Date.parse(d.start) <= now && now < Date.parse(d.end); }

function labelText(d) { return d.label + (d.partial ? " (18 hours)" : ""); }

function niceMax(v) {
  for (const m of [5, 10, 25, 50, 100, 150, 250, 400]) if (v <= m) return m;
  return Math.ceil(v / 100) * 100;
}

function shortAmount(d) {                  // bar label: "0", "< 0.1", "12.3"
  return d.shown === null ? "no data" : d.shown.replace(" mm", "");
}

/* 10-day chart: one bar per day, coloured by IMD category, labelled with date and shown amount */
function drawDayChart(days, now) {
  const box = $("chart");
  box.replaceChildren();
  if (days.length === 0) { box.append(el("p", { text: "No days left in this forecast." })); return; }
  const W = 360, H = 250, top = 30, base = 190, left = 4, right = 4;
  const slot = (W - left - right) / days.length, bw = Math.min(28, slot * 0.7);
  const max = niceMax(Math.max(0, ...days.filter((d) => d.mm !== null).map((d) => d.mm)));
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Bar chart of rain per day: " + days.map((d) => `${dayName(d.date)} ${d.shown ?? "no data"}`).join(", ") });
  s.append(svg("line", { x1: left, x2: W - right, y1: base, y2: base, stroke: "#34536a", "stroke-width": 1 }));
  s.append(svg("text", { x: W - right, y: 14, "text-anchor": "end", "font-size": 11 }, `scale: 0–${max} mm`));
  days.forEach((d, i) => {
    const cx = left + slot * (i + 0.5);
    const g = svg("g", { tabindex: 0, role: "button", "aria-label": `${dayName(d.date)}: ${d.shown ?? "no data"}, ${d.label}` });
    if (d.mm === null) {                                           // missing: dashed empty box, never a 0 bar
      g.append(svg("rect", { class: "cat-unavailable", x: cx - bw / 2, y: base - 40, width: bw, height: 40, rx: 3 }));
      g.append(svg("text", { x: cx, y: base - 46, "text-anchor": "middle", "font-size": 10 }, "no data"));
    } else {
      const h = d.mm === 0 ? 3 : Math.max(4, (d.mm / max) * (base - top));
      g.append(svg("rect", { class: `bar cat-${d.category}`, x: cx - bw / 2, y: base - h, width: bw, height: h, rx: 3,
        stroke: "rgba(16,48,74,0.35)", "stroke-width": 0.8, style: `animation-delay:${i * 60}ms` }));
      g.append(svg("text", { x: cx, y: base - h - 6, "text-anchor": "middle", "font-size": 13, "font-weight": 700 },
        shortAmount(d)));
    }
    const [wd, dd] = dayName(d.date).split(" ");
    g.append(svg("text", { x: cx, y: base + 19, "text-anchor": "middle", "font-size": 13,
      "font-weight": isToday(d, now) ? 800 : 400 }, isToday(d, now) ? "Today" : wd));
    g.append(svg("text", { x: cx, y: base + 36, "text-anchor": "middle", "font-size": 13 }, dd));
    const open = () => toggleDay(d.date, true);
    g.addEventListener("click", open);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    s.append(g);
  });
  s.append(svg("text", { x: W / 2, y: H - 4, "text-anchor": "middle", "font-size": 12 }, "mm of rain per day"));
  box.append(s);
}

function drawLegend() {
  const ul = $("legend");
  ul.replaceChildren();
  for (const [key, word] of CATEGORIES) {
    ul.append(el("li", {}, el("span", { class: `swatch cat-${key}`, "aria-hidden": "true" }), word));
  }
}

function drawDayList(days, intervals, now) {
  const ol = $("days");
  ol.replaceChildren();
  for (const d of days) {
    const id = `day-${d.date}`;
    const head = el("button", { type: "button", class: "day-head", "aria-expanded": "false", "aria-controls": id + "-detail" });
    const when = isToday(d, now) ? "Today · " : "";
    head.append(
      el("span", { class: "day-date" }, el("span", { class: "today-tag", text: when }), dayName(d.date)),
      el("span", { class: "day-amount", text: d.shown ?? "—" }),
      el("span", {}, el("span", { class: `chip cat-${d.category}`, text: labelText(d) })),
      el("span", { class: "day-msg", text: d.status === "unavailable" ? "No forecast available for this day." : d.message }),
    );
    const detail = el("div", { class: "day-detail", id: id + "-detail", hidden: "" });
    head.addEventListener("click", () => toggleDay(d.date));
    const li = el("li", { class: "day", id }, head, detail);
    li._data = { d, intervals };
    ol.append(li);
  }
}

function toggleDay(date, forceOpen = false) {
  const li = document.getElementById(`day-${date}`);
  if (!li) return;
  const head = li.querySelector(".day-head"), detail = li.querySelector(".day-detail");
  const open = forceOpen || head.getAttribute("aria-expanded") !== "true";
  head.setAttribute("aria-expanded", String(open));
  detail.hidden = !open;
  if (open && !detail.hasChildNodes()) drawBlocks(detail, li._data.d, li._data.intervals);
  if (forceOpen) li.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* 3-hour chart for one day: one bar per forecast block, start times in IST */
function drawBlocks(box, d, intervals) {
  const start = Date.parse(d.start), end = Date.parse(d.end);
  const ivs = intervals.filter((i) => Date.parse(i.start) >= start && Date.parse(i.end) <= end);
  if (d.status === "unavailable" || ivs.length === 0) {
    box.append(el("p", { text: "No forecast available for this day." }));
    return;
  }
  const hours = [...new Set(ivs.map((i) => i.hours))].join(" and ");
  box.append(el("p", { class: "hint",
    text: `Each bar is one ${hours}-hour block; the time shown is when the block starts (IST). ` +
          "Rain can fall at any time within a block." }));
  const W = 360, H = 190, top = 26, base = 142, left = 4, right = 4;
  const slot = (W - left - right) / ivs.length, bw = Math.min(30, slot * 0.66);
  const max = niceMax(Math.max(0, ...ivs.filter((i) => i.mm !== null).map((i) => i.mm)));
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Rain per block: " + ivs.map((i) => `${i.start.slice(11, 16)} ${i.shown ?? "no data"}`).join(", ") });
  s.append(svg("line", { x1: left, x2: W - right, y1: base, y2: base, stroke: "#34536a", "stroke-width": 1 }));
  s.append(svg("text", { x: W - right, y: 12, "text-anchor": "end", "font-size": 11 }, `scale: 0–${max} mm`));
  ivs.forEach((iv, k) => {
    const cx = left + slot * (k + 0.5);
    if (iv.mm === null) {
      s.append(svg("rect", { class: "cat-unavailable", x: cx - bw / 2, y: base - 34, width: bw, height: 34, rx: 3 }));
      s.append(svg("text", { x: cx, y: base - 40, "text-anchor": "middle", "font-size": 10 }, "no data"));
    } else {
      const h = iv.mm === 0 ? 3 : Math.max(4, (iv.mm / max) * (base - top));
      s.append(svg("rect", { class: "bar", x: cx - bw / 2, y: base - h, width: bw, height: h, rx: 3,
        style: `fill:var(${iv.mm === 0 ? "--c-no-rain" : "--c-moderate"});animation-delay:${k * 50}ms` }));
      s.append(svg("text", { x: cx, y: base - h - 6, "text-anchor": "middle", "font-size": 13, "font-weight": 700 },
        iv.shown.replace(" mm", "")));
    }
    s.append(svg("text", { x: cx, y: base + 19, "text-anchor": "middle", "font-size": 12 }, iv.start.slice(11, 16)));
  });
  s.append(svg("text", { x: W / 2, y: H - 6, "text-anchor": "middle", "font-size": 11 }, "mm of rain in each block"));
  box.append(s);
}
