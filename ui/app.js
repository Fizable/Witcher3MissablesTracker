// Witcher 3 route tracker UI. Keyed DOM updates: cards/rows are kept in Maps and only
// replaced when their data signature changes; header/search/level inputs are never rebuilt.
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const GLYPH = { Main: '✦', Secondary: '◆', Contracts: '⚔', 'Treasure Hunts': '◈', Gwent: '🃏' };
const ICON = { Done: '✔', Active: '◐', 'Not started': '○', Failed: '✖', Assumed: '✔?', 'N/A': '–' };
const FIRST_N = 5;

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
const lvlChip = (s) => s.section.toUpperCase() + (/\d/.test(s.lv || '') ? ' · L' + s.lv : '');
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
let lastTargetSig = '';
let planData = null;
let cardFilter = 'all';
const MORE_TABS = ['cards', 'progress', 'coverage', 'status'];

// ---------- header ----------
const el = {
  pin: $('#pin'), level: $('#level'), saveName: $('#saveName'), saveAge: $('#saveAge'), saveError: $('#saveError'),
  q: $('#q'), verdict: $('#verdict'), hits: $('#hits'),
  listPane: $('#listPane'), detailPane: $('#detailPane'), detail: $('#detail'),
};
const ui = {
  setup: $('#setupCard'), runTargets: $('#runTargets'), runCounts: $('#runCounts'),
  goalRow: $('#goalRow'), impossibleSec: $('#impossibleSec'), impossible: $('#impossible'),
  planNote: $('#planNote'), planIssues: $('#planIssues'), planAhead: $('#planAhead'), topLater: $('#topLater'),
  tradeoffsSec: $('#tradeoffsSec'), tradeoffs: $('#tradeoffs'), outcomeMatrix: $('#outcomeMatrix'),
  cards: $('#cards'), cardsCount: $('#cardsCount'), cardsNote: $('#cardsNote'),
  coverage: $('#coverage'), picker: $('#targetPicker'), targetOptions: $('#targetOptions'),
  applyTargets: $('#applyTargets'), morePanel: $('#morePanel'),
};

// ---------- MORE drawer (reference material, not the play loop) ----------
function showMoreTab(tab) {
  if (!MORE_TABS.includes(tab)) tab = 'cards';
  document.querySelectorAll('#morePanel .more-tab').forEach((b) => b.classList.toggle('on', b.dataset.tab === tab));
  const panes = { cards: '#cardsSec', progress: '#progSec', coverage: '#coverageSec', status: '#statusSec' };
  Object.entries(panes).forEach(([name, sel]) => $(sel).classList.toggle('hidden', name !== tab));
}
function openMore(tab) {
  if (!MORE_TABS.includes(tab)) tab = 'cards';
  showMoreTab(tab);
  ui.morePanel.classList.remove('hidden');
  focusInto(ui.morePanel);
  // Reference panes are not rendered while hidden, so opening one refreshes it from the current view.
  if (tab === 'cards') { if (cardsData) renderCards(cardsData); else loadCards(); }
  else if (tab === 'progress' && view) renderProgress(view, true);
  else if (tab === 'coverage' && view) renderCoverage(view, true);
  else if (tab === 'status' && view) { renderImpossible(view, true); renderTradeoffs(view, true); }
}
function closeMore() {
  ui.morePanel.classList.add('hidden');
  restoreFocus();
}
function openCards(filter) {
  cardFilter = filter || 'all';
  syncCardFilters();
  openMore('cards');
}

// ---------- keyboard: focus moves into an overlay and is handed back on close ----------
let focusReturn = null;
function focusInto(panel) {
  const active = document.activeElement;
  // Remember the control that opened the overlay, so Escape returns to it and not to nowhere.
  if (active instanceof HTMLElement && !panel.contains(active)) focusReturn = active;
  const box = panel.querySelector('.more-box, .picker-box') || panel;
  box.setAttribute('tabindex', '-1');
  box.focus({ preventScroll: true });
}
function restoreFocus() {
  const back = focusReturn;
  focusReturn = null;
  if (back && back.isConnected) back.focus({ preventScroll: true });
}

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
  // A new read error may need the folder panel again; a one-shot auto-open is not enough.
  if (err && !lastSaveError) panelAutoOpened = false;
  lastSaveError = err;
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
let lastSaveError = '';
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

// ---------- run header, setup gate and goal picker ----------
const PACK_LABEL = { base: 'Main game', ep1: 'Hearts of Stone', bob: 'Blood and Wine', other_dlc: 'Free DLC', gwent: 'Gwent' };
const stateText = (s) => String(s || 'unknown').replace(/_/g, ' ');
const stateClass = (s) => ({ reachable: 'green', settled: 'blue', impossible: 'red', unknown: 'dim', not_guided_yet: 'dim' }[s] || 'dim');

function renderSetup(v) {
  const show = !!(v.setup && v.setup.needed);
  ui.setup.classList.toggle('hidden', !show);
  const choose = ui.setup.querySelector('[data-act="open-picker"]');
  if (choose) choose.disabled = !(v.setup && v.setup.has_targets);
}

function renderRun(v) {
  const t = v.target;
  ui.runTargets.replaceChildren();
  if (!t) {
    add(ui.runTargets, h('span', 'tagchip', 'SPOILER-FREE'));
  } else {
    t.ids.forEach((id, i) => {
      const st = (t.states || {})[id] || {};
      const chip = h('span', 'goalchip ' + stateClass(st.state));
      add(chip, h('span', '', t.labels[i] || id), h('span', 'goalstate', stateText(st.state)));
      if (st.reason) chip.title = st.reason;
      add(ui.runTargets, chip);
    });
  }
  const q = (v.completion && v.completion.quests) || {};
  const mx = (v.completion && v.completion.matrix) || {};
  const c = (v.completion && v.completion.cards) || {};
  // Only non-zero trouble is named. A permanent "0 lost" reads as reassurance, which is not the
  // same thing as a check.
  const line = (label, x, doneWord) => {
    const parts = [(x.total || 0) + ' total', (x.done ?? x.owned ?? 0) + ' ' + doneWord, (x.available || 0) + ' still possible'];
    if (x.at_risk) parts.push(x.at_risk + ' at risk');
    if (x.lost) parts.push(x.lost + ' lost');
    if (x.excluded) parts.push(x.excluded + ' excluded');
    if (x.unknown) parts.push(x.unknown + ' unknown');
    return label + ': ' + parts.join(' · ');
  };
  ui.runCounts.replaceChildren();
  if (q.total) add(ui.runCounts, h('div', 'runcount', line('Quests', q, 'done')));
  // The audited matrix is deliberately not a percentage: every one of its route nodes is named in
  // one of the six states, and the manual/replaced split is visible beside it.
  if (mx.total) {
    const audit = mx.manual_audit || {};
    const manual = ' · ' + (mx.manual || 0) + ' manual reviewed' + (audit.replaced ? ' (' + audit.replaced + ' replaced)' : '');
    add(ui.runCounts, h('div', 'runcount',
      'Matrix: ' + mx.total + ' route nodes · ' + (mx.done || 0) + ' done · ' + (mx.obtainable || 0) +
      ' obtainable · ' + (mx.at_risk || 0) + ' at risk · ' + (mx.lost || 0) + ' lost · ' +
      (mx.excluded || 0) + ' excluded · ' + (mx.unknown || 0) + ' unknown' + manual));
    if (mx.outside_route) add(ui.runCounts, h('div', 'dim small', mx.outside_route + ' save-only row(s) are shown separately and not counted in the ' + mx.total + '.'));
  }
  const exclusions = (v.completion && v.completion.exclusions) || [];
  if (exclusions.length) {
    const box = h('div', 'runcount exclusions');
    add(box, h('div', '', 'Excluded from this run:'));
    exclusions.forEach((x) => {
      const mechanism = Array.isArray(x.mechanism) ? x.mechanism.join(', ') : (x.mechanism || 'mechanism not recorded');
      add(box, h('div', 'dim small', (x.title || x.id) + ' - ' + mechanism + (x.reason ? ' (' + x.reason + ')' : '')));
    });
    add(ui.runCounts, box);
  }
  if (c.total) add(ui.runCounts, h('div', 'runcount', line('Cards', c, 'owned')));
  if (c.missable) {
    add(ui.runCounts, h('div', 'dim small',
      'Card windows: ' + c.missable + ' missable (' + (c.missable_tier_b || 0) + ' Tier B, ' +
      (c.missable_tier_a || 0) + ' Tier A) · ' +
      (c.at_risk || 0) + ' open now · ' + (c.check || 0) + ' passed - check · ' +(c.lost || 0) + ' lost'));
  }
  if (!q.total && !c.total) add(ui.runCounts, h('div', 'dim small', 'Reading your save...'));
}

