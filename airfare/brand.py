"""AirFare's look, shared by every page it writes: colour tokens, type, the logo and the flight-path drawing.

The pages use fonts that ship with Windows (Bahnschrift for headings, codes and prices; Segoe UI for text),
so they look the same online, offline and when opened straight from disk.
"""
from __future__ import annotations

import json
from urllib.parse import quote

from .config import WEBUI_PORT
from .i18n import LANGS, norm, tr

# A top-down airliner, nose pointing right, in a 24x24 box (the same outline as the app icon).
PLANE_PATH = ("M23 12L22.2 12.8 20.8 13 14.6 13 10.1 22.6 8.6 22.6 11 13 5.4 13 2.8 16.3 1.6 16.3 2.5 12.8 2.1 12 "
              "2.5 11.2 1.6 7.7 2.8 7.7 5.4 11 11 11 8.6 1.4 10.1 1.4 14.6 11 20.8 11 22.2 11.2Z")

LOGO_SVG = f"""<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="logo">
<defs><linearGradient id="ssg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#12A39F"/>
<stop offset="1" stop-color="#0A5C5E"/></linearGradient></defs>
<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#ssg)"/>
<path d="M13.4 50.6Q16 35.8 27.5 37.4" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"
 stroke-dasharray="0.1 4.6" opacity=".9"/>
<circle cx="13.4" cy="50.6" r="4.6" fill="#fff"/><circle cx="13.4" cy="50.6" r="3.1" fill="#E5484D"/>
<path d="{PLANE_PATH}" fill="#fff" transform="translate(41 24.3) rotate(-45) scale(1.57) translate(-12 -12)"/>
</svg>"""

FAVICON = "data:image/svg+xml," + quote(LOGO_SVG.replace(' class="logo"', "").replace("\n", ""))

# Colour and type tokens. The airmail stripe (red and blue, like an air-mail envelope) marks the top of
# every page and the LOW PRICE alert.
TOKENS_CSS = """
:root { --paper:#F3F7F7; --card:#FFFFFF; --ink:#13262B; --muted:#56666B; --line:#D6E1E2; --soft:#E8F0F0;
  --sky:#0E8F8B; --sky-ink:#FFFFFF; --sky-soft:#DDF3F1; --red:#D93B30; --ok:#1B7F4B; --bad:#B42318; --warn:#9A5800;
  --warn-bg:#FCF1DC; --s1:#0E8F8B; --s2:#E0782B; --s3:#6A4FD8;
  --display:"Bahnschrift","DIN Alternate","D-DIN","Barlow Semi Condensed","Segoe UI",system-ui,sans-serif;
  --text:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif;
  --stripe:repeating-linear-gradient(-45deg,var(--red) 0 12px,transparent 12px 19px,var(--sky) 19px 31px,transparent 31px 38px); }
@media (prefers-color-scheme: dark) { :root { --paper:#0C1718; --card:#132122; --ink:#E6F0F0; --muted:#93A6A8;
  --line:#24383A; --soft:#182A2B; --sky:#5FD3CF; --sky-ink:#06302E; --sky-soft:#143A39; --red:#FF6B5E; --ok:#5CC98A;
  --bad:#FF8A80; --warn:#F2B45A; --warn-bg:#3A2C10; --s1:#5FD3CF; --s2:#F08A3E; --s3:#A58CFF; } }
"""

# A dashed flight path over a couple of line-drawn clouds, with the plane part-way along it.
SKY_SVG = f"""<svg class="sky" viewBox="0 0 600 140" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".35">
<path d="M70 60h44a12 12 0 0 0-3-23.6 17 17 0 0 0-32.4-4.6A11.5 11.5 0 0 0 70 60z"/>
<path d="M452 128h58a14 14 0 0 0-2.4-27.8 21 21 0 0 0-40-5.2 14 14 0 0 0-15.6 33z"/></g>
<path class="route-line" d="M24 118Q300-36 576 104" fill="none" stroke="currentColor" stroke-width="2"
 stroke-linecap="round" stroke-dasharray="2 9"/>
<circle cx="24" cy="118" r="7" fill="var(--card)" stroke="var(--red)" stroke-width="3"/>
<circle cx="576" cy="104" r="6" fill="var(--card)" stroke="currentColor" stroke-width="2"/>
<g class="fly"><g transform="translate(366 40) rotate(5.9)">
<path d="{PLANE_PATH}" fill="var(--sky)" transform="scale(1.6) translate(-12 -12)"/></g></g>
</svg>"""

