// Built from extension/background.js by tools/make_firefox.py: change that file and run the tool again.
// AirFare collector. When the AirFare app on this PC has a job, open its Skyscanner and Aviasales pages
// in a minimized window, wait for the prices to load, read them, send them back and close those tabs.
// It only ever closes tabs it opened itself; your own tabs and windows are never touched.
const SERVER = "http://127.0.0.1:8766";
const CAPTURE_ID = "airfare-capture";
const ROBOT_MARKERS = ["are you a person or a robot", "press & hold", "press and hold", "вы не робот",
                       "подтвердите, что вы человек"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let busy = false;

// A job comes from whatever answers on AirFare's port, so the extension opens only Skyscanner and Aviasales
// pages from its own site list (manifest.json) and never any other address.
const SITES = browser.runtime.getManifest().host_permissions.filter((p) => p.startsWith("https://"));
// ...and only their search result pages: Skyscanner /x/y/<from>/<to>/<yymmdd>[/<yymmdd>]/, Aviasales /search/<code>.
const SKYSCANNER_SEARCH = /^\/[^/]+\/[^/]+\/[a-z0-9]{2,8}\/[a-z0-9]{2,8}\/\d{6}(\/\d{6})?(\/|$)/i;
const AVIASALES_SEARCH = /^\/search\/[A-Za-z0-9]{6,40}$/;
function validJob(job) {
  const ours = (url) => {
    try {
      const u = new URL(url);
      const search = u.host.includes("aviasales") ? AVIASALES_SEARCH : SKYSCANNER_SEARCH;
      return u.protocol === "https:" && !u.username && !u.password && SITES.includes(`https://${u.host}/*`) &&
        search.test(u.pathname);
    } catch (e) {
      return false;
    }
  };
  return Boolean(job) && typeof job.id === "string" && Array.isArray(job.pages) && job.pages.length > 0 &&
    job.pages.length <= 120 && job.pages.every((p) => p && typeof p.url === "string" && ours(p.url)) &&
    Array.isArray(job.matches) && job.matches.every((m) => SITES.includes(m));
}

browser.runtime.onInstalled.addListener(start);
browser.runtime.onStartup.addListener(start);
browser.alarms.onAlarm.addListener((a) => { if (a.name === "airfare-poll") poll(); });
browser.alarms.get("airfare-poll").then((a) => { if (!a) start(); });

function start() {
  browser.alarms.create("airfare-poll", { periodInMinutes: 1 });
  poll();
}

async function poll() {
  if (busy) return;
  let job;
  try {
    const r = await fetch(`${SERVER}/job`, {
      cache: "no-store",
      headers: { "X-AirFare-Extension": browser.runtime.getManifest().version },
    });
    if (r.status !== 200) return;
    job = await r.json();
  } catch (e) {
    return;   // AirFare isn't running right now
  }
  if (!validJob(job)) return;
  busy = true;
  try {
    const pages = await collect(job);
    await send("/results", { id: job.id, pages });
  } catch (e) {
    await send("/results", { id: job.id, error: String((e && e.message) || e) }).catch(() => {});
  } finally {
    busy = false;
  }
}

function send(path, body) {
  return fetch(SERVER + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function collect(job) {
  await browser.scripting.unregisterContentScripts({ ids: [CAPTURE_ID] }).catch(() => {});
  await browser.scripting.registerContentScripts([{
    id: CAPTURE_ID, matches: job.matches, js: ["capture.js"],
    runAt: "document_start", world: "MAIN", persistAcrossSessions: false,
  }]);
  const opened = [];   // ids of the flight tabs this job opens: the only tabs it may close
  try {
    const win = await browser.windows.create({ url: job.pages.map((p) => p.url), state: "minimized", focused: false });
    const tabs = win.tabs || (await browser.tabs.query({ windowId: win.id }));
    opened.push(...tabs.map((t) => t.id));
    const state = job.pages.map((p, i) => ({ page: p, tabId: tabs[i].id, started: Date.now(), blocked: false }));

    await baseWait(job, win.id, state);
    const extraUntil = Date.now() + job.extra_seconds * 1000;
    while (Date.now() < extraUntil) {
      const done = await Promise.all(state.map((s) => s.blocked || feedComplete(s.tabId)));
      if (done.every(Boolean)) break;
      await sleep(1000);
    }
    return await Promise.all(state.map(read));
  } finally {
    await closeOwnTabs(opened, job).catch(() => {});
    await browser.scripting.unregisterContentScripts({ ids: [CAPTURE_ID] }).catch(() => {});
  }
}

const isStartPage = (t) => (t.pendingUrl || t.url || "").startsWith(`${SERVER}/start`);

// Close the flight tabs and AirFare's "starting Chrome" page, nothing else. A tab you opened in AirFare's
// window (or a link Chrome put there) keeps the window open. When AirFare's tabs are all Chrome has open,
// one AirFare page stays instead: closing Chrome's last window would make Chrome remember the flight pages
// as your last session, in place of the tabs it offers to restore.
async function closeOwnTabs(opened, job) {
  const all = await browser.tabs.query({});
  const ours = new Set([...opened, ...all.filter(isStartPage).map((t) => t.id)]);
  const windows = await browser.windows.getAll({ populate: true, windowTypes: ["normal"] });
  const yoursOpen = windows.some((w) => (w.tabs || []).some((t) => !ours.has(t.id)));
  let keep = null;
  if (!yoursOpen) {
    const start = all.find(isStartPage);
    if (start) keep = start.id;
    else if (opened.length) {
      const first = all.find((t) => t.id === opened[0]);
      const lang = ["en", "es", "ru"].includes(job.lang) ? job.lang : "en";
      const done = await browser.tabs.create({ windowId: first ? first.windowId : undefined, active: true,
                                              url: browser.runtime.getURL(`done.html?lang=${lang}`) });
      keep = done.id;
    }
  }
  const close = all.filter((t) => ours.has(t.id) && t.id !== keep).map((t) => t.id);
  if (close.length) await browser.tabs.remove(close);
}

async function baseWait(job, winId, state) {
  let until = Date.now() + job.wait_seconds * 1000;
  const gaveUp = new Set();   // sites whose robot check went unsolved: their other pages don't ask again
  while (Date.now() < until) {
    await sleep(2000);   // the extension API calls below also keep this service worker awake
    for (const s of state) {
      if (s.blocked || !(await isRobot(s.tabId))) continue;
      if (gaveUp.has(s.page.site) || !(await robotHandoff(job, winId, s))) {
        s.blocked = true;
        gaveUp.add(s.page.site);
        continue;
      }
      // One solved check usually clears the others (same cookie): reload them and wait again.
      for (const o of state) if (o !== s && !o.blocked && (await isRobot(o.tabId))) await browser.tabs.reload(o.tabId);
      until = Date.now() + job.wait_seconds * 1000;
    }
  }
}

async function robotHandoff(job, winId, s) {
  if (job.robot_seconds <= 0) return false;
  await send("/progress", { id: job.id, event: "robot", n: s.page.n }).catch(() => {});
  await browser.windows.update(winId, { state: "normal", focused: true });
  await browser.tabs.update(s.tabId, { active: true });
  const until = Date.now() + job.robot_seconds * 1000;
  let solved = false;
  while (Date.now() < until) {
    await sleep(2000);
    if (!(await isRobot(s.tabId))) { solved = true; break; }
  }
  await browser.windows.update(winId, { state: "minimized" }).catch(() => {});
  if (solved) {
    // Back to the search if solving the check landed somewhere else.
    const tab = await browser.tabs.get(s.tabId);
    const path = new URL(tab.url).pathname;
    const onSearch = s.page.site === "Aviasales" ? path.startsWith("/search/") : /\/\d{6}\//.test(path);
    if (!onSearch) await browser.tabs.update(s.tabId, { url: s.page.url });
  }
  return solved;
}

async function isRobot(tabId) {
  try {
    const tab = await browser.tabs.get(tabId);
    if ((tab.url || "").toLowerCase().includes("captcha")) return true;
    const [r] = await browser.scripting.executeScript({
      target: { tabId },
      func: () => (document.title + " " + (document.body ? document.body.innerText.slice(0, 3000) : "")).toLowerCase(),
    });
    return ROBOT_MARKERS.some((m) => ((r && r.result) || "").includes(m));
  } catch (e) {
    return false;
  }
}

async function feedComplete(tabId) {
  try {
    const [r] = await browser.scripting.executeScript({
      target: { tabId }, world: "MAIN",
      func: () => {
        const p = (window.__airfare || {}).payloads || [];
        if (!p.length) return false;
        const last = p[p.length - 1];
        // Aviasales: a results chunk with last_update_timestamp 0 ends the search.
        if (Array.isArray(last)) return p.some((b) => Array.isArray(b) && b.some((c) => c && c.last_update_timestamp === 0));
        const ctx = last.context || (last.itineraries || {}).context || {};
        return ctx.status ? String(ctx.status).toLowerCase() === "complete" : true;
      },
    });
    return Boolean(r && r.result);
  } catch (e) {
    return false;
  }
}

async function read(s) {
  try {
    const tab = await browser.tabs.get(s.tabId);
    const [r] = await browser.scripting.executeScript({
      target: { tabId: s.tabId }, world: "MAIN",
      func: () => ({
        payloads: (window.__airfare || {}).payloads || [],
        text: ((document.querySelector("main") || document.body || {}).innerText || "").slice(0, 15000),
      }),
    });
    const robot = s.blocked || (await isRobot(s.tabId));
    return {
      n: s.page.n, url: tab.url, robot,
      payloads: r.result.payloads, text: robot ? "" : r.result.text,
      seconds: Math.round((Date.now() - s.started) / 100) / 10,
    };
  } catch (e) {
    return { n: s.page.n, error: String((e && e.message) || e) };
  }
}
