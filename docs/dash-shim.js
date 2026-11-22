// Minimal runtime for the snapshot page: loads the JSON data files and runs the page's
// calculations (dash.calc) and drawings (dash.draw). Mirrors the small part of the
// claude.ai dashboard API that index.html uses, so the same page code runs on any static host.
(function () {
  const SOURCES = {
    counts: 'data/counts.json', outcomes: 'data/outcomes.json', roster: 'data/roster.json',
    rounds: 'data/rounds.json', label_checks: 'data/label_checks.json', formd_match: 'data/formd_match.json',
    vintages: 'data/vintages.json', snapshots: 'data/snapshots.json', funds: 'data/funds.json',
    current_signals: 'data/current_signals.json', alumni_status: 'data/alumni_status.json'
  };
  const store = {}, calcs = {}, draws = {};
  let ready = false;
  const rowsOf = (v) => (Array.isArray(v) ? v : v && Array.isArray(v.rows) ? v.rows : v);

  function run(name) {
    const fn = draws[name];
    if (!fn) return;
    document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
      try { fn(el); } catch (e) { console.error('draw', name, e); }
    });
  }
  const runAll = () => Object.keys(draws).forEach(run);

  const dash = {
    colors: ['var(--pv-bar-hi)', 'var(--pv-bar)'],
    calc(id, o) { calcs[id] = o; },
    data(id) {
      if (id in SOURCES) {
        if (!ready) return {status: 'loading', data: []};
        return id in store ? {status: 'ok', data: store[id]} : {status: 'error', data: []};
      }
      const c = calcs[id];
      if (!c) return {status: 'missing', data: []};
      if (!ready) return {status: 'loading', data: null};
      const ins = c.inputs.map((i) => dash.data(i));
      const bad = ins.find((g) => g.status !== 'ok');
      if (bad) return {status: bad.status, data: null};
      try { return {status: 'ok', data: c.fn(...ins.map((g) => g.data))}; } catch (e) { console.error('calc', id, e); return {status: 'error', data: null}; }
    },
    draw(name, fn) { if (fn) { draws[name] = fn; if (ready) run(name); } else run(name); },
    onData(fn) { fn(); },
    params() { return {}; }, setParams() {}, resetParams() {}, setLink() {}, loader() {}, refresh() {}
  };
  window.dash = dash;

  async function load() {
    await Promise.all(Object.entries(SOURCES).map(async ([id, url]) => {
      try { const r = await fetch(url); if (r.ok) store[id] = rowsOf(await r.json()); } catch (e) { console.error('load', id, e); }
    }));
    ready = true;
    runAll();
  }
  document.addEventListener('DOMContentLoaded', () => { runAll(); load(); });
  let w = window.innerWidth, t;
  window.addEventListener('resize', () => {
    if (Math.abs(window.innerWidth - w) < 3) return;
    w = window.innerWidth; clearTimeout(t); t = setTimeout(runAll, 120);
  });
  // Charts inside the closed appendix measure zero width until it opens.
  document.addEventListener('toggle', () => runAll(), true);
})();
