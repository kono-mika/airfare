"""The Price history page: every price AirFare has seen, filtered by route and dates, plus the results of
"search the lowest price history" lookups.

The same page works opened from disk (reports/history.html, refreshed after every check) and served by
AirFare Settings, where it can also delete records and run a lookup. It carries every interface language
and switches between them in place. Records saved in another currency (before a currency change) are shown
converted at the latest exchange rate, marked with "≈".
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from . import analyst, brand, chatgpt, deepseek, i18n, money, openai_api, pricelog

DEEPSEEK_LABELS = {"deepseek-flash": "V4.1 Flash", "deepseek-v4-pro": "V4 Pro"}


def routes_info(cfg: dict, records: list[dict]) -> list[dict]:
    """Routes for the picker: configured ones first, then routes that only exist in old records."""
    out, seen = [], set()
    for r in cfg.get("routes", []):
        seen.add(r["id"])
        out.append({"id": r["id"], "name": r.get("name") or f"{r.get('origin', '').upper()} → {r.get('destination', '').upper()}",
                    "return": r.get("trip") == "return", "depart_from": r.get("depart_from") or "",
                    "depart_to": r.get("depart_to") or r.get("depart_from") or "",
                    "return_from": r.get("return_from") or "", "return_to": r.get("return_to") or r.get("return_from") or "",
                    "active": True})
    for rec in records:
        if rec["route_id"] not in seen:
            seen.add(rec["route_id"])
            out.append({"id": rec["route_id"], "name": rec.get("route_name") or rec["route_id"],
                        "return": bool(rec.get("return")), "depart_from": "", "depart_to": "",
                        "return_from": "", "return_to": "", "active": False})
    return out


def lookup_options(cfg: dict) -> dict:
    """The analysts and models the History page offers for a lookup, and which one is picked by default."""
    provider = cfg.get("llm_provider") or "claude"
    claude_key = cfg.get("claude_mode") == "key"
    return {
        "providers": [
            {"id": "claude", "name": "Claude", "can_browse": True,
             "available": bool(cfg.get("anthropic_api_key")) if claude_key else True,
             "note": "Add an Anthropic API key in Settings, or switch Claude to your Claude account.",
             "models": [[m, label] for m, label in analyst.CLAUDE_MODELS.items()] + [["", "Account default"]]},
            {"id": "chatgpt", "name": "ChatGPT", "can_browse": True, "available": bool(chatgpt.codex_path()),
             "note": "Install the Codex app and sign in to ChatGPT in Settings to use your ChatGPT account.",
             "models": [["", "Account default"]]},
            {"id": "openai", "name": "ChatGPT (API)", "can_browse": True, "available": bool(cfg.get("openai_api_key")),
             "note": "Add an OpenAI API key in Settings to use ChatGPT through the API.",
             "models": [[m, openai_api.LABELS.get(m, m)] for m in openai_api.MODELS]},
            {"id": "deepseek", "name": "DeepSeek", "can_browse": False, "available": bool(cfg.get("deepseek_api_key")),
             "note": "Add a DeepSeek API key in Settings to use DeepSeek.",
             "models": [[m, DEEPSEEK_LABELS.get(m, m)] for m in deepseek.MODELS]},
        ],
        "default": {"provider": provider,
                    "model": {"deepseek": cfg.get("deepseek_model"), "openai": cfg.get("openai_model"),
                              "chatgpt": cfg.get("chatgpt_model") or ""}.get(provider, cfg.get("model") or "")},
    }


def in_currency(records: list[dict], currency: str, rates: dict) -> list[dict]:
    """Records as the page shows them: prices in the chosen currency, older ones converted (marked ≈)."""
    out = []
    for r in records:
        # Older records name no currency: the site they came from tells what "$" or "kr" meant there.
        site = urlparse(r.get("url") or "").hostname or ""
        src = r.get("currency_code") or money.detect(r.get("price_text") or "", site)
        if src and src != currency and r.get("price") is not None:
            value = money.convert(r["price"], src, currency, rates)
            if value is not None:
                r = {**r, "price": round(value, 2), "price_text": "≈ " + money.fmt(value, currency),
                     "site_price": r.get("site_price") or r.get("price_text")}
        out.append(r)
    return out


def page_data(cfg: dict, rates: dict | None = None) -> dict:
    currency = cfg.get("currency") or money.DEFAULT
    if rates is None:
        rates = money.rates(refresh=False)          # building the page never waits for the network
    records = in_currency(pricelog.load(), currency, rates)
    return {"records": records, "research": pricelog.load_research(), "routes": routes_info(cfg, records),
            "lookup": lookup_options(cfg), "currency": currency, "sign": money.sign(currency),
            "sign_after": currency in money.AFTER}


def build(cfg: dict, served: bool) -> str:
    lang = i18n.norm(cfg.get("language"))
    rates = money.rates(refresh=False)
    # "<" written as its JSON escape, so no stored text (a route name, a quote) can end or bend the data block.
    data = json.dumps({**page_data(cfg, rates), "served": served, "lang": lang, "texts": i18n.bundle()},
                      ensure_ascii=False).replace("<", "\\u003c")
    # The converted prices' rates credit: fixed HTML outside the scripts, put in before the data goes in.
    credit = f'<p class="muted">{money.CREDIT_HTML}</p>' if money.needs_credit(rates) else ""
    page = PAGE.replace("__LANG__", lang).replace("<!--RATES_CREDIT-->", credit)
    return brand.fill(page, lang).replace("__DATA__", data)


PAGE = r"""<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AirFare</title>
<link rel="icon" href="__FAVICON__">
<style>/*TOKENS*/
/*NAV_CSS*/
:root { --bg:var(--paper); --fg:var(--ink); --accent:var(--sky); --warn-fg:var(--warn); }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 var(--text); }
body::before { content:""; display:block; height:6px; background:var(--stripe); }
main { max-width:1080px; margin:0 auto; padding:24px 16px 56px; }
h2 { font:600 19px/1.2 var(--display); margin:0 0 10px; }
p { margin:0; } a { color:var(--accent); }
.muted { color:var(--muted); font-size:13px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:18px; }
.filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; align-items:end; }
label.f { display:flex; flex-direction:column; gap:4px; font-size:13px; color:var(--muted); min-width:0; }
input, select, button { font:inherit; color:inherit; }
input[type=date], select { background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:7px 9px; width:100%; min-width:0; }
.btn { border:1px solid var(--line); background:var(--card); border-radius:8px; padding:7px 14px; cursor:pointer; }
.btn:hover { background:var(--soft); } .btn.danger { color:var(--bad); } .btn.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.btn:disabled { opacity:.5; cursor:default; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:16px 0; }
.kpi { background:var(--soft); border-radius:10px; padding:12px 14px; min-width:0; }
.kpi .lab { font-size:12px; color:var(--muted); } .kpi .val { font:600 26px var(--display); font-variant-numeric:tabular-nums; }
.kpi .sub { font-size:12px; color:var(--muted); overflow-wrap:anywhere; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin-bottom:4px; }
.legend i { width:16px; height:0; display:inline-block; vertical-align:middle; margin-right:6px; }
svg.chart { width:100%; height:auto; display:block; }
svg .grid { stroke:var(--line); } svg .ax { fill:var(--muted); font-size:11px; } svg .end { fill:var(--fg); font-size:12px; font-weight:600; }
svg .pt { stroke:var(--card); stroke-width:2; }
.tablewrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
th, td { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; white-space:nowrap; }
th { color:var(--muted); font-weight:600; } tr.low td { background:var(--warn-bg); }
td.x button { border:0; background:transparent; color:var(--muted); cursor:pointer; font-size:16px; }
td .site { color:var(--muted); font-size:12px; margin-left:4px; }
.actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
.result { border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin-top:10px; }
.result.found { border-color:var(--ok); } .result .big { font:600 24px var(--display); }
.result .none { font-size:18px; font-weight:600; }
.spinner { display:inline-block; width:12px; height:12px; border:2px solid var(--line); border-top-color:var(--accent);
  border-radius:50%; animation:spin .8s linear infinite; vertical-align:-1px; margin-right:6px; }
