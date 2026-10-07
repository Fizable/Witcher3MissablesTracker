// Backend access. In Tauri: invoke/listen. In a plain browser: mock files in ./mock.
'use strict';
const Api = (() => {
  const T = window.__TAURI__;
  if (T && T.core) {
    return {
      mock: false,
      get_view: () => T.core.invoke('get_view'),
      get_detail: (id) => T.core.invoke('get_detail', { id }),
      search: (q) => T.core.invoke('search', { q }),
      check_quest: (short) => T.core.invoke('check_quest', { short }),
      toggle_tick: (id) => T.core.invoke('toggle_tick', { id }),
      set_level: (level) => T.core.invoke('set_level', { level }),
      set_flag: (flag, value) => T.core.invoke('set_flag', { flag, value }),
      set_folder: (kind, path) => T.core.invoke('set_folder', { kind, path }),
      pick_folder: (kind) => T.core.invoke('pick_folder', { kind }),
      set_pin: (pin) => T.core.invoke('set_pin', { pin }),
      open_url: (url) => T.core.invoke('open_url', { url }),
      onView: (cb) => T.event.listen('view', (e) => cb(e.payload)),
    };
  }

  // ---- mock backend ----
  const files = {};
  const load = (n) => (files[n] ||= fetch('mock/' + n + '.json').then((r) => r.json()));
  let view = null;
  const overrides = new Map(); // id -> original status (non-manual steps the user forced to Done)
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const ensure = async () => (view ||= clone(await load('view')));
  const stepOf = (id) => view.steps.find((s) => s.id === id);

  return {
    mock: true,
    async set_flag() { return ensure(); },
    async set_folder() { return ensure(); },
    async pick_folder() { return ensure(); },
    async get_view() { await ensure(); return clone(view); },
    async get_detail(id) {
      await ensure();
      const d = clone((await load('details'))[id] || { step: stepOf(id), kb: null, guide: null, tracking: '', overridden: false });
      const s = stepOf(id);
      if (s) d.step = clone(s);
      d.overridden = overrides.has(id);
      return d;
    },
    async search(q) {
      q = q.toLowerCase();
      const idx = await load('search_index');
      const hit = (x) => x.display.toLowerCase().includes(q) || x.short.toLowerCase().includes(q);
      return idx.filter(hit).sort((a, b) =>
        (b.display.toLowerCase().startsWith(q) - a.display.toLowerCase().startsWith(q)) || a.display.localeCompare(b.display));
    },
    async check_quest(short) { return (await load('verdicts'))[short]; },
    async toggle_tick(id) {
      await ensure();
      const s = stepOf(id);
      if (s) {
        if (s.manual) s.status = s.status === 'Done' ? 'Not started' : 'Done';
        else if (overrides.has(id)) { s.status = overrides.get(id); overrides.delete(id); }
        else { overrides.set(id, s.status); s.status = 'Done'; }
        view.todo = view.todo.filter((x) => stepOf(x).status !== 'Done');
      }
      return clone(view);
    },
    async set_level(level) { await ensure(); view.level = level; return clone(view); },
    async set_pin() {},
    async open_url(url) { window.open(url, '_blank', 'noopener'); },
    onView() {},
  };
})();