function renderGoalRow(v) {
  ui.goalRow.replaceChildren();
  const t = v.target;
  if (!t) {
    add(ui.goalRow, h('span', 'fl', 'Ending goal: none'),
      h('button', 'btn sm', 'Choose', { 'data-act': 'open-picker' }));
    return;
  }
  const left = h('div', 'goaltext');
  add(left, h('div', 'fl', 'Ending goal: ' + (t.labels || []).join(', ')));
  const row = h('div', 'goalbuttons');
  add(row, h('button', 'btn sm', 'Change', { 'data-act': 'open-picker' }),
    h('button', 'btn sm', 'Clear', { 'data-act': 'clear-target' }),
    h('button', 'btn sm', t.guidance === 'on' ? 'Guidance: on' : 'Guidance: off', { 'data-act': 'toggle-guidance' }));
  add(ui.goalRow, left, row);
}

// ---------- planner sections ----------
function renderImpossible(v, force) {
  if (!force && $('#statusSec').classList.contains('hidden')) return;
  const rows = (v.steps || []).filter((s) => s.status === 'Failed' || s.lost);
  ui.impossibleSec.classList.toggle('hidden', !rows.length);
  ui.impossible.replaceChildren();
  rows.slice(0, 30).forEach((s) => {
    const c = h('div', 'card accent-lost');
    add(c, h('div', 'card-top'), h('span', 'tag lost', s.status === 'Failed' ? 'FAILED IN YOUR QUEST LOG' : 'CUT OFF'),
      h('span', 'sidetag dim', s.section));
    add(c, h('button', 'title link', s.title, { 'data-act': 'detail', 'data-id': s.id }));
    add(c, h('div', 'why', s.status === 'Failed' ? 'The journal marks this quest failed.' : 'A reviewed cutoff has passed for this quest.'));
    ui.impossible.append(c);
  });
  if (rows.length > 30) add(ui.impossible, h('div', 'dim small', '+' + (rows.length - 30) + ' more in PROGRESS'));
}

function renderTradeoffs(v, force) {
  if (!force && $('#statusSec').classList.contains('hidden')) return;
  const edges = v.tradeoffs || [];
  ui.tradeoffsSec.classList.toggle('hidden', !edges.length);
  ui.tradeoffs.replaceChildren();
  edges.forEach((e) => {
    const c = h('div', 'card accent-amber');
    add(c, h('div', 'card-top'), h('span', 'tag amber', 'TRADEOFF'));
    add(c, h('div', 'why', e.reason || 'These goals cannot both be completed in one run.'));
    add(c, h('div', 'dim small', (e.a_label || e.a || '') + '  /  ' + (e.b_label || e.b || '')));
    ui.tradeoffs.append(c);
  });
}

// ---------- one-run plan (only after a goal is selected) ----------
let planSeq = 0;
function targetLabel(id) {
  const t = view && view.target;
  if (!t || !t.ids) return id;
  const i = t.ids.indexOf(id);
  return i >= 0 ? (t.labels || [])[i] || id : id;
}
function planMatchesView(p) {
  const t = view && view.target;
  // The plan is what is still coming; only exact instructions are guidance-gated upstream.
  if (!p || !t) return false;
  if (p.state === 'empty') return false;
  const selected = (p.selected || []).slice().sort().join(',');
  const wanted = (t.ids || []).slice().sort().join(',');
  return selected === wanted;
}
function clearPlan() {
  planSeq++;
  planData = null;
  ui.planNote.textContent = '';
  ui.planIssues.classList.add('hidden');
  ui.planIssues.replaceChildren();
  if (view) renderTodo(view);
}
async function loadPlan() {
  const t = view && view.target;
  if (!t || !t.ids || !t.ids.length) { clearPlan(); return; }
  const seq = ++planSeq;
  let p;
  try { p = await Api.get_plan(t.ids); } catch (e) { console.error(e); return; }
  if (seq !== planSeq || !view || !view.target) return;
  planData = p;
  renderPlanIssues(p);
  renderTodo(view);
}
function renderPlanIssues(p) {
  ui.planIssues.replaceChildren();
  if (!p || !planMatchesView(p)) { ui.planIssues.classList.add('hidden'); return; }
  const issues = [];
  (p.unguided || []).forEach((id) => {
    const card = h('div', 'card accent-amber');
    add(card, h('div', 'card-top'), h('span', 'tag amber', 'NO GUIDANCE'));
    add(card, h('div', 'title', targetLabel(id)));
    add(card, h('div', 'why', 'No reviewed guidance yet; the planner will not claim a ready route.'));
    issues.push(card);
  });
  (p.conflicts || []).forEach((x) => {
    const card = h('div', 'card accent-amber');
    add(card, h('div', 'card-top'), h('span', 'tag amber', 'CONFLICT'));
    add(card, h('div', 'why', x.reason || 'These goals cannot both be completed in one run.'));
    add(card, h('div', 'dim small', (x.targets || []).map(targetLabel).join(' / ')));
    issues.push(card);
  });
  (p.blocked_by || []).forEach((x) => {
    const card = h('div', 'card accent-lost');
    add(card, h('div', 'card-top'), h('span', 'tag lost', 'BLOCKED'));
    add(card, h('div', 'title', targetLabel(x.target)));
    add(card, h('div', 'why', x.reason || 'This goal is already impossible in this save.'));
    issues.push(card);
  });
  issues.forEach((card) => ui.planIssues.append(card));
  ui.planIssues.classList.toggle('hidden', !issues.length);
  const c = p.coverage || {};
  ui.planNote.textContent = (c.ahead || 0) + ' ahead · ' + (c.met || 0) + ' set · ' + (p.state || 'unknown');
  if (p.state === 'ready' && !(p.steps || []).some((s) => s.state !== 'settled')) {
    ui.planNote.textContent += ' · all selected outcomes set';
  }
}

// ---------- outcome matrix (inside the spoiler-gated picker) ----------
let outcomesSeq = 0;
async function loadOutcomeMatrix() {
  const seq = ++outcomesSeq;
  let d;
  try { d = await Api.get_outcomes(); } catch (e) { console.error(e); return; }
  if (seq !== outcomesSeq || ui.picker.classList.contains('hidden')) return;
  renderOutcomeMatrix(d);
}
function renderOutcomeMatrix(d) {
  ui.outcomeMatrix.classList.remove('hidden');
  ui.outcomeMatrix.replaceChildren();
  add(ui.outcomeMatrix, h('div', 'lbl', 'OUTCOME MATRIX'));
  const groups = (d && d.groups) || [];
  if (!groups.length) {
    add(ui.outcomeMatrix, h('p', 'dim small', 'No reviewed outcome data in this build.'));
    return;
  }
  groups.forEach((g) => {
    const box = h('div', 'matrix-group');
    add(box, h('div', 'lbl', g.label));
    (g.outcomes || []).forEach((o) => {
      const row = h('div', 'matrix-row');
      add(row, h('span', 'fl', o.label), h('span', 'small ' + stateClass(o.state), stateText(o.state)));
      add(row, h('span', 'dim small', o.target_id ? (o.selected ? 'selected goal' : 'goal available') : 'not a goal'));
      box.append(row);
    });
    ui.outcomeMatrix.append(box);
  });
  ((d && d.conflicts) || []).forEach((c) => add(ui.outcomeMatrix, h('div', 'why', c.reason)));
}
async function toggleOutcomeMatrix() {
  if (!ui.outcomeMatrix.classList.contains('hidden')) {
    outcomesSeq++;
    ui.outcomeMatrix.classList.add('hidden');
    ui.outcomeMatrix.replaceChildren();
    return;
  }
  await loadOutcomeMatrix();
}