@keyframes spin { to { transform:rotate(360deg); } }
.note { background:var(--soft); border-radius:10px; padding:10px 14px; font-size:13px; margin-bottom:16px; }
label.check { display:flex; align-items:center; gap:8px; font-size:14px; padding-bottom:8px; cursor:pointer; }
</style></head>
<body><main>
<!--TOP:history-->
<p class="note" id="file-note" hidden data-i18n-html="html:history-disk">Opened from disk: browsing works, but to delete records or run a lookup, open <strong>Price history</strong> from AirFare Settings.</p>

<section class="card">
  <h2 data-i18n>Conditions</h2>
  <div class="filters">
    <label class="f"><span data-i18n>Route</span> <select id="route"></select></label>
    <label class="f"><span data-i18n>Depart from</span> <input type="date" id="df"></label>
    <label class="f"><span data-i18n>Depart until</span> <input type="date" id="dt"></label>
    <label class="f ret"><span data-i18n>Return from</span> <input type="date" id="rf"></label>
    <label class="f ret"><span data-i18n>Return until</span> <input type="date" id="rt"></label>
    <label class="f"><span data-i18n>Source</span> <select id="src"><option value="" data-i18n>All sources</option><option>Skyscanner</option><option>Aviasales</option><option>Google Flights</option></select></label>
    <button class="btn" id="reset" data-i18n>Use the route's dates</button>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="legend" id="legend"></div>
  <div id="chart"></div>
