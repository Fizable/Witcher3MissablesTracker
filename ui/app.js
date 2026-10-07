// Witcher 3 route tracker UI. Keyed DOM updates: cards/rows are kept in Maps and only
// replaced when their data signature changes; header/search/level inputs are never rebuilt.
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const GLYPH = {
  'White Orchard': '🌾', 'Velen': '🌲', 'Novigrad': '🏛', 'Skellige': '⛵', 'Kaer Morhen': '🏰',
  'Ciri / base game ending': '✦', 'Hearts of Stone': '♠', 'Blood and Wine': '🍷',
};
const ICON = { Done: '✔', Active: '◐', 'Not started': '○', Failed: '✖', Assumed: '✔?', 'N/A': '–' };
const FIRST_N = 4;

// ---------- helpers ----------
function h(tag, cls, text, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null && text !== '') e.textContent = text;
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
const add = (p, ...kids) => { for (const k of kids) if (k) p.append(k); return p; };
const store = {
  get(k, d) { try { const v = localStorage.getItem('w3.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('w3.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
};
const short = (s, n) => (s.length > n ? s.slice(0, n).trimEnd() + '…' : s);
const noParen = (t) => t.replace(/\s*\([^)]*\)\s*/g, ' ').replace(/\s+/g, ' ').trim();
const lvNum = (s) => { const n = parseInt(s.lv, 10); return Number.isFinite(n) ? n : 0; };
const lvlChip = (s) => s.section.toUpperCase() + (s.lv ? ' · L' + s.lv : '');
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Keyed list: keeps one element per key, rebuilds it only when sig changes, keeps order. */
function keyedList(parent) {
  const map = new Map(); // key -> {el, sig}
  return function sync(items, keyOf, sigOf, build) {
    const seen = new Set();
    items.forEach((it, i) => {
      const k = keyOf(it); seen.add(k);
      const sig = JSON.stringify(sigOf(it));
      let rec = map.get(k);
      if (!rec) { rec = { el: build(it), sig }; map.set(k, rec); }
      else if (rec.sig !== sig) { const el = build(it); rec.el.replaceWith(el); rec.el = el; rec.sig = sig; }
      if (parent.children[i] !== rec.el) parent.insertBefore(rec.el, parent.children[i] || null);
    });
    for (const [k, rec] of map) if (!seen.has(k)) { rec.el.remove(); map.delete(k); }
  };
}

// ---------- state ----------
let view = null;
let viewAt = performance.now();
let showAll = store.get('showAll', false);
let collapsed = store.get('collapsed', {});
const stepsById = new Map();
const detailCache = new Map(); // id -> detail
let detailId = null;
let listScroll = 0;

// ---------- header ----------
const el = {
  pin: $('#pin'), level: $('#level'), saveName: $('#saveName'), saveAge: $('#saveAge'), saveError: $('#saveError'),
  q: $('#q'), verdict: $('#verdict'), hits: $('#hits'),
  listPane: $('#listPane'), detailPane: $('#detailPane'), detail: $('#detail'),
};

function fmtAge(secs) {
  secs = Math.max(0, Math.round(secs));
  if (secs < 60) return secs + 's ago';
  const m = Math.floor(secs / 60);
  if (m < 60) return m + 'm ago';
  const hr = Math.floor(m / 60);
  return hr < 48 ? hr + 'h ago' : Math.floor(hr / 24) + 'd ago';
}
function tickAge() {
  if (!view || !view.save || !view.save.name) { el.saveAge.textContent = ''; return; }
  const t = fmtAge(view.save.age_secs + (performance.now() - viewAt) / 1000);
  if (el.saveAge.textContent !== t) el.saveAge.textContent = t;
}
setInterval(tickAge, 1000);

function renderHeader(v) {
  const save = v.save || {};
  const name = save.name || 'no save loaded';
  if (el.saveName.textContent !== name) { el.saveName.textContent = name; el.saveName.title = name; }
  const err = save.error || '';
  el.saveError.classList.toggle('hidden', !err);
  if (el.saveError.textContent !== err) el.saveError.textContent = err;
  // never clobber the level input while the user is typing in it
  if (document.activeElement !== el.level && el.level.value !== String(v.level)) el.level.value = v.level;
  tickAge();
}

// ---------- my game (world-state tags) ----------
const flagsEl = $('#flags');
const flagRows = new Map();
function renderFlags(v) {
  (v.flags || []).forEach((f) => {
    let r = flagRows.get(f.id);
    if (!r) {
      r = { root: h('div', 'flag'), btns: {} };
      const txt = h('div', 'ftxt'); add(txt, h('div', 'fl', f.label), f.note ? h('div', 'dim small', f.note) : null);
      const seg = h('div', 'seg');
      [['yes', 'Yes'], ['no', 'No'], ['', 'Not sure']].forEach(([val, lab]) => {
        const b = h('button', 'segb', lab, { 'data-act': 'flag', 'data-flag': f.id, 'data-val': val });
        r.btns[val] = b; seg.append(b);
      });
      add(r.root, txt, seg); flagsEl.append(r.root); flagRows.set(f.id, r);
    }
    for (const [val, b] of Object.entries(r.btns)) b.classList.toggle('on', val === (f.value || ''));
  });
}

// ---------- folders (game + saves) ----------
const foldersEl = $('#folders');
const folderRows = new Map();
let panelAutoOpened = false;
function renderFolders(v) {
  const f = v.folders;
  if (!f) return;
  [['game', 'Game folder'], ['saves', 'Saves folder']].forEach(([kind, label]) => {
    let r = folderRows.get(kind);
    if (!r) {
      const root = h('div', 'folder'), top = h('div', 'ftop');
      const status = h('span', 'fstat'), path = h('div', 'fpath dim small');
      const inp = h('input', 'finput', null, { type: 'text', placeholder: 'paste a folder path, or press Browse', spellcheck: 'false', 'data-kind': kind });
      const row = h('div', 'frow');
      add(row, inp, h('button', 'btn sm', 'Browse…', { 'data-act': 'browse', 'data-kind': kind }), h('button', 'btn sm', 'Use', { 'data-act': 'usefolder', 'data-kind': kind }));
      add(top, h('span', 'fl', label), status);
      add(root, top, path, row);
      inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') useFolder(kind); });
      foldersEl.append(root);
      r = { status, path, inp };
      folderRows.set(kind, r);
    }
    const x = f[kind] || {};
    const st = x.ok ? '✔ found' : '⚠ not found';
    if (r.status.textContent !== st) { r.status.textContent = st; r.status.className = 'fstat ' + (x.ok ? 'green' : 'red'); }
    const pt = (x.path || 'nothing detected yet') + (x.auto && x.path ? '  (automatic)' : '');
    if (r.path.textContent !== pt) { r.path.textContent = pt; r.path.title = x.path || ''; }
  });
  const m = $('#foldermsg');
  const msg = f.message || '';
  m.classList.toggle('hidden', !msg);
  if (m.textContent !== msg) m.textContent = msg;
  // open the panel once when something needs the user's attention
  if (!panelAutoOpened && ((f.game && !f.game.ok) || (f.saves && !f.saves.ok))) {
    panelAutoOpened = true;
    $('#flagsPanel').classList.remove('hidden');
    const g = $('.gear'); if (g) g.classList.add('on');
  }
}
function useFolder(kind) {
  const r = folderRows.get(kind);
  Api.set_folder(kind, r ? r.inp.value : '').then((v) => { if (r) r.inp.value = ''; render(v); }).catch(console.error);
}

// ---------- alerts / hold off ----------
const alertList = keyedList($('#alerts'));
const holdList = keyedList($('#hold'));

function missingText(list) { return (list || []).map((m) => m.title).join(', '); }

function renderAlerts(v) {
  const alerts = v.alerts || [];
  $('#alertsSec').classList.toggle('hidden', !alerts.length);
  alertList(alerts, (a) => a.level + a.msg, (a) => a, (a) => {
    const c = h('div', 'card accent-' + (a.level === 'stop' ? 'red' : 'amber'));
    add(c, h('div', 'msg', a.msg));
    if (a.missing && a.missing.length) add(c, h('div', 'dim small', 'Still open: ' + missingText(a.missing)));
    return c;
  });
}

function renderHold(v) {
  const hold = v.holdoff || [];
  $('#holdSec').classList.toggle('hidden', !hold.length);
  $('#holdCount').textContent = hold.length ? '· ' + hold.length : '';
  holdList(hold, (x) => x.kind + x.name, (x) => x, (x) => {
    const event = x.kind === 'event';
    const c = h('div', 'card accent-' + (event ? 'red' : 'amber'));
    const label = event ? "DON'T TRIGGER YET" : x.status === 'Active' ? 'PAUSE (already started)' : "DON'T START YET";
    add(c, h('div', 'tag ' + (event ? 'red' : 'amber'), label), h('div', 'title', x.name));
    if (x.why) add(c, h('div', 'why', x.why));
    if (x.missing && x.missing.length) add(c, h('div', 'dim small', 'Do first: ' + missingText(x.missing)));
    return c;
  });
}

// ---------- DO NEXT ----------
const cardList = keyedList($('#todoCards'));
const rowList = keyedList($('#todoRows'));

function buildCard(s, objs) {
  const active = s.status === 'Active';
  const c = h('article', 'card todo accent-' + (active ? 'green' : s.conditional ? 'blue' : 'gold'));
  const top = h('div', 'card-top');
  add(top, h('span', 'chip', lvlChip(s)),
    h('span', 'sidetag ' + (active ? 'green' : 'dim'), active ? 'in your quest log' : s.conditional ? 'only if it exists in your game' : 'not in your log yet'));
  add(c, top, h('button', 'title link', s.title, { 'data-act': 'detail', 'data-id': s.id }));

  if (active && objs.length) {
    const ul = h('ul', 'bul');
    objs.forEach((o) => add(ul, h('li', '', o)));
    add(c, h('div', 'lbl', 'IN YOUR QUEST LOG NOW'), ul);
  } else if (s.start) {
    add(c, h('div', 'lbl', 'HOW TO START'), h('div', 'txt', short(s.start, 190)));
  } else if (s.manual) {
    add(c, h('div', 'dim small', 'Not visible in the save: tick it yourself when done.'));
  }
  if (s.note) add(c, h('div', 'lbl gold', "DON'T MISS"), h('div', 'txt', s.note));

  const foot = h('div', 'card-foot');
  const need = lvNum(s);
  if (view.level > 0 && need && view.level < need - 2) add(foot, h('span', 'amber small', 'level ' + need + ' suggested'));
  if (s.conf === 'low' || s.conf === 'med') add(foot, h('span', 'dim small', 'quest match: ' + s.conf));
  add(foot, h('span', 'grow'), h('button', 'btn sm', 'how?', { 'data-act': 'detail', 'data-id': s.id }));
  if (s.manual) add(foot, h('button', 'btn sm', 'mark done', { 'data-act': 'tick', 'data-id': s.id }));
  else add(foot, h('span', 'dim small', 'tracked from your save'));
  add(c, foot);
  return c;
}

function buildRow(s, rank) {
  const b = h('button', 'row', null, { 'data-act': 'detail', 'data-id': s.id });
  const st = s.status === 'Active' ? 'in your log' : s.conditional ? 'if it exists' : 'not in log';
  add(b, h('span', 'rank dim', String(rank)), h('span', 'rtitle', noParen(s.title)),
    h('span', 'dim small rreg', s.section), h('span', 'small ' + (s.status === 'Active' ? 'green' : 'dim'), st));
  return b;
}

function renderTodo(v) {
  const ids = (v.todo || []).filter((id) => stepsById.has(id));
  const first = ids.slice(0, FIRST_N), rest = ids.slice(FIRST_N);
  $('#todoEmpty').classList.toggle('hidden', ids.length > 0);
  cardList(first, (id) => id, (id) => [stepsById.get(id), v.objectives[id] || [], v.level],
    (id) => buildCard(stepsById.get(id), v.objectives[id] || []));
  const rank = new Map(ids.map((id, i) => [id, i + 1]));
  rowList(rest, (id) => id, (id) => [stepsById.get(id), rank.get(id)], (id) => buildRow(stepsById.get(id), rank.get(id)));
  $('#todoToggle').classList.toggle('hidden', !rest.length);
  $('#todoMore').classList.toggle('closed', !showAll || !rest.length);
  $('#todoToggle').textContent = showAll
    ? '▴ show only the first ' + FIRST_N
    : '▾ show all ' + ids.length + ' (+' + rest.length + ' more)';
}

// ---------- PROGRESS ----------
const sectionRecs = new Map(); // name -> {root, head parts, rows sync}
const sectionsEl = $('#sections');

function buildRow2(s) {
  const r = h('div', 'prow');
  const icon = h('button', 'picon', null, { 'data-act': 'tick', 'data-id': s.id });
  const title = h('button', 'ptitle', null, { 'data-act': 'detail', 'data-id': s.id });
  add(r, icon, title);
  patchRow(r, s);
  return r;
}
function patchRow(r, s) {
  const [icon, title] = r.children;
  const clickable = s.manual || s.status === 'Assumed';
  r.className = 'prow st-' + s.status.split(' ').join('-').split('/').join('-');
  const ic = ICON[s.status] || '○';
  if (icon.textContent !== ic) icon.textContent = ic;
  icon.disabled = !clickable;
  icon.tabIndex = clickable ? 0 : -1;
  icon.title = s.status === 'N/A' ? 'does not apply to your game (see My game)' : s.status === 'Assumed' ? 'assumed from later progress: click to confirm' : s.manual ? 'click to toggle' : s.status;
  const t = s.title + (s.manual ? ' ✎' : '');
  if (title.textContent !== t) title.textContent = t;
}

function buildSection(name) {
  const root = h('div', 'psec');
  const head = h('button', 'phead', null, { 'data-act': 'collapse', 'data-name': name, 'aria-expanded': 'true' });
  const caret = h('span', 'caret', '▾'), glyph = h('span', 'glyph', GLYPH[name] || '•');
  const nm = h('span', 'pname', name), cnt = h('span', 'pcount dim small');
  const bar = h('span', 'bar'), fill = h('span', 'fill');
  bar.append(fill);
  add(head, caret, glyph, nm, cnt, bar);
  const wrap = h('div', 'collapsible'), inner = h('div', 'inner'), rows = h('div', 'prows');
  inner.append(rows); wrap.append(inner);
  add(root, head, wrap);
  const rec = { root, head, cnt, fill, wrap, rowsEl: rows, rowMap: new Map() };
  return rec;
}

function renderProgress(v) {
  const names = v.sections || [];
  names.forEach((name, i) => {
    let rec = sectionRecs.get(name);
    if (!rec) { rec = buildSection(name); sectionRecs.set(name, rec); }
    if (sectionsEl.children[i] !== rec.root) sectionsEl.insertBefore(rec.root, sectionsEl.children[i] || null);
    const steps = v.steps.filter((s) => s.section === name && !s.opt);
    const live = steps.filter((s) => s.status !== 'N/A');
    const done = live.filter((s) => s.status === 'Done').length;
    const ct = done + '/' + live.length;
    if (rec.cnt.textContent !== ct) rec.cnt.textContent = ct;
    rec.fill.style.width = (live.length ? (100 * done) / live.length : 0) + '%';
    const isC = !!collapsed[name];
    rec.wrap.classList.toggle('closed', isC);
    rec.head.setAttribute('aria-expanded', String(!isC));
    rec.head.classList.toggle('is-closed', isC);
    // rows: patched in place (no replace)
    const seen = new Set();
    steps.forEach((s, j) => {
      seen.add(s.id);
      let r = rec.rowMap.get(s.id);
      if (!r) { r = buildRow2(s); rec.rowMap.set(s.id, r); } else patchRow(r, s);
      if (rec.rowsEl.children[j] !== r) rec.rowsEl.insertBefore(r, rec.rowsEl.children[j] || null);
    });
    for (const [id, r] of rec.rowMap) if (!seen.has(id)) { r.remove(); rec.rowMap.delete(id); }
  });
  for (const [n, rec] of sectionRecs) if (!names.includes(n)) { rec.root.remove(); sectionRecs.delete(n); }
}

// ---------- main render ----------
function render(v) {
  if (!v) return;
  view = v; viewAt = performance.now();
  v.objectives = v.objectives || {};
  stepsById.clear();
  v.steps.forEach((s) => stepsById.set(s.id, s));
  // drop cached details whose step state changed
  for (const [id, d] of detailCache) {
    const s = stepsById.get(id);
    if (!s || s.status !== d.step.status || s.note !== d.step.note) detailCache.delete(id);
  }
  renderHeader(v); renderFlags(v); renderFolders(v); renderAlerts(v); renderHold(v); renderTodo(v); renderProgress(v);
  if (detailId && !detailCache.has(detailId)) openDetail(detailId, true);
}

// ---------- search ----------
let searchSeq = 0, searchTimer = 0, selectedShort = '';
function clearVerdict() { el.verdict.classList.add('hidden'); el.verdict.replaceChildren(); selectedShort = ''; markSelected(); }
function markSelected() { for (const b of el.hits.querySelectorAll('button')) b.classList.toggle('sel', b.dataset.short === selectedShort); }

async function runSearch() {
  const q = el.q.value.trim();
  const seq = ++searchSeq;
  if (q.length < 2) { el.hits.classList.add('hidden'); el.hits.replaceChildren(); clearVerdict(); return; }
  let res = [];
  try { res = await Api.search(q); } catch (e) { console.error(e); }
  if (seq !== searchSeq) return; // stale
  el.hits.replaceChildren();
  if (!res.length) add(el.hits, add(h('li', 'nohit dim small', 'No matches.')));
  res.slice(0, 40).forEach((x) => {
    const b = h('button', 'hit', null, { 'data-act': 'hit', 'data-short': x.short, 'data-step': x.step || '' });
    add(b, h('span', 'hname', x.display), h('span', 'dim small', x.status));
    add(el.hits, add(h('li'), b));
  });
  el.hits.classList.remove('hidden');
  markSelected();
}

async function showVerdict(sh) {
  selectedShort = sh; markSelected();
  let v;
  try { v = await Api.check_quest(sh); } catch (e) { console.error(e); return; }
  if (selectedShort !== sh || !v) return;
  const color = { safe: 'green', warn: 'amber', stop: 'red', info: 'blue' }[v.verdict] || 'blue';
  const c = h('div', 'card verdict accent-' + color);
  const top = h('div', 'card-top');
  add(top, h('span', 'tag ' + color, (v.display || '').toUpperCase()), h('span', 'grow'),
    h('button', 'x', '✕', { 'data-act': 'closeverdict', 'aria-label': 'close' }));
  add(c, top, h('div', 'title', v.headline));
  (v.details || []).forEach((d) => add(c, h('div', 'why', d)));
  el.verdict.replaceChildren(c);
  el.verdict.classList.remove('hidden');
}

el.q.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 120); });