function renderCoverage(v, force) {
  if (!force && $('#coverageSec').classList.contains('hidden')) return;
  const packs = (v.coverage && v.coverage.packs) || {};
  const names = ['base', 'ep1', 'bob', 'other_dlc', 'gwent'];
  ui.coverage.replaceChildren();
  const table = h('table', 'coverage-table');
  const head = h('tr');
  ['Pack', 'Quests', 'Phases', 'Scenes', 'Branches', 'Cards', 'Cutoffs'].forEach((t) => add(head, h('th', '', t)));
  const thead = h('thead');
  thead.append(head);
  table.append(thead);
  const body = h('tbody');
  names.forEach((n) => {
    const p = packs[n];
    if (!p) return;
    const tr = h('tr');
    add(tr, h('td', '', PACK_LABEL[n] || n));
    ['quests', 'with_phases', 'with_scenes', 'with_branches', 'with_cards', 'with_cutoffs'].forEach((k) => {
      const unmodelled = k === 'with_cards' && p.not_modelled;
      add(tr, h('td', 'num', unmodelled ? 'not modelled' : p[k] == null ? 'not measured' : String(p[k])));
    });
    body.append(tr);
  });
  table.append(body);
  ui.coverage.append(table);
  // A zero in the card column is not a clean bill. Name the packs that have no card model.
  const notes = names.filter((n) => packs[n] && packs[n].not_modelled)
    .map((n) => (PACK_LABEL[n] || n) + ': ' + packs[n].note);
  if (notes.length) ui.coverage.append(h('p', 'dim small covnote', notes.join(' ')));
}

// ---------- Gwent cards ----------
let cardsData = null;
let cardsLoading = false;
let cardsSeq = 0;
async function loadCards() {
  if (cardsLoading) return;
  cardsLoading = true;
  const seq = ++cardsSeq;
  try {
    const d = await Api.get_cards();
    if (seq !== cardsSeq) return;
    cardsData = d;
    renderCards(d);
  } catch (e) { console.error(e); }
  finally { cardsLoading = false; }
}

function cardWindowBadge(card) {
  const live = card.window_live || {};
  return [live.tone || 'dim', live.label || 'NO WINDOW'];
}

function cardWindowSource(card) {
  const w = card.window || {};
  return w.source ? 'Source: ' + w.source.name + ' (' + w.source.reviewed + ').' : '';
}

function cardWindowLine(card) {
  const w = card.window || {};
  if (w.kind === 'missable') {
    const src = w.source ? ' Source: ' + w.source.name + ' (' + w.source.reviewed + ').' : '';
    return 'Closes: ' + (w.step_title || w.step) + ' - ' + w.event + '. ' + w.mechanism + src;
  }
  if (w.kind === 'one_time') {
    return 'One-time source: ' + (w.step_title || w.step) + ' - ' + w.mechanism;
  }
  return w.reason || 'No window classification.';
}

function cardEvidence(card) {
  const w = card.window || {};
  const live = card.window_live || {};
  if (w.kind === 'none') return null;
  const det = h('details', 'evidence');
  add(det, h('summary', '', 'Technical details'));
  const body = h('div', 'evbody');
  const line = (text) => { if (text) add(body, h('div', 'evline', text)); };
  const tier = w.tier_rank ? 'Tier ' + w.tier_rank + ' - ' + stateText(w.tier) : 'no tier';
  line('Classification: ' + (w.kind === 'missable' ? 'missable' : 'one-time source') + ' · ' + tier + '.');
  if (w.step_title || w.step) line('Closing step: ' + (w.step_title || w.step) + ' (' + (w.step || 'no step') + ').');
  if (w.opens) line('Opens at: ' + (w.opens.step || 'unknown') + (w.opens.note ? ' - ' + w.opens.note : '') + '.');
  if (w.event) line('Event: ' + w.event + '.');
  if (w.mechanism) line('Mechanism: ' + w.mechanism);
  (w.fallback || []).forEach((f) => line('Fallback: ' + (f.value || f.kind) + (f.note ? ' - ' + f.note : '') + '.'));
  if (w.source) {
    const s = w.source;
    line('Community source: ' + s.name + (s.url ? ' - ' + s.url : '') + ' · reviewed ' + s.reviewed + '.');
  }
  (w.evidence || []).forEach((e) => line('Evidence: ' + (e.kind || 'unknown') + ' - ' + (e.value || '')));
  if (live.live_note) line('This save: ' + live.live_note);
  add(det, body);
  return det;
}

function cardMatchesFilter(card) {
  const state = (card.window_live || {}).state;
  if (cardFilter === 'open') return state === 'active' || state === 'check' || state === 'lost';
  if (cardFilter === 'later') return state === 'ahead';
  if (cardFilter === 'owned') return card.owned === 'owned';
  if (cardFilter === 'unknown') return card.owned === 'unknown';
  return true;
}

function syncCardFilters() {
  document.querySelectorAll('#cardFilters .filter').forEach((b) => {
    b.classList.toggle('on', b.dataset.filter === cardFilter);
  });
}

function renderCards(d) {
  const c = d.counts || {};
  ui.cardsCount.textContent = (c.owned || 0) + ' / ' + (c.total || 0) + ' owned' +
    (c.unknown ? ' · ' + c.unknown + ' unknown' : '') +
    (c.missable ? ' · ' + c.missable + ' missable' : '') +
    (c.active ? ' · ' + c.active + ' open now' : '');
  ui.cardsNote.textContent = d.block_ok
    ? (d.missable_windows && d.missable_windows.reviewed
      ? (c.missable || 0) + ' reviewed card window(s): ' + (c.missable_tier_b || 0) + ' community/Tier B, ' +
        (c.missable_tier_a || 0) + ' gamefile/Tier A. ' + (c.one_time || 0) + ' one-time, ' +
        (c.no_window || 0) + ' documented no-window. Tier B rows name their source and review date.'
      : 'No card-level window has been reviewed. This is the collection ledger, not a deadline warning.')
    : 'Card ownership could not be read: ' + (d.reason || 'the save has no collection block') + '. Cards are shown as unknown, never as not owned.';
  ui.cards.replaceChildren();
  const all = d.cards || [];
  const list = all.filter(cardMatchesFilter);
  if (!all.length) { add(ui.cards, h('div', 'dim small', 'No card index in this build.')); return; }
  if (!list.length) { add(ui.cards, h('div', 'dim small', 'No cards in this filter.')); return; }
  const details = h('details', 'cards-collapse');
  add(details, h('summary', '', (cardFilter === 'all' ? 'Show all ' : 'Show ') + list.length + ' cards'));
  const body = h('div', 'cards-body');
  const decks = new Map();
  list.forEach((card) => {
    const key = card.deck || 'Other';
    if (!decks.has(key)) decks.set(key, []);
    decks.get(key).push(card);
  });
  [...decks.keys()].sort().forEach((deck) => {
    const group = h('div', 'card-group');
    add(group, h('div', 'lbl', deck));
    decks.get(deck).forEach((card) => {
      const row = h('div', 'cardrow');
      add(row, h('button', 'cardname', card.name, { 'data-act': 'card', 'data-id': card.id }),
        h('span', 'small ' + (card.owned === 'owned' ? 'green' : card.owned === 'unknown' ? 'dim' : 'red'), stateText(card.owned)),
        h('span', 'dim small card-src', card.source_text || 'unknown source'));
      const badge = cardWindowBadge(card);
      const live = card.window_live || {};
      const line = cardWindowLine(card);
      const source = cardWindowSource(card);
      // Owned and passed rows drop the deadline sentence, but keep the label and, for a reviewed
      // community window, the visible source and review date. The label comes from the payload.
      if (live.state !== 'owned' && live.state !== 'passed') {
        const wline = h('div', 'cardwindow');
        add(wline, h('span', 'windowtag ' + badge[0], badge[1]),
          h('span', 'dim small cardwindow-text', line));
        row.append(wline);
      } else if (source) {
        const wline = h('div', 'cardwindow');
        add(wline, h('span', 'windowtag ' + badge[0], badge[1]),
          h('span', 'dim small cardwindow-text', source));
        row.append(wline);
      } else {
        add(row, h('div', 'cardwindow'), h('span', 'windowtag ' + badge[0], badge[1]));
      }
      const evidence = cardEvidence(card);
      if (evidence) row.append(evidence);
      row.title = [card.name, card.source_text, line].filter(Boolean).join('\n');
      group.append(row);
    });
    body.append(group);
  });
  details.append(body);
  ui.cards.append(details);
}