</section>

<section class="card">
  <h2 data-i18n>Lowest price in the past 2 years</h2>
  <div class="filters served" id="lookup-opts">
    <label class="f"><span data-i18n>Analyst</span> <select id="lk-provider"></select></label>
    <label class="f"><span data-i18n>Model</span> <select id="lk-model"></select></label>
    <label class="check" id="lk-web-wrap"><input type="checkbox" id="lk-web" checked> <span data-i18n>Search the web</span></label>
  </div>
  <p class="muted" id="lookup-intro" style="margin-top:10px"></p>
  <div class="actions"><button class="btn primary" id="lookup"></button><span class="muted" id="lookup-msg"></span></div>
  <div id="lookups"></div>
</section>

<section class="card">
  <h2 id="rec-title"></h2>
  <div class="tablewrap"><table><thead><tr><th data-i18n>Seen</th><th data-i18n>Source</th><th data-i18n>Depart</th><th data-i18n>Return</th><th data-i18n>Price</th><th data-i18n>Airlines</th><th data-i18n>Stops</th><th data-i18n>Travel time</th><th></th><th class="del"></th></tr></thead><tbody id="rows"></tbody></table></div>
  <div class="actions"><button class="btn" id="csv" data-i18n>Export CSV</button><span class="served"><button class="btn danger" id="del-shown"></button> <button class="btn danger" id="del-route" data-i18n>Delete all history for this route</button></span></div>
