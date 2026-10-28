// Runs in the page itself (registered only while a AirFare job is running). Keeps a copy of the
// results feed the Skyscanner or Aviasales page downloads, so the extension can read prices without
// parsing the page layout. Nothing leaves the page; the extension reads window.__airfare after the wait.
(() => {
  if (window.__airfare) return;
  const store = (window.__airfare = { payloads: [] });
  const interesting = (url) => /unified-search|itinerar|\/search\/v\d[\d.]*\/results/i.test(String(url || ""));

  // Aviasales sends about a megabyte per poll; keep only what AirFare reads (prices, legs, airlines).
  const slimAviasales = (body) => body.filter((c) => c && Array.isArray(c.tickets) && Array.isArray(c.flight_legs)).map((c) => {
    const used = new Set();
    const ticket = (t) => t && {
      id: t.id, position: t.position, score: t.score,
      segments: (t.segments || []).map((s) => {
        (s.flights || []).forEach((i) => used.add(i));
        return {
          flights: s.flights,
          transfers: (s.transfers || []).map((x) => ({
            recheck_baggage: !!x.recheck_baggage, night_transfer: !!x.night_transfer,
            visa_rules: { required: !!(x.visa_rules && x.visa_rules.required) },
          })),
        };
      }),
      proposals: (t.proposals || []).filter((p) => p && p.price)
        .sort((a, b) => a.price.value - b.price.value).slice(0, 3).map((p) => ({
          price: { currency_code: p.price.currency_code, value: p.price.value },
          flight_terms: Object.fromEntries(Object.entries(p.flight_terms || {}).map(([k, v]) =>
            [k, { marketing_carrier_designator: v && v.marketing_carrier_designator }])),
        })),
    };
    const tickets = c.tickets.map(ticket);
    const cheapest = ticket(c.cheapest_ticket);
    const legs = c.flight_legs.map((l, i) => (used.has(i) && l ? {
      origin: l.origin, destination: l.destination,
      local_departure_date_time: l.local_departure_date_time, local_arrival_date_time: l.local_arrival_date_time,
      departure_unix_timestamp: l.departure_unix_timestamp, arrival_unix_timestamp: l.arrival_unix_timestamp,
      operating_carrier_designator: l.operating_carrier_designator,
    } : {}));
    const airlines = Object.fromEntries(Object.entries(c.airlines || {}).map(([k, a]) => [k, { name: a && a.name }]));
    return {
      chunk_id: c.chunk_id, last_update_timestamp: c.last_update_timestamp, tickets, cheapest_ticket: cheapest,
      flight_legs: legs, airlines, meta: { total_tickets_count: (c.meta || {}).total_tickets_count },
    };
  });

  const keep = (data) => {   // the response as text, or already parsed
    if (typeof data === "string" && data.indexOf("itineraries") < 0 && data.indexOf("flight_legs") < 0) return;
    try {
      let body = typeof data === "string" ? JSON.parse(data) : data;
      if (Array.isArray(body)) {
        body = slimAviasales(body);
        if (!body.length) return;
      } else if (!(body && typeof body === "object" && "itineraries" in body)) {
        return;
      }
      store.payloads.push(body);
      if (store.payloads.length > 3) store.payloads.shift();   // each poll repeats earlier results
    } catch (e) { /* not JSON */ }
  };

  if (/(^|\.)aviasales\./.test(location.hostname)) {
    // Aviasales reads its results with response.text(); copy what it reads instead of fetching twice.
    for (const method of ["text", "json"]) {
      const original = Response.prototype[method];
      Response.prototype[method] = async function (...args) {
        const value = await original.apply(this, args);
        try { if (interesting(this.url)) keep(value); } catch (e) { /* never break the page */ }
        return value;
      };
    }
  } else {
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
      const response = await originalFetch.apply(this, args);
      try {
        if (interesting(response.url)) response.clone().text().then(keep, () => {});
      } catch (e) { /* never break the page */ }
      return response;
    };
  }

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__airfareUrl = url;
    return originalOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    if (interesting(this.__airfareUrl)) {
      this.addEventListener("load", () => {
        try { keep(typeof this.response === "string" ? this.response : JSON.stringify(this.response)); } catch (e) { /* ignore */ }
      });
    }
    return originalSend.apply(this, args);
  };
})();