async function toggleCard(id) {
  if (!cardsData) return;
  const card = (cardsData.cards || []).find((c) => c.id === id);
  if (!card) return;
  try {
    cardsData = await Api.set_card(id, card.owned !== 'owned');
    renderCards(cardsData);
    render(await Api.get_view());
  } catch (e) { console.error(e); }
}

// ---------- target picker (only opened after the spoiler opt-in) ----------
let pickerData = null;
let picked = new Set();
let firstRunPicker = false;

function syncApply() { ui.applyTargets.disabled = picked.size === 0; }

function renderPicker() {
  ui.targetOptions.replaceChildren();
  const targets = (pickerData && pickerData.targets) || [];
  if (!targets.length) {
    add(ui.targetOptions, h('p', 'dim', 'No reviewed ending targets in this build. You can stay spoiler-free.'));
    syncApply();
    return;
  }
  const byPack = new Map();
  targets.forEach((t) => {
    const key = t.pack || 'other_dlc';
    if (!byPack.has(key)) byPack.set(key, []);
    byPack.get(key).push(t);
  });
  ['base', 'ep1', 'bob', 'other_dlc', 'gwent'].forEach((pack) => {
    const rows = byPack.get(pack);
    if (!rows) return;
    const group = h('div', 'target-group');
    add(group, h('div', 'lbl', PACK_LABEL[pack] || pack));
    rows.forEach((t) => {
      const lab = h('label', 'target-option');
      const box = h('input', null, null, { type: 'checkbox' });
      box.checked = picked.has(t.id);
      box.addEventListener('change', () => { if (box.checked) picked.add(t.id); else picked.delete(t.id); syncApply(); });
      const txt = h('div', 'target-text');
      // A not-guided target carries a file-level reason in the payload; that is evidence, not a
      // player-facing explanation. The picker says only that no line has been reviewed yet.
      const reason = t.guidance_status === 'not_guided_yet' ? '' : (t.reason ? ' · ' + t.reason : '');
      add(txt, h('div', 'fl', t.label), h('div', 'small ' + stateClass(t.state), stateText(t.state) + reason));
      add(lab, box, txt);
      group.append(lab);
    });
    ui.targetOptions.append(group);
  });
  const presets = (pickerData && pickerData.presets) || [];
  if (presets.length) {
    const group = h('div', 'target-group');
    add(group, h('div', 'lbl', 'PRESETS'));
    presets.forEach((p) => {
      add(group, h('button', 'btn sm', p.label, { 'data-act': 'preset', 'data-preset': p.id }));
    });
    ui.targetOptions.append(group);
  }
  syncApply();
}

async function openPicker() {
  firstRunPicker = !!(view && view.setup && view.setup.needed);
  outcomesSeq++;
  try { pickerData = await Api.get_targets(); } catch (e) { console.error(e); return; }
  picked = new Set((view && view.target && view.target.ids) || []);
  ui.outcomeMatrix.classList.add('hidden');
  ui.outcomeMatrix.replaceChildren();
  renderPicker();
  ui.picker.classList.remove('hidden');
  focusInto(ui.picker);
}

async function closePicker() {
  outcomesSeq++;
  ui.picker.classList.add('hidden');
  // Do not leave ending names in the DOM after the user goes back to spoiler-free.
  ui.targetOptions.replaceChildren();
  ui.outcomeMatrix.classList.add('hidden');
  ui.outcomeMatrix.replaceChildren();
  pickerData = null;
  restoreFocus();
  if (firstRunPicker) {
    firstRunPicker = false;
    try { render(await Api.set_target([])); } catch (e) { console.error(e); }
  }
}

async function applyPicker() {
  if (!picked.size) return;
  try {
    const v = await Api.set_target([...picked]);
    outcomesSeq++;
    ui.picker.classList.add('hidden');
    ui.targetOptions.replaceChildren();
    ui.outcomeMatrix.classList.add('hidden');
    ui.outcomeMatrix.replaceChildren();
    pickerData = null;
    firstRunPicker = false;
    restoreFocus();
    render(v);
  } catch (e) { console.error(e); }
}

// ---------- top section: only what still has a cost ----------
const topList = keyedList($('#top'));

/**
 * The only list-level warning surface. The backend sends an entry only while acting on it can still
 * change the outcome: a loss that happened, a cutoff you are standing inside, or a missable quest
 * that is still winnable. Settled and done never arrive here; an empty list hides the section.
 *
 * A card says what is at stake and why, in the game's own names. The file mechanism and the
 * save-status transcript stay on the quest's detail page, behind "Technical details".
 */
function renderTop(v) {
  // The payload is the whole truth: a loss, a live cutoff, a failed quest, a choice that matters
  // now, or a card window the player can act on. An ahead card window is a count in
  // MORE > CARDS > LATER, never a band entry.
  const items = v.top || [];
  ui.topLater.replaceChildren();
  // Silence is the correct answer: an empty band is hidden, not filled.
  $('#topSec').classList.toggle('hidden', !items.length);
  topList(items, (x) => x.kind + x.headline, (x) => x, (x) => {
    const col = x.level === 'stop' ? 'red' : x.level === 'lost' ? 'lost' : x.level === 'warn' ? 'amber' : 'blue';
    const first = (x.ids || [])[0];
    const c = h('div', 'card accent-' + col, null, first ? { 'data-act': 'detail', 'data-id': first } : null);
    add(c, h('div', 'tag ' + col, x.tag || 'WATCH OUT'));
    if (first) add(c, h('button', 'title link', x.headline, { 'data-act': 'detail', 'data-id': first }));
    else add(c, h('div', 'title', x.headline));
    if (x.action) add(c, h('div', 'action', x.action));
    return c;
  });
}

function warnCol(x) {
  if (x.live === 'inside' || x.live === 'check') return 'red';
  if (x.live === 'ahead') return 'amber';
  if (x.live === 'passed' || x.live === 'lost' || x.live === 'missed') return 'lost';
  if (x.live === 'settled') return 'blue';
  return x.level === 'stop' ? 'red' : x.level === 'lost' ? 'lost' : x.level === 'warn' ? 'amber' : 'blue';
}

function warnTag(x) {
  if (x.live === 'lost') return 'LOST IN THIS SAVE';
  if (x.live === 'check' || x.live === 'passed') return 'CUTOFF PASSED - CHECK NOW';
  if (x.live === 'inside') return 'DO THIS NOW';
  if (x.live === 'ahead') return 'MISSABLE';
  if (x.live === 'missed') return 'MISSED IN THIS SAVE';
  if (x.live === 'settled') return 'SETTLED IN THIS SAVE';
  return 'WATCH OUT';
}