</section>
<!--RATES_CREDIT-->
</main>
<!--NAV_SCRIPT-->
<script type="application/json" id="data">__DATA__</script>
<script>
let D = JSON.parse(document.getElementById("data").textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let LANG = D.lang || "en";
const LOCALE = {en: "en-GB", es: "es-ES", ru: "ru-RU"};
const fill = (s, p) => String(s).replace(/\{(\w+)\}/g, (m, k) => (p && k in p ? p[k] : m));
const t = (text, p) => fill(((D.texts[LANG] || {})[text]) || text, p);
function tn(n, forms, p) {
  const o = (((D.texts[LANG] || {})[forms]) || forms).split("|");
  let i = n === 1 ? 0 : 1;
  if (LANG === "ru") i = n % 10 === 1 && n % 100 !== 11 ? 0 : (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? 1 : 2);
  return fill(o[Math.min(i, o.length - 1)], {n, ...p});
}
function translateStatic() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    if (!el.dataset.en) el.dataset.en = el.textContent.replace(/\s+/g, " ").trim();
    el.textContent = t(el.dataset.en);
  });
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    if (!el.dataset.enHtml) el.dataset.enHtml = el.innerHTML;
    el.innerHTML = LANG === "en" ? el.dataset.enHtml : ((D.texts[LANG] || {})[el.dataset.i18nHtml] || el.dataset.enHtml);
  });
}
function day(iso) {
  const d = new Date(String(iso || "").slice(0, 10) + "T12:00:00");
  return iso && !isNaN(d) ? d.toLocaleDateString(LOCALE[LANG], {weekday:"short", day:"numeric", month:"short", year:"numeric"}) : "—";
}
const dur = m => `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
const stops = n => n === 0 ? t("direct") : tn(n, "{n} stop|{n} stops");
const SOURCES = ["Skyscanner", "Aviasales", "Google Flights"];
const COLORS = {"Skyscanner": "var(--s1)", "Aviasales": "var(--s3)", "Google Flights": "var(--s2)"};
const DASH = {"Skyscanner": "", "Aviasales": "2 4", "Google Flights": "6 4"};
const NBSP = String.fromCharCode(160);
function money(v) {      // as money.fmt does: €214, $230, 15 400 ₽, 1 234 Kč
  const s = Math.round(v).toLocaleString("en-US"), sign = D.sign || D.currency;
  if (D.sign_after) return s.replace(/,/g, NBSP) + NBSP + sign;
  return sign !== D.currency ? sign + s : s + " " + D.currency;
}
if (!D.served) { document.querySelectorAll(".served, .del").forEach(e => e.hidden = true); $("#file-note").hidden = false; $("#lookup").hidden = true; }

function route() { return D.routes.find(r => r.id === $("#route").value) || D.routes[0]; }
function setDates(r) { $("#df").value = r.depart_from; $("#dt").value = r.depart_to; $("#rf").value = r.return_from; $("#rt").value = r.return_to; }
function filtered() {
  const r = route(); if (!r) return [];
  const df = $("#df").value, dt = $("#dt").value, rf = $("#rf").value, rt = $("#rt").value, src = $("#src").value;
  return D.records.filter(x => x.route_id === r.id && (!src || x.source === src)
    && (!df || (x.depart || "") >= df) && (!dt || (x.depart || "") <= dt)
    && (!r.return || ((!rf || (x.return || "") >= rf) && (!rt || (x.return || "") <= rt))));
}

function render() {
  const r = route();
  document.querySelectorAll(".ret").forEach(e => e.hidden = !(r && r.return));
  const recs = filtered().sort((a, b) => b.time.localeCompare(a.time) || a.price - b.price);
  // The all-time low, first time it was seen.
  const low = recs.reduce((m, x) => !m || x.price < m.price || (x.price === m.price && x.time < m.time) ? x : m, null);
  const latestTime = recs.length ? recs[0].time : null;
  const latest = recs.filter(x => x.time === latestTime).reduce((m, x) => !m || x.price < m.price ? x : m, null);
  const first = recs.length ? recs[recs.length - 1].time : null;
  const tile = (lab, val, sub) => `<div class="kpi"><p class="lab">${esc(lab)}</p><p class="val">${esc(val)}</p><p class="sub">${esc(sub)}</p></div>`;
  $("#kpis").innerHTML = !recs.length ? `<p class="muted">${esc(t("No prices recorded for these conditions yet."))}</p>` :
    tile(t("All-time cheapest"), low.price_text, `${low.source} · ${t("seen {when}", {when: low.time.replace("T", " ")})} · ${day(low.depart)}${low.return ? " → " + day(low.return) : ""} · ${low.airlines}`)
    + tile(t("Latest check"), latest.price_text, `${latest.source} · ${latest.time.replace("T", " ")}`)
    + tile(t("Records"), String(recs.length), first ? t("since {when}", {when: first.replace("T", " ")}) : "")
    + tile(t("Above the all-time low"), latest.price > low.price ? `+${money(latest.price - low.price)}` : t("at the low"), t("latest check vs all-time cheapest"));
  $("#legend").innerHTML = SOURCES.map(s => `<span><i style="border-top:2px ${DASH[s] ? "dashed" : "solid"} ${COLORS[s]}"></i>${esc(t("{source} cheapest", {source: s}))}</span>`).join("");
  chart(recs);
  $("#rec-title").textContent = t("Records ({n})", {n: recs.length});
  $("#rows").innerHTML = recs.map(x => `<tr class="${low && x.id === low.id ? "low" : ""}"><td>${esc(x.time.replace("T", " "))}</td><td>${esc(x.source)}</td>
    <td>${esc(day(x.depart))}</td><td>${esc(x.return ? day(x.return) : t("one-way"))}</td><td><strong>${esc(x.price_text)}</strong>${x.site_price ? `<span class="site">${esc(x.site_price)}</span>` : ""}</td>
    <td>${esc(x.airlines)}</td><td>${esc(stops(x.stops))}</td><td>${dur(x.minutes || 0)}</td>
    <td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(t("open"))}</a>` : ""}</td>
    <td class="x del" ${D.served ? "" : "hidden"}><button title="${esc(t("Delete this record"))}" aria-label="${esc(t("Delete this record"))}" data-id="${esc(x.id)}">×</button></td></tr>`).join("");
  $("#del-shown").textContent = tn(recs.length, "Delete the {n} record shown|Delete the {n} records shown");
  $("#del-shown").disabled = !recs.length;
  renderLookupOpts();
  renderLookups();
}