# Small line icons for section headings (24x24, drawn with the current text colour).
ICONS = {
    "ticket": '<path d="M3 7.5A1.5 1.5 0 0 0 4.5 6h15A1.5 1.5 0 0 0 21 7.5v2a2.5 2.5 0 0 0 0 5v2a1.5 1.5 0 0 0-1.5 1.5h-15A1.5 1.5 0 0 0 3 16.5v-2a2.5 2.5 0 0 0 0-5z"/><path d="M15 6.5v11" stroke-dasharray="1.5 2.5"/>',
    "radar": '<circle cx="12" cy="12" r="1.8"/><path d="M8.2 15.8a5.4 5.4 0 0 1 0-7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6M5.3 18.7a9.5 9.5 0 0 1 0-13.4M18.7 5.3a9.5 9.5 0 0 1 0 13.4"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "spark": '<path d="M11 3.5l1.7 4.8 4.8 1.7-4.8 1.7L11 16.5l-1.7-4.8L4.5 10l4.8-1.7z"/><path d="M18 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    "sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "trend": '<path d="M4 19.5h16"/><path d="M5 15l4.5-4.5 3.5 3 6-6.5"/><path d="M15.5 7H19v3.5"/>',
    "coin": '<circle cx="12" cy="12" r="8.5"/><path d="M14.8 8.6a4 4 0 1 0 0 6.8M7.6 11h5.4M7.6 13.2h5.4"/>',
    "bell": '<path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.5H5z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
    "broom": '<path d="M19.5 3.5l-7 7"/><path d="M12.5 10.5c-2.6-1-5.2.2-6.5 2.8L4 18.5c2.4.8 5.1 1.3 7.2 1.5l2.3-2.6c1.5-2.4 1.2-5.3-1-6.9z"/><path d="M7.5 15.5l2 2M10 13.5l2.2 2.2"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "chat": '<path d="M4.5 6.5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-6l-4 3.5v-3.5h-1a2 2 0 0 1-2-2z"/>',
    "warning": '<path d="M12 4.5l8.5 15h-17z"/><path d="M12 10v4.5M12 17v.5"/>',
}


# The bar at the top of every page: the logo and the same three tabs, which open in the same browser tab so
# Back and Forward move between them.
NAV_CSS = """
.top { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
.brand { display:flex; align-items:center; gap:10px; } .brand .logo { width:36px; height:36px; flex:none; }
.brand h1 { font:600 28px/1 var(--display); margin:0; letter-spacing:.01em; }
.tabs { display:flex; gap:4px; background:var(--soft); border-radius:10px; padding:3px; }
.tabs a { padding:6px 14px; border-radius:8px; text-decoration:none; color:var(--ink); font-size:14px; }
.tabs a:hover { color:var(--sky); }
.tabs a[aria-current] { background:var(--card); color:var(--ink); font-weight:600; box-shadow:0 1px 2px rgba(20,33,61,.1); }
.tabs a[hidden] { display:none; }
.top-r { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.langs { display:flex; gap:2px; font-size:13px; }
.langs a { padding:4px 7px; border-radius:6px; color:var(--muted); text-decoration:none; letter-spacing:.04em; }
.langs a:hover { color:var(--sky); }
.langs a[aria-current] { color:var(--ink); font-weight:600; background:var(--soft); }
"""
PAGES = (("dashboard", "Dashboard", "latest.html"), ("history", "Price history", "history.html"),
         ("cleanup", "Clean up", "cleanup.html"), ("settings", "Settings", "/"))
LIVE_ONLY = ("cleanup", "settings")      # pages only AirFare's local server can show (no copy on disk)