// ---------- detail ----------
function block(parent, title, cls) {
  const b = h('section', 'dblock');
  add(b, h('h3', cls || '', title));
  parent.append(b);
  return b;
}
const bullets = (items) => { const ul = h('ul', 'bul'); items.forEach((t) => add(ul, h('li', '', t))); return ul; };
const NEVER = new Set(['never', 'none', 'none stated on wiki']);

function renderDetail(d) {
  const s = d.step, kb = d.kb, g = d.guide;
  const root = el.detail;
  root.replaceChildren();
  add(root, h('div', 'chip', lvlChip(s) + ' · ' + s.status), h('h2', 'dtitle', s.title));
  const badge = kb ? ['green', '✔ from the wiki audit (single source: Witcher wiki)']
    : g ? ['amber', '◐ from guide pages (older research)'] : ['dim', 'no researched info for this step yet'];
  add(root, h('div', 'badge ' + badge[0], badge[1]));
  if (d.verdict) {
    const vc = { safe: 'green', warn: 'amber', stop: 'red', info: 'blue' }[d.verdict.verdict] || 'blue';
    const box = h('div', 'card verdict accent-' + vc);
    add(box, h('div', 'lbl ' + vc, 'CAN I DO THIS NOW?'), h('div', 'title', d.verdict.headline));
    (d.verdict.details || []).forEach((t) => add(box, h('div', 'why', t)));
    add(root, box);
  }

  if (kb && kb.title) add(block(root, 'IN-GAME QUEST'), h('div', 'txt', kb.title));

  const what = kb ? '' : g ? g.summary : s.note;
  if (what) add(block(root, 'WHAT IT IS'), h('div', 'txt', what));

  const start = kb ? kb.start : g && g.available_when;
  if (start) add(block(root, 'WHEN YOU GET THE OPTION'), h('div', 'txt', start));

  if (kb && kb.needs_before && kb.needs_before.length)
    add(block(root, 'WHAT IT NEEDS FIRST'), bullets(kb.needs_before.map((n) =>
      n.quest + ' (' + (n.strength === 'hard' ? 'required' : 'recommended') + ')' + (n.why ? ' ' + n.why : ''))));

  if (g && g.how_to && g.how_to.length) {
    const ol = h('ol', 'num');
    g.how_to.forEach((t) => add(ol, h('li', '', t)));
    add(block(root, 'HOW TO DO IT'), ol);
  }

  const miss = [];
  if (kb) {
    const f = (kb.fails_or_locks_when || '').trim();
    if (f && !NEVER.has(f.toLowerCase().replace(/\.$/, ''))) miss.push('Lost/failed: ' + f);
    (kb.must_finish_before || []).forEach((m) => miss.push('Finish before: ' + m.event + (m.why ? ' — ' + m.why : '')));
  }
  if (!miss.length && g && g.missable) miss.push(g.missable);
  if (miss.length) add(block(root, 'CAN YOU MISS IT?', 'red'), bullets(miss));

  if (s.note && (kb || g)) add(block(root, 'ROUTE NOTE'), h('div', 'txt', s.note));
  if (kb && kb.unverified && kb.unverified.length) add(block(root, 'NOT VERIFIED', 'amber'), bullets(kb.unverified.map((u) => typeof u === 'string' ? u : JSON.stringify(u))));

  const srcs = [...new Set([...(kb && kb.sources || []), ...(g && g.sources || [])])];
  if (srcs.length) {
    const ul = h('ul', 'srcs');
    srcs.forEach((u) => add(ul, add(h('li'), h('a', 'src', u, { href: u, 'data-act': 'url', 'data-url': u }))));
    add(block(root, 'SOURCES'), ul);
  }

  const tb = block(root, 'TRACKING');
  if (d.tracking) add(tb, h('div', 'txt', d.tracking));
  if (s.manual) add(tb, h('button', 'btn', s.status === 'Done' ? 'mark as not done' : 'mark done', { 'data-act': 'tick', 'data-id': s.id }));
  else add(tb, h('button', 'linkbtn small', d.overridden ? 'undo my override' : 'override: save detection is wrong, mark done', { 'data-act': 'tick', 'data-id': s.id }));
}