// ----- which analyst, model and mode the lookup uses ----------------------------------------
const LK = D.lookup;
function provider() { return LK.providers.find(p => p.id === $("#lk-provider").value) || LK.providers[0]; }
function savedPick() { try { return JSON.parse(localStorage.getItem("airfare.lookup") || "null"); } catch (e) { return null; } }
function rememberPick() {
  try { localStorage.setItem("airfare.lookup", JSON.stringify({provider: $("#lk-provider").value, model: $("#lk-model").value, web: $("#lk-web").checked})); }
  catch (e) { /* private window: just don't remember */ }
}
function fillProviders() {
  const keep = $("#lk-provider").value;
  $("#lk-provider").innerHTML = LK.providers.map(p => `<option value="${esc(p.id)}">${esc(p.name)}${p.available ? "" : " (" + esc(t("needs an API key")) + ")"}</option>`).join("");
  if (keep) $("#lk-provider").value = keep;
}
function fillModels(model) {
  const p = provider();
  $("#lk-model").innerHTML = p.models.map(([id, label]) => `<option value="${esc(id)}">${esc(t(label))}</option>`).join("");
  const fallback = p.id === LK.default.provider ? LK.default.model : p.models[0][0];
  $("#lk-model").value = p.models.some(m => m[0] === model) ? model : fallback;
}
function webOn() { return provider().can_browse && $("#lk-web").checked; }
function renderLookupOpts() {
  const p = provider(), label = ($("#lk-model").selectedOptions[0] || {}).textContent || "";
  $("#lk-web-wrap").hidden = !p.can_browse;
  $("#lookup").textContent = t("Search the lowest price with {name} {model}", {name: p.name, model: label});
  $("#lookup").disabled = !p.available;
  const how = webOn() ? t("{name} searches the web for the lowest price recorded in the past two years for exactly this route and these dates.", {name: p.name})
    : p.can_browse ? t("{name} answers only from what it already knows, without searching the web; expect \"No information\" most of the time.", {name: p.name})
    : t("{name}'s API can't browse the web, so it can only cite sources it already knows; expect \"No information\" most of the time.", {name: p.name});
  $("#lookup-intro").textContent = (p.available ? "" : t(p.note) + " ") + how + " "
    + t("A price is shown only if it is for these airports and dates, was recorded in the window, and AirFare finds it quoted on the cited page. Otherwise: No information.")
    + " " + t("Prices in another currency are converted to {currency}.", {currency: D.currency});
}
fillProviders();
{
  const pick = savedPick() || LK.default;
  $("#lk-provider").value = LK.providers.some(p => p.id === pick.provider) ? pick.provider : LK.default.provider;
  fillModels(pick.provider === $("#lk-provider").value ? pick.model : null);
  $("#lk-web").checked = pick.web !== false;
}
$("#lk-provider").onchange = () => { fillModels(null); renderLookupOpts(); rememberPick(); };
$("#lk-model").onchange = () => { renderLookupOpts(); rememberPick(); };
$("#lk-web").onchange = () => { renderLookupOpts(); rememberPick(); };