/** A warning on the quest's own page: the sentence a player needs, nothing about file names. */
function watchBox(x) {
  const col = warnCol(x);
  const box = h('div', 'trk-warn ' + col);
  // The top warning is the authority for the tag: the same warning must not read MISSABLE in
  // AT RISK NOW and WATCH OUT on the quest page. Derived watch rows have no tag, so fall back.
  add(box, h('div', 'tag ' + col, x.tag || warnTag(x)), h('div', 'title', x.headline));
  if (x.action) add(box, h('div', 'action', x.action));
  return box;
}


// ---------- DO NEXT ----------
const cardList = keyedList($('#todoCards'));
const rowList = keyedList($('#todoRows'));

/**
 * A mission card: the current objective first (the line you read most), then one short description,
 * then only spoiler-free chips. The cutoff box lives in the top section and the detail pane; the
 * hand-written note, the wiki start text and the match confidence are gone.
 */
function buildCard(s, objs, tracked, planStep) {
  const active = s.status === 'Active';
  const w = tracked ? tracked.warning : null;
  const accent = w ? (w.level === 'stop' ? 'red' : 'amber') : active ? 'green' : s.conditional ? 'blue' : 'gold';
  const c = h('article', 'card todo accent-' + accent);
  const top = h('div', 'card-top');
  // A tracked step is in the save even when its journal state is "not started" (the tracker may
  // know the next goal before the log flips it active). Never label that card "not in your log".
  const place = active ? 'in your quest log'
    : tracked ? 'tracked in your game'
      : s.conditional ? 'only if it exists in your game' : 'not in your log yet';
  add(top, h('span', 'chip', lvlChip(s)), tracked ? h('span', 'tag blue', 'TRACKED IN YOUR GAME') : null,
    planStep ? h('span', 'tag blue', 'PLAN') : null,
    h('span', 'sidetag ' + (active ? 'green' : 'dim'), place));
  add(c, top, h('button', 'title link', s.title, { 'data-act': 'detail', 'data-id': s.id }));

  // Guidance belongs on the card that is actually current. A plan step that is still ahead shows
  // only its goal marker; the exact line appears when its quest is tracked, so the list cannot
  // leak a future scene line.
  if (planStep) {
    const chips = h('div', 'chips');
    (planStep.targets || []).forEach((id) => add(chips, h('span', 'tagchip goalchip', targetLabel(id))));
    if (planStep.state === 'unreachable') add(chips, h('span', 'tagchip', 'BLOCKED'));
    if (planStep.state === 'unknown') add(chips, h('span', 'tagchip', 'UNKNOWN'));
    add(c, chips);
    if (tracked && planStep.state === 'ahead' && (planStep.instructions || []).length) {
      const box = h('div', 'plan-guidance');
      add(box, h('div', 'lbl gold', 'SAY THIS'));
      planStep.instructions.forEach((i) => {
        add(box, h('div', 'goal-line', '“' + i.instruction + '”'));
        add(box, h('div', 'dim small', targetLabel(i.target) + (i.locid ? ' · locId ' + i.locid : '')));
      });
      add(c, box);
    }
    if (planStep.note) add(c, h('div', 'why', planStep.note));
    if (planStep.facts && planStep.facts.length) add(c, h('div', 'dim small', 'Phase fact: ' + planStep.facts.join(', ')));
  }

  // Only the current quest (and any tracked step) carries its description and objectives. A plan
  // step that is still ahead is a reference row: title, goal, level and the one-line note are enough
  // to decide what comes next without turning UP NEXT into five full dossier cards.
  const full = !planStep || tracked;
  if (full && objs.length) {
    const ul = h('ul', 'bul');
    objs.slice(0, 2).forEach((o) => add(ul, h('li', '', o)));
    add(c, h('div', 'lbl', active ? 'CURRENT OBJECTIVE' : 'STARTS WITH'), ul);
  }
  if (full && s.desc) add(c, h('div', 'txt desc', s.desc));
  const chipTags = (s.tags || []).filter((t) => !(s.goal && (t.id === 'ending_choice' || t.id === 'branch')));
  if (s.goal || chipTags.length || s.provenance === 'manual_reviewed') {
    const chips = h('div', 'chips');
    if (s.goal) add(chips, h('span', 'tagchip goalchip', 'GOAL'));
    chipTags.forEach((t) => add(chips, h('span', 'tagchip', t.label)));
    if (s.provenance === 'manual_reviewed') add(chips, h('span', 'tagchip', 'MANUAL REVIEWED', { title: s.review_reason || 'Reviewed checklist step, not gamefile-proven.' }));
    add(c, chips);
  }
  if (w) add(c, h('div', 'tag ' + (w.level === 'stop' ? 'red' : 'amber'), w.headline));
  if (s.manual) add(c, h('div', 'dim small', s.provenance === 'manual_reviewed' ? 'Reviewed checklist step, not gamefile-proven. You tick it yourself.' : 'You tick this one yourself when it is done.'));

  const foot = h('div', 'card-foot');
  const need = lvNum(s);
  if (view.level > 0 && need && view.level < need - 2) add(foot, h('span', 'amber small', 'level ' + need + ' suggested'));
  add(foot, h('span', 'grow'), h('button', 'btn sm', 'details', { 'data-act': 'detail', 'data-id': s.id }));
  if (s.manual) add(foot, h('button', 'btn sm', 'mark done', { 'data-act': 'tick', 'data-id': s.id }));
  add(c, foot);
  return c;
}

function buildRow(s, rank, planStep) {
  const b = h('button', 'row', null, { 'data-act': 'detail', 'data-id': s.id });
  const st = s.status === 'Active' ? 'in your log' : s.conditional ? 'if it exists' : 'not in log';
  if ((s.watch || []).length) add(b, h('span', 'warnmark', '⚠', { title: s.watch[0].headline }));
  add(b, h('span', 'rank dim', String(rank)), h('span', 'rtitle', noParen(s.title)),
    h('span', 'dim small rreg', s.section), h('span', 'small ' + (s.status === 'Active' ? 'green' : 'dim'), st));
  if (planStep) add(b, h('span', 'tagchip', 'PLAN'));
  return b;
}

function planStepMap() {
  const p = planMatchesView(planData) ? planData : null;
  const map = new Map();
  if (p) (p.steps || []).forEach((s) => { if (s.state !== 'settled') map.set(s.step, s); });
  return map;
}

function renderPlanAhead(items) {
  const box = ui.planAhead;
  if (!box) return;
  box.replaceChildren();
  if (!items.length) { box.classList.add('hidden'); return; }
  const details = h('details', 'plan-ahead');
  const levels = items.map((s) => Number(s.level) || 0).filter((n) => n > 0);
  const span = levels.length ? ' (L' + Math.min(...levels) + (Math.max(...levels) !== Math.min(...levels) ? '-' + Math.max(...levels) : '') + ')' : '';
  add(details, h('summary', '', 'PLAN AHEAD · ' + items.length + ' future goal step' + (items.length === 1 ? '' : 's') + span));
  const ul = h('ul', 'plan-ahead-list');
  items.forEach((s) => {
    const st = stepsById.get(s.step);
    const li = h('li');
    add(li, h('span', 'plan-ahead-name', st.title),
      h('span', 'plan-ahead-meta', ' · L' + (st.lv || '?') + ((s.targets || []).length ? ' · ' + s.targets.map(targetLabel).join(', ') : '')));
    ul.append(li);
  });
  details.append(ul);
  box.append(details);
  box.classList.remove('hidden');
}