async function openDetail(id, keepScroll) {
  if (!detailId) listScroll = el.listPane.scrollTop;
  detailId = id;
  let d = detailCache.get(id);
  if (!d) { try { d = await Api.get_detail(id); } catch (e) { console.error(e); return; } detailCache.set(id, d); }
  if (detailId !== id) return;
  const st = el.detailPane.scrollTop;
  renderDetail(d);
  el.listPane.classList.add('hidden'); el.detailPane.classList.remove('hidden');
  el.detailPane.scrollTop = keepScroll ? st : 0;
}
function closeDetail() {
  if (!detailId) return;
  detailId = null;
  el.detailPane.classList.add('hidden'); el.listPane.classList.remove('hidden');
  el.listPane.scrollTop = listScroll;
}

// ---------- actions ----------
async function tick(id) {
  try { render(await Api.toggle_tick(id)); } catch (e) { console.error(e); }
}

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const { act, id, name, short: sh, url } = t.dataset;
  if (act === 'url') { e.preventDefault(); Api.open_url(url); }
  else if (act === 'detail') openDetail(id);
  else if (act === 'back') closeDetail();
  else if (act === 'flag') { Api.set_flag(t.dataset.flag, t.dataset.val).then(render).catch(console.error); }
  else if (act === 'browse') { t.disabled = true; Api.pick_folder(t.dataset.kind).then(render).catch(console.error).finally(() => { t.disabled = false; }); }
  else if (act === 'usefolder') useFolder(t.dataset.kind);
  else if (act === 'gear') { $('#flagsPanel').classList.toggle('hidden'); t.classList.toggle('on'); }
  else if (act === 'tick') tick(id);
  else if (act === 'hit') {
    if (t.dataset.step) { el.q.value = ''; runSearch(); openDetail(t.dataset.step); }
    else showVerdict(sh);
  }
  else if (act === 'closeverdict') clearVerdict();
  else if (act === 'toggle-all') { showAll = !showAll; store.set('showAll', showAll); if (view) renderTodo(view); }
  else if (act === 'collapse') {
    collapsed[name] = !collapsed[name];
    store.set('collapsed', collapsed);
    if (view) renderProgress(view);
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (detailId) { closeDetail(); return; }
  if (!el.verdict.classList.contains('hidden')) { clearVerdict(); return; }
  if (el.q.value) { el.q.value = ''; runSearch(); }
});

let levelTimer = 0;
el.level.addEventListener('input', () => {
  clearTimeout(levelTimer);
  levelTimer = setTimeout(async () => {
    const n = Math.max(0, Math.min(100, parseInt(el.level.value, 10) || 0));
    try { render(await Api.set_level(n)); } catch (err) { console.error(err); }
  }, 350);
});
el.pin.checked = store.get('pin', true);
el.pin.addEventListener('change', () => { store.set('pin', el.pin.checked); Api.set_pin(el.pin.checked); });

// ---------- boot ----------
(async function boot() {
  Api.onView(render);
  Api.set_pin(el.pin.checked);
  try { render(await Api.get_view()); }
  catch (e) { el.saveError.textContent = 'Could not load view: ' + e; el.saveError.classList.remove('hidden'); }
})();