function chart(recs) {
  const byTime = {};
  recs.forEach(x => { const s = byTime[x.time] ||= {}; s[x.source] = Math.min(s[x.source] ?? Infinity, x.price); });
  const times = Object.keys(byTime).sort().slice(-60);
  if (times.length < 2) { $("#chart").innerHTML = `<p class="muted">${esc(t("The trend appears after two checks with these conditions."))}</p>`; return; }
  const sources = SOURCES.filter(s => times.some(x => byTime[x][s] != null));
  const vals = times.flatMap(x => sources.map(s => byTime[x][s]).filter(v => v != null));
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = Math.max((hi - lo) * .15, 3); lo = Math.max(lo - pad, 0); hi += pad;
  const W = 640, H = 210, L = 56, R = 70, T = 14, B = 26, n = times.length;
  const x = i => L + (W - L - R) * (n > 1 ? i / (n - 1) : .5), y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  let s = "";
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${esc(money(v))}</text>`; }
  const step = Math.max(1, Math.round(n / 6));
  const sameDay = new Set(times.map(x => x.slice(0, 10))).size === 1;
  const label = x => sameDay ? x.slice(11, 16) : new Date(x.slice(0, 10) + "T12:00:00").toLocaleDateString(LOCALE[LANG], {day: "numeric", month: "short"});
  times.forEach((tm, i) => { if (i % step === 0 || i === n - 1) s += `<text class="ax" x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(label(tm))}</text>`; });
  sources.forEach(src => {
    const pts = times.map((tm, i) => byTime[tm][src] != null ? [x(i), y(byTime[tm][src]), byTime[tm][src], tm] : null).filter(Boolean);
    if (pts.length > 1) s += `<polyline points="${pts.map(p => p[0] + "," + p[1]).join(" ")}" fill="none" stroke="${COLORS[src]}" stroke-width="2" stroke-dasharray="${DASH[src]}" stroke-linejoin="round"/>`;
    pts.forEach(p => s += `<circle class="pt" cx="${p[0]}" cy="${p[1]}" r="3.5" fill="${COLORS[src]}"><title>${esc(src)}: ${esc(money(p[2]))} (${esc(p[3].replace("T", " "))})</title></circle>`);
    const last = pts[pts.length - 1]; if (last) s += `<text class="end" x="${last[0] + 8}" y="${last[1] + 4}">${esc(money(last[2]))}</text>`;
  });
  $("#chart").innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Cheapest price per check"))}">${s}</svg>`;
}

function renderLookups() {
  const r = route();
  const items = D.research.filter(x => r && x.route_id === r.id).sort((a, b) => b.time.localeCompare(a.time));
  $("#lookups").innerHTML = items.map(x => {
    const c = x.conditions || {};
    const cond = `${day(c.depart_from)} – ${day(c.depart_to)}${c.return_from ? ` · ${t("back")} ${day(c.return_from)} – ${day(c.return_to)}` : ""}`;
    const del = D.served ? `<button class="btn" style="float:right" data-rid="${esc(x.id)}" aria-label="${esc(t("Delete this lookup"))}">${esc(t("Delete"))}</button>` : "";
    const head = `<p class="muted">${esc(x.time.replace("T", " "))} · ${esc(x.analyst)} · ${esc(cond)}${x.cost_usd != null ? ` · $${Number(x.cost_usd) < 0.01 ? Number(x.cost_usd).toFixed(4) : Number(x.cost_usd).toFixed(3)}` : ""}</p>`;
    if (x.status === "found") {
      const shown = x.converted_text && x.converted_currency && String(x.currency || "").toUpperCase() !== x.converted_currency
        ? `${esc(x.converted_text)} <span class="muted">(${esc(x.lowest_price)} ${esc(x.currency || "")})</span>` : `${esc(x.lowest_price)} ${esc(x.currency || "")}`;
      return `<div class="result found">${del}${head}<p class="big">${shown}</p>
      <p>${esc(day(x.depart_date))}${x.return_date ? " → " + esc(day(x.return_date)) : ""} · ${esc(x.origin)} → ${esc(x.destination)} · ${esc(t("recorded {when}", {when: day(x.observed_on)}))}</p>
      <p class="muted">“${esc(x.quote)}” — <a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_name || x.source_url)}</a></p></div>`;
    }
    return `<div class="result">${del}${head}<p class="none">${esc(t("No information"))}</p><p class="muted">${esc(t(x.reason || ""))}${x.notes ? " · " + esc(x.notes) : ""}</p></div>`;
  }).join("");
}

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-AirFare": "1"}, body: JSON.stringify(body)});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ? t(data.error) : t("Request failed ({status})", {status: r.status}));
  return data;
}
async function del(body, question) {
  if (!confirm(question)) return;
  try { const d = await post("/api/history/delete", body); D.records = d.records; D.research = d.research; render(); }
  catch (e) { alert(e.message); }
}