/**
 * UP NEXT is the play queue, not the route. It carries only what the save says is live: the tracked
 * quest, quests already in the log, and the one plan step that is current. Future goal steps go into
 * one collapsed PLAN AHEAD line; route steps that are merely unlocked stay in PROGRESS.
 */
function renderTodo(v) {
  const plan = planMatchesView(planData) ? planData : null;
  const allPlan = plan ? (plan.steps || []).filter((s) => s.state !== 'settled' && stepsById.has(s.step)) : [];
  const tr = v.tracked, trackedSteps = new Set(tr ? tr.steps : []);
  const currentPlan = (s) => {
    const st = stepsById.get(s.step);
    return trackedSteps.has(s.step) || st.status === 'Active' || st.frontier === 'in_log';
  };
  const planSteps = allPlan.filter(currentPlan);
  const planAhead = allPlan.filter((s) => !currentPlan(s));
  const aheadIds = new Set(planAhead.map((s) => s.step));
  // "Unlocked" is not "actionable": most of the route is available and not in the log, so it would
  // fill this queue with things the player has not found yet. Only the log can prove a live quest.
  // The backend already decided the queue: tracked + in-log + the one plan step that is next.
  // Future goal steps belong to PLAN AHEAD, so they are removed here rather than re-filtered by a
  // second rule the payload could disagree with.
  const base = (v.todo || []).filter((id) => stepsById.has(id) && !aheadIds.has(id));
  const planById = new Map(planSteps.map((s) => [s.step, s]));
  // Tracked first, then the plan step you are actually on, then the ordinary route order. One id appears once.
  const ids = [];
  base.forEach((id) => { if (trackedSteps.has(id) && !ids.includes(id)) ids.push(id); });
  planSteps.forEach((s) => { if (!ids.includes(s.step)) ids.push(s.step); });
  base.forEach((id) => { if (!ids.includes(id)) ids.push(id); });
  const first = ids.slice(0, FIRST_N), rest = ids.slice(FIRST_N);
  const trackedOf = (id) => (trackedSteps.has(id) ? tr : null);
  renderPlanAhead(planAhead);
  $('#todoEmpty').classList.toggle('hidden', ids.length > 0);
  const emptyText = (v.save && v.save.error) ? 'Load a save to see what is next.' : 'Nothing queued right now.';
  if ($('#todoEmpty').textContent !== emptyText) $('#todoEmpty').textContent = emptyText;
  cardList(first, (id) => id, (id) => [stepsById.get(id), v.objectives[id] || [], v.level, trackedOf(id), planById.get(id)],
    (id) => buildCard(stepsById.get(id), v.objectives[id] || [], trackedOf(id), planById.get(id)));
  const rank = new Map(ids.map((id, i) => [id, i + 1]));
  rowList(rest, (id) => id, (id) => [stepsById.get(id), rank.get(id), planById.get(id)],
    (id) => buildRow(stepsById.get(id), rank.get(id), planById.get(id)));
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
  // A tick is a note. Only a manual row is finished by it; a file-derived row keeps the journal's
  // answer and shows the note as a note, never as a green done check.
  const clickable = (s.manual || s.tick_disagrees || s.status === 'Not started' || s.status === 'Active' || s.status === 'Assumed')
    && s.status !== 'N/A' && s.status !== 'Done' && s.status !== 'Failed';
  r.className = 'prow st-' + s.status.split(' ').join('-').split('/').join('-') + (s.tick_disagrees ? ' noted' : '');
  const ic = s.tick_disagrees ? '✎' : (ICON[s.status] || '○');
  if (icon.textContent !== ic) icon.textContent = ic;
  icon.disabled = !clickable;
  icon.tabIndex = clickable ? 0 : -1;
  icon.title = s.tick_disagrees
    ? 'you noted this; the save still says ' + s.status + '. Click to remove the note.'
    : s.status === 'N/A' ? 'does not apply to your game (see My game)'
      : s.status === 'Assumed' ? 'assumed from later progress: click to confirm'
        : s.manual ? 'click to toggle' : clickable ? 'click to add a note (the save still decides)' : s.status;
  const t = s.title + (s.manual ? (s.provenance === 'manual_reviewed' ? ' ✎ [manual reviewed]' : ' ✎') : s.tick_disagrees ? ' ✎ noted, not confirmed' : '');
  if (title.textContent !== t) title.textContent = t;
  title.title = s.classification ? stateText(s.classification.state) + ': ' + (s.classification.reason || '') : '';
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

function renderProgress(v, force) {
  if (!force && $('#progSec').classList.contains('hidden')) return;
  // The matrix owns the section list: a save-only "Tracked" row must never invent a sixth
  // header that has no counts. Fall back to the route's sections only when the matrix is absent.
  const matrixSections = v.completion && v.completion.matrix && v.completion.matrix.sections;
  const names = matrixSections ? Object.keys(matrixSections) : (v.sections || []);
  names.forEach((name, i) => {
    let rec = sectionRecs.get(name);
    if (!rec) { rec = buildSection(name); sectionRecs.set(name, rec); }
    if (sectionsEl.children[i] !== rec.root) sectionsEl.insertBefore(rec.root, sectionsEl.children[i] || null);
    // PROGRESS is the inspectable matrix: every in-route node appears, including optional and
    // excluded rows. The backend owns the per-section counts (and therefore the six-state totals);
    // this view must not recount statuses or the headers can disagree with the matrix line.
    const steps = v.steps.filter((s) => s.section === name);
    const counts = ((v.completion && v.completion.matrix && v.completion.matrix.sections) || {})[name];
    const ct = counts ? counts.done + '/' + counts.total : '—';
    if (rec.cnt.textContent !== ct) rec.cnt.textContent = ct;
    rec.fill.style.width = (counts && counts.total ? (100 * counts.done) / counts.total : 0) + '%';
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
  // A target change must discard every cached detail: an old line or label may not survive it.
  const targetSig = JSON.stringify(v.target || null);
  if (targetSig !== lastTargetSig) { detailCache.clear(); lastTargetSig = targetSig; }
  // drop cached details whose step state changed
  for (const [id, d] of detailCache) {
    const s = stepsById.get(id);
    if (!s || s.status !== d.step.status || s.desc !== d.step.desc) detailCache.delete(id);
  }
  renderHeader(v); renderFlags(v); renderFolders(v); renderSetup(v); renderRun(v); renderGoalRow(v);
  loadPlan();
  renderTop(v); renderTodo(v); renderImpossible(v); renderTradeoffs(v); renderCoverage(v); renderProgress(v);
  if (!cardsData) loadCards();
  if (detailId && !detailCache.has(detailId)) openDetail(detailId, true);
}

// ---------- search ----------
let searchSeq = 0, searchTimer = 0, selectedShort = '', hitIdx = -1;
function clearVerdict() { el.verdict.classList.add('hidden'); el.verdict.replaceChildren(); selectedShort = ''; markSelected(); }
function markSelected() { for (const b of el.hits.querySelectorAll('button.hit')) b.classList.toggle('sel', b.dataset.short === selectedShort); }
const hitButtons = () => [...el.hits.querySelectorAll('button.hit')];
function markHit() {
  const bs = hitButtons();
  bs.forEach((b, i) => { const on = i === hitIdx; b.classList.toggle('kbdsel', on); b.setAttribute('aria-selected', String(on)); });
  const cur = bs[hitIdx];
  if (cur) el.q.setAttribute('aria-activedescendant', cur.id);
  else el.q.removeAttribute('aria-activedescendant');
}
function hideHits() { el.hits.classList.add('hidden'); hitIdx = -1; markHit(); }

async function runSearch() {
  const q = el.q.value.trim();
  const seq = ++searchSeq;
  hitIdx = -1;
  if (q.length < 2) { el.hits.classList.add('hidden'); el.hits.replaceChildren(); clearVerdict(); return; }
  let res = [];
  try { res = await Api.search(q); } catch (e) { console.error(e); }
  if (seq !== searchSeq) return; // stale
  el.hits.replaceChildren();
  if (!res.length) add(el.hits, add(h('li', 'nohit dim small', 'No matches.')));
  res.slice(0, 40).forEach((x, i) => {
    const b = h('button', 'hit', null, {
      'data-act': 'hit', 'data-short': x.short, 'data-step': x.step || '',
      id: 'hit-' + i, role: 'option', 'aria-selected': 'false',
    });
    add(b, h('span', 'hname', x.display), h('span', 'dim small', x.status));
    add(el.hits, add(h('li', '', null, { role: 'presentation' }), b));
  });
  el.hits.classList.remove('hidden');
  markSelected();
  markHit();
}

function activateHit(i) {
  const b = hitButtons()[i];
  if (!b) return;
  if (b.dataset.step) { el.q.value = ''; runSearch(); openDetail(b.dataset.step); }
  else showVerdict(b.dataset.short);
  hideHits();
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
  if (v.from_game_files) add(c, h('div', 'tag green', (v.evidence === 'files+saves' ? 'GAME FILES + YOUR SAVES' : 'GAME FILES')));
  add(c, h('div', 'title', v.headline));
  (v.details || []).forEach((d) => add(c, h('div', 'why', d)));
  el.verdict.replaceChildren(c);
  el.verdict.classList.remove('hidden');
}

el.q.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 120); });
// Up/down walk the hits, Enter opens the highlighted one. A single match needs no pick at all.
el.q.addEventListener('keydown', (e) => {
  const n = hitButtons().length;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!n) return;
    e.preventDefault();
    el.hits.classList.remove('hidden');
    hitIdx = e.key === 'ArrowDown' ? Math.min(n - 1, hitIdx + 1) : Math.max(0, hitIdx - 1);
    markHit();
    const b = hitButtons()[hitIdx];
    if (b) b.scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'Enter') {
    if (hitIdx >= 0) { e.preventDefault(); activateHit(hitIdx); }
    else if (n === 1) { e.preventDefault(); activateHit(0); }
  }
});