# The tabs need AirFare's local server, which stops when no page has been open for two minutes, when the
# PC sleeps, or when AirFare is updated. So every live tab first checks that AirFare answers; if not, it
# starts AirFare through its airfare: link (see links.py) and then opens the page in the same browser tab.
# A served page also tells the server it's still in use. A page opened from disk keeps its Dashboard and
# Price history tabs as files and uses the same route for Clean up and Settings.
#
# The language links (EN, ES, RU) save the choice through the server. Settings and Price history switch in
# place (they register window.airfareLanguage), so nothing typed is lost; the dashboard reloads in the new
# language, or, opened from disk, opens its copy in that language (latest-es.html).
NAV_SCRIPT = """<script>
(() => {
  const served = location.protocol.startsWith("http");
  const TEXT = __TABS__;
  const say = (lang, key) => (TEXT[lang] || TEXT.en)[key];
  document.querySelectorAll(".langs a").forEach(a => a.addEventListener("click", e => {
    const lang = a.dataset.lang;
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    try { localStorage.setItem("airfare.lang", lang); } catch (err) { /* private window */ }
    const saved = served ? fetch("/api/language", {method: "POST", body: JSON.stringify({language: lang}),
      headers: {"X-AirFare": "1", "Content-Type": "application/json"}}).catch(() => {}) : Promise.resolve();
    if (window.airfareLanguage) {
      e.preventDefault();
      document.documentElement.lang = lang;
      document.querySelectorAll(".langs a").forEach(x => x.toggleAttribute("aria-current", x === a));
      document.querySelectorAll(".tabs a").forEach((t, i) => { t.textContent = say(lang, "tabs")[i]; });
      window.airfareLanguage(lang);
    } else if (served) {
      e.preventDefault();
      saved.then(() => location.reload());
    }
  }));
  const home = served ? location.origin + "/" : "http://127.0.0.1:__PORT__/";
  const up = () => fetch(home + "api/version", {mode: served ? "same-origin" : "no-cors", cache: "no-store"})
    .then(r => { if (served && !r.ok) throw new Error("not AirFare"); });
  if (served) {
    const beat = () => fetch("/api/heartbeat", {method: "POST", body: "{}",
      headers: {"X-AirFare": "1", "Content-Type": "application/json"}}).catch(() => {});
    beat(); setInterval(beat, 20000);
  }
  document.querySelectorAll(".tabs a").forEach(tab => {
    const live = served || tab.classList.contains("needs-server");
    if (!live) return;
    tab.hidden = false;
    const target = served ? tab.href : new URL(tab.getAttribute("href"), home).href;
    tab.addEventListener("click", e => {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;   // opening in a new tab stays as it was
      e.preventDefault();
      const label = tab.textContent, lang = document.documentElement.lang;
      up().then(() => { location.href = target; }, () => {
        tab.textContent = say(lang, "starting");
        location.href = "airfare:start";
        const until = Date.now() + 60000;     // includes the browser asking whether to open AirFare
        const wait = () => up().then(() => { location.href = target; }, () => {
          if (Date.now() < until) return setTimeout(wait, 800);
          tab.textContent = label;
          alert(say(lang, "failed"));
        });
        setTimeout(wait, 800);
      });
    });
  });
})();
</script>"""
NAV_TEXTS = {"starting": "Starting AirFare…", "failed": "AirFare didn't start. Open it from its desktop or Start menu icon."}
NAV_SCRIPT = NAV_SCRIPT.replace("__PORT__", str(WEBUI_PORT)).replace("__TABS__", json.dumps(
    {lang: {"tabs": [tr(label, lang) for _, label, _ in PAGES], **{k: tr(t, lang) for k, t in NAV_TEXTS.items()}}
     for lang in LANGS}, ensure_ascii=False))


def nav(current: str, lang: str = "en") -> str:
    links = []
    for key, label, href in PAGES:
        label = tr(label, lang)
        if key == current:
            links.append(f'<a href="{href}" aria-current="page">{label}</a>')
        elif key in LIVE_ONLY:
            links.append(f'<a href="{href}" class="needs-server" hidden>{label}</a>')
        else:
            links.append(f'<a href="{href}">{label}</a>')
    return f'<nav class="tabs" aria-label="AirFare">{"".join(links)}</nav>'


def lang_links(current: str, lang: str) -> str:
    """EN · ES · RU. The dashboard's links point at its copy in each language, for when it opens from disk."""
    lang = norm(lang)
    links = []
    for code, name in LANGS.items():
        href = f"latest-{code}.html" if current == "dashboard" else "#"
        here = ' aria-current="true"' if code == lang else ""
        links.append(f'<a href="{href}" data-lang="{code}" lang="{code}" title="{name}"{here}>{code.upper()}</a>')
    return f'<nav class="langs" aria-label="Language">{"".join(links)}</nav>'


def top_bar(current: str, lang: str = "en") -> str:
    return (f'<div class="top"><div class="brand">{LOGO_SVG}<h1>AirFare</h1></div>'
            f'<div class="top-r">{nav(current, lang)}{lang_links(current, lang)}</div></div>')


def icon(name: str) -> str:
    return (f'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def legal(lang: str = "en") -> str:
    """The line every page ends with: an independent tool, the sites' and providers' names are theirs, and
    prices are to be checked before booking."""
    text = tr("AirFare is an independent, open-source tool. It is not affiliated with or endorsed by Skyscanner, "
              "Aviasales, Google, Anthropic, OpenAI, DeepSeek or SerpApi; their names are trademarks of their owners, "
              "used only to say which service is meant. Prices can be wrong or out of date: check them on the site "
              "before you book.", lang)
    return f'<p class="legal">{text}</p>'


LEGAL_CSS = ".legal { color:var(--muted); font-size:12px; margin:40px 0 0; border-top:1px solid var(--line); padding-top:12px; }"


def fill(page: str, lang: str = "en") -> str:
    """Put the shared pieces into a page that marks them with placeholders."""
    for key, value in (("/*TOKENS*/", TOKENS_CSS + LEGAL_CSS), ("/*NAV_CSS*/", NAV_CSS), ("<!--NAV_SCRIPT-->", NAV_SCRIPT),
                       ("<!--LOGO-->", LOGO_SVG), ("<!--SKY-->", SKY_SVG), ("__FAVICON__", FAVICON),
                       ("__PLANE__", PLANE_PATH), ("<!--LEGAL-->", legal(lang))):
        page = page.replace(key, value)
    for key, _, _ in PAGES:
        page = page.replace(f"<!--TOP:{key}-->", top_bar(key, lang))
    for name in ICONS:
        page = page.replace(f"<!--ICON:{name}-->", icon(name))
    return page