function fillRoutes() {
  const keep = $("#route").value;
  $("#route").innerHTML = D.routes.map(r => `<option value="${esc(r.id)}">${esc(r.name)}${r.active ? "" : " (" + esc(t("no longer tracked")) + ")"}</option>`).join("");
  if (keep) $("#route").value = keep;
}
window.airfareLanguage = lang => {     // the EN · ES · RU links in the top bar
  LANG = lang; translateStatic(); fillRoutes(); fillProviders(); fillModels($("#lk-model").value); render();
};
translateStatic();
fillRoutes();
if (D.routes[0]) setDates(D.routes[0]);
$("#route").onchange = () => { setDates(route()); render(); };
["#df", "#dt", "#rf", "#rt", "#src"].forEach(s => $(s).addEventListener("change", render));
$("#reset").onclick = () => { setDates(route()); render(); };
$("#rows").addEventListener("click", e => { const id = e.target.dataset.id; if (id) del({ids: [id]}, t("Delete this record?")); });
$("#lookups").addEventListener("click", e => { const id = e.target.dataset.rid; if (id) del({research_ids: [id]}, t("Delete this lookup result?")); });
$("#del-shown").onclick = () => { const ids = filtered().map(x => x.id); del({ids}, tn(ids.length, "Delete the {n} record shown? This can't be undone.|Delete the {n} records shown? This can't be undone.")); };
$("#del-route").onclick = () => {
  if (route()) del({route_id: route().id}, t("Delete all price history for {name}? This can't be undone.", {name: route().name}));
};
$("#csv").onclick = () => {      // the records shown, as a spreadsheet file (works opened from disk too)
  const recs = filtered().sort((a, b) => a.time.localeCompare(b.time) || a.price - b.price);
  const head = ["seen", "source", "route", "origin", "destination", "depart", "return", "price", "currency", "site_price",
                "airlines", "stops", "minutes", "url"];
  const cell = v => { const s = String(v ?? ""); return /[",;\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const rows = recs.map(x => [x.time.replace("T", " "), x.source, x.route_name, x.origin, x.destination, x.depart, x.return || "",
                              x.price, D.currency, x.site_price || "", x.airlines, x.stops, x.minutes, x.url || ""]);
  const csv = "\uFEFF" + [head, ...rows].map(r => r.map(cell).join(",")).join("\r\n");   // the BOM makes Excel read UTF-8
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
  a.download = ("airfare-" + ((route() || {}).name || "prices")).replace(/[^\w.-]+/g, "_") + ".csv";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$("#lookup").onclick = async () => {
  if (!route()) return;    // no routes and no recorded prices yet
  const b = $("#lookup"), m = $("#lookup-msg"), p = provider(); b.disabled = true;
  m.innerHTML = `<span class="spinner"></span>${esc(webOn() ? t("{name} is searching… this can take a minute or two.", {name: p.name}) : t("{name} is answering… this can take a minute or two.", {name: p.name}))}`;
  try {
    const d = await post("/api/history/research", {route_id: route().id, depart_from: $("#df").value, depart_to: $("#dt").value,
                                                   return_from: $("#rf").value, return_to: $("#rt").value,
                                                   provider: p.id, model: $("#lk-model").value, web: webOn()});
    D.research = d.research; m.textContent = d.result.status === "found" ? t("Found a verified price.") : t("No information.");
    renderLookups();
  } catch (e) { m.textContent = e.message; }
  b.disabled = false;
};
render();
</script>
</body></html>
"""