// ---------- detail ----------
function block(parent, title, cls) {
  const b = h('section', 'dblock');
  add(b, h('h3', cls || '', title));
  parent.append(b);
  return b;
}

/**
 * The page a player opens from a card: what the quest is, what is at stake, and what to do. The
 * source-file trail is real but secondary, so it sits in one collapsed "Technical details" section
 * at the bottom instead of running through the page.
 */
function evidenceBlock(d, s, dv, gr) {
  const det = h('details', 'evidence');
  add(det, h('summary', '', 'Technical details'));
  const body = h('div', 'evbody');
  const line = (text) => { if (text) add(body, h('div', 'evline', text)); };

  if (dv && dv.stems && dv.stems.length) line('Game files: ' + dv.stems.join(', ') + '.');
  if (d.tracking) line(d.tracking);

  const reqs = gr && gr.requires ? gr.requires : [];
  reqs.forEach((r) => {
    if (r.facts && r.facts.length) line('Fact condition for ' + r.step + ': ' + r.facts.join(', ') + '.');
  });

  (dv && dv.watch ? dv.watch : []).forEach((w) => {
    const closes = [w.closes_at_title, ...(w.closed_by_titles || [])].filter(Boolean);
    if (closes.length) line('Closing step: ' + closes.join(' / ') + '.');
    if (w.mechanism) {
      const m = w.mechanism === 'journal_failure' ? 'journal Failure block' : w.mechanism === 'spawnset' ? 'CDeactivateSpawnset' : w.mechanism;
      line('Mechanism: ' + m + '.');
    }
    if (w.evidence) line('Evidence tier: ' + w.evidence + '.');
    if (w.why) line('Why this warning exists: ' + w.why);
    (w.files || []).forEach((f) => line('Game file: ' + f + '.'));
    (w.caveats || []).forEach((c) => line('Caveat: ' + c));
    if (w.live_note) line('Your save: ' + w.live_note);
  });
  // A card warning shares the top surface with quest warnings; when its link opens the closing
  // quest, the card window must still be inspectable here rather than only in the card row.
  ((view && view.top) || []).filter((x) => x.kind === 'card' && (x.ids || []).includes(s.id)).forEach((x) => {
    line('Card warning: ' + (x.tag || 'card window') + '. ' + (x.action || x.detail || ''));
    if (x.file) line('Card evidence: ' + x.file + '.');
  });

  (Array.isArray(d.guidance) ? d.guidance : []).forEach((g) => {
    if (g.source && g.source.file) {
      line('Goal guidance: ' + g.label + ' - ' + g.source.file + ' · locId ' + g.source.locid + '.');
    }
  });
  const branches = Array.isArray(d.branches) ? d.branches : [];
  if (branches.length) line('Extracted decisions at this step: ' + branches.map((b) => b.id).join(', ') + '.');

  if (!body.children.length) line('No extra source detail for this step.');
  add(det, body);
  return det;
}

function renderDetail(d) {
  const s = d.step;
  const live = stepsById.get(s.id) || {};
  if (live.classification) s.classification = live.classification;
  const dv = d.derived || null;
  const gr = d.graph || null;
  const root = el.detail;
  root.replaceChildren();
  add(root, h('div', 'chip', lvlChip(s) + ' · ' + s.status), h('h2', 'dtitle', s.title));
  if (s.provenance === 'manual_reviewed') add(root, h('div', 'tag green', 'MANUAL REVIEWED - NOT GAMEFILE-PROVEN'));
  if (s.desc) add(root, h('div', 'ddesc', String(s.desc).trim()));
  // Prefer the same top items the list shows, so the tag, headline and action cannot drift from
  // AT RISK NOW. Fall back to the generated watch row when the step has no current top item.
  const topWarns = ((view && view.top) || []).filter((x) => (x.ids || []).includes(s.id));
  const warns = topWarns.length ? topWarns : (dv && dv.watch ? dv.watch : []);
  const lost = warns.some((x) => x.live === 'lost' || String(x.tag || '').includes('LOST'));
  const tags = (s.tags || []).filter((t) => !(lost && t.id === 'missable') && !(s.goal && (t.id === 'ending_choice' || t.id === 'branch')));
  if (s.goal || tags.length) {
    const chips = h('div', 'chips');
    if (s.goal) add(chips, h('span', 'tagchip goalchip', 'GOAL'));
    tags.forEach((t) => add(chips, h('span', 'tagchip', t.label)));
    add(root, chips);
  }

  warns.forEach((x) => add(root, watchBox(x)));

  // The exact line is the only thing the player needs at the table. Fact names and the scene
  // source are evidence, so they live in Technical details instead of beside the instruction.
  const guidance = Array.isArray(d.guidance) ? d.guidance : [];
  guidance.forEach((g) => {
    const b = block(root, 'YOUR GOAL - ' + g.label, 'gold');
    if (g.step_state === 'ahead') {
      add(b, h('div', 'lbl gold', 'SAY THIS'));
      add(b, h('div', 'goal-line', '“' + g.instruction + '”'));
    } else if (g.step_state === 'settled') {
      add(b, h('div', 'txt', 'Already settled in this save.'));
    } else if (g.step_state === 'unreachable') {
      add(b, h('div', 'txt red', 'This goal is no longer reachable.'));
    } else {
      add(b, h('div', 'txt', 'Not enough information yet.'));
    }
  });

  const branches = Array.isArray(d.branches) ? d.branches : [];
  if (branches.length) {
    const b = block(root, 'CHOICES');
    add(b, h('div', 'txt', 'This step contains decisions that change later content.'));
    if (branches.some((x) => x.ending_relevant)) {
      add(b, h('div', 'dim small', 'One of them affects an ending.'));
    }
  }

  const all = (dv && dv.objectives ? dv.objectives : []).map((o) => o.text).filter(Boolean);
  const cur = (d.current_objectives || []).filter(Boolean);
  if (all.length || cur.length) {
    const active = s.status === 'Active';
    const shown = active && cur.length ? cur : all.slice(0, active ? 1 : Math.min(3, all.length));
    const b = block(root, active ? (shown.length > 1 ? 'CURRENT OBJECTIVES' : 'CURRENT OBJECTIVE') : 'OBJECTIVES');
    const ul = h('ul', 'bul');
    shown.forEach((o, i) => add(ul, h('li', i === 0 && active ? 'current' : '', (i === 0 && active ? '▸ ' : '') + o)));
    add(b, ul);
    if (all.length > shown.length) {
      const more = h('details', 'evidence');
      add(more, h('summary', '', 'Show all ' + all.length + ' objectives'));
      const full = h('ul', 'bul');
      all.forEach((o) => add(full, h('li', '', o)));
      const body = h('div', 'evbody');
      add(body, full);
      add(more, body);
      add(b, more);
    }
  }

  const reqs = gr && gr.requires ? gr.requires : [];
  if (reqs.length) {
    const b = block(root, 'DO THIS FIRST');
    reqs.forEach((r) => {
      const t = (stepsById.get(r.step) || {}).title || r.step;
      add(b, h('div', 'txt', t));
    });
  }

  if (s.manual) {
    const b = block(root, 'TRACKING');
    add(b, h('div', 'txt', s.provenance === 'manual_reviewed'
      ? 'Reviewed manual step. You tick this one yourself; it is not a gamefile claim.'
      : 'You tick this one yourself when it is done.'));
    if (s.review_reason) add(b, h('div', 'dim small', 'Why it cannot be read from the save: ' + s.review_reason));
    if (s.review_source) add(b, h('div', 'dim small', 'Review source: ' + s.review_source + (s.reviewed ? ' · ' + s.reviewed : '')));
    add(b, h('button', 'btn', s.status === 'Done' ? 'mark as not done' : 'mark done', { 'data-act': 'tick', 'data-id': s.id }));
  }

  if (s.classification) {
    const b = block(root, 'MATRIX STATUS');
    add(b, h('div', 'txt', stateText(s.classification.state) + ' - ' + (s.classification.reason || 'no evidence recorded')));
  }

  if (!s.manual) {
    // Ticking a file-derived step is a note, not a status. Put it on the page as a plain button
    // and say what it does; the save still decides the card, the matrix and the warning.
    const b = block(root, 'NOTE');
    add(b, h('div', 'why', s.tick_disagrees
      ? 'You noted this as done, but the save still says ' + s.status + '. The journal wins; remove the note if it was a mistake.'
      : 'The tracker reads this step from your save. A note records what the save cannot show; it never overrides the journal.'));
    add(b, h('button', 'btn sm', s.tick_disagrees ? 'remove my note' : 'note this as done', { 'data-act': 'tick', 'data-id': s.id }));
    const fix = h('details', 'evidence');
    add(fix, h('summary', '', 'Something wrong with this reading?'));
    const fb = h('div', 'evbody');
    add(fb, h('div', 'evline', 'A note is kept beside the save state: the card keeps saying ' + s.status + ' until the journal itself changes.'));
    add(fb, h('button', 'linkbtn small', s.tick_disagrees ? 'remove my note' : 'add a note', { 'data-act': 'tick', 'data-id': s.id }));
    add(fix, fb);
    add(root, fix);
  }

  add(root, evidenceBlock(d, s, dv, gr));
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
  if (e.target.id === 'morePanel') { closeMore(); return; }
  if (e.target.id === 'targetPicker') { closePicker(); return; }
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const { act, id, name, short: sh, url, preset } = t.dataset;
  if (act === 'url') { e.preventDefault(); Api.open_url(url); }
  else if (act === 'detail') openDetail(id);
  else if (act === 'back') closeDetail();
  else if (act === 'skip-setup') { Api.set_target([]).then(render).catch(console.error); }
  else if (act === 'open-picker') openPicker();
  else if (act === 'close-picker') closePicker();
  else if (act === 'outcome-matrix') toggleOutcomeMatrix();
  else if (act === 'apply-targets') applyPicker();
  else if (act === 'clear-target') {
    Api.set_target([]).then((v) => { ui.targetOptions.replaceChildren(); pickerData = null; render(v); }).catch(console.error);
  }
  else if (act === 'toggle-guidance') {
    const on = !(view && view.target && view.target.guidance === 'on');
    Api.set_guidance(on).then(render).catch(console.error);
  }
  else if (act === 'preset') {
    const p = (pickerData && pickerData.presets || []).find((x) => x.id === preset);
    if (p) { picked = new Set(p.targets || []); renderPicker(); }
  }
  else if (act === 'card') toggleCard(id);
  else if (act === 'flag') { Api.set_flag(t.dataset.flag, t.dataset.val).then(render).catch(console.error); }
  else if (act === 'browse') {
    t.disabled = true;
    Api.pick_folder(t.dataset.kind).then(render).catch((e) => {
      // A picker that will not open is not silence: say so where the folder controls are.
      const m = $('#foldermsg');
      m.classList.remove('hidden');
      m.textContent = 'Could not open the folder picker: ' + (e && e.message ? e.message : e) + '. You can paste the path instead.';
    }).finally(() => { t.disabled = false; });
  }
  else if (act === 'usefolder') useFolder(t.dataset.kind);
  else if (act === 'gear') { $('#flagsPanel').classList.toggle('hidden'); t.classList.toggle('on'); }
  else if (act === 'tick') tick(id);
  else if (act === 'hit') {
    if (t.dataset.step) { el.q.value = ''; runSearch(); openDetail(t.dataset.step); }
    else showVerdict(sh);
  }
  else if (act === 'closeverdict') clearVerdict();
  else if (act === 'more') openMore('cards');
  else if (act === 'close-more') closeMore();
  else if (act === 'more-tab') openMore(t.dataset.tab);
  else if (act === 'open-cards') openCards(t.dataset.filter);
  else if (act === 'card-filter') {
    cardFilter = t.dataset.filter || 'all';
    syncCardFilters();
    if (cardsData) renderCards(cardsData);
  }
  else if (act === 'toggle-all') { showAll = !showAll; store.set('showAll', showAll); if (view) renderTodo(view); }
  else if (act === 'collapse') {
    collapsed[name] = !collapsed[name];
    store.set('collapsed', collapsed);
    if (view) renderProgress(view);
  }
});

document.addEventListener('keydown', (e) => {
  const overlayOpen = !ui.picker.classList.contains('hidden') || !ui.morePanel.classList.contains('hidden');
  // "/" jumps to the search box, the way it does in most reference tools.
  if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const a = document.activeElement;
    const typing = !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable);
    if (!typing && !overlayOpen) { e.preventDefault(); el.q.focus(); el.q.select(); return; }
  }
  if (e.key === 'Tab' && overlayOpen) { trapTab(e); return; }
  if (e.key !== 'Escape') return;
  if (!ui.picker.classList.contains('hidden')) { closePicker(); return; }
  if (!ui.morePanel.classList.contains('hidden')) { closeMore(); return; }
  if (detailId) { closeDetail(); return; }
  // An open hit list is the innermost thing Escape can dismiss.
  if (!el.hits.classList.contains('hidden')) { hideHits(); return; }
  if (!el.verdict.classList.contains('hidden')) { clearVerdict(); return; }
  if (el.q.value) { el.q.value = ''; runSearch(); }
});

/** Tab stays inside the open overlay instead of walking into the page behind it. */
function trapTab(e) {
  const dialog = !ui.picker.classList.contains('hidden') ? ui.picker : ui.morePanel;
  const focusable = [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), [href], summary, [tabindex]:not([tabindex="-1"])')]
    .filter((n) => n.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1], active = document.activeElement;
  if (!dialog.contains(active)) { e.preventDefault(); first.focus(); return; }
  if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
}

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
