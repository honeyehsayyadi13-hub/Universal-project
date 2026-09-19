/* app.js 
════════════════════════════════════════════════════════════════
   Universal Route Planner — front end
   ────────────────────────────────────────────────────────────────
   BACKEND CONTRACT (point API_BASE at your Flask app, or leave it as
   '' if this file is served by the same Flask app):

   GET  {API_BASE}/api/rides
     -> { "<rideId>": { "waittime": <minutes>, "is_open": true|false|null }, ... }
     A ride only appears in this dict when Data.py's background poller has
     ever seen it. A ride missing from the dict means "unknown" (not
     necessarily closed) — we don't force it into the closed list on that
     basis alone.

   POST {API_BASE}/api/route
     body: {
       "ride_counts":       { "<rideId>": <int quantity>, ... },  // only visible, qty>0 rides
       "ride_locked":       { "<rideId>": true, ... },             // OBJECT, not array —
                                                                    // routeOptimizer.py calls
                                                                    // ride_locked.get(key) on this
       "closed_ride_keys":  ["<rideId>", ...],
       "breaks":            [[startMin, endMin], ...],             // minutes since midnight
       "start_key":         "<rideId>|entrance",
       "live_waits":        { "<rideId>": <minutes>, ... }          // straight from /api/rides
     }
     -> a list from compute_and_print_route(); each entry may be a plain
        ride-id string, a [ride_id, predicted_wait] pair, or a dict with
        ride_id/predicted_wait-style keys — the normalizer below handles
        all three shapes. On failure the backend returns a JSON body of
        { "error": "..." } with a non-200 status.

   Adjust API_BASE / field names below to match your actual Flask routes.
   ════════════════════════════════════════════════════════════════ */

const API_BASE = '';
const STATUS_POLL_MS = 8000;

// ── ride catalogue (mirrors ride_names / raw_buttons / _ride_image_paths) ──
const RIDES = [
  { id: 'hulk',           name: 'The Incredible Hulk Coaster',                 displayName: "The Incredible Hulk",   icon: 'assets/logos/hulk_logo.png',            x: 456  , y: 668, realX: 454, realY: 741, sizeMult: 1, brightness: 1.4 },
  { id: 'stormForce',     name: 'Storm Force Accelatron',                      displayName: "Storm Force", icon: 'assets/logos/stormForce_logo.png',      x: 429   , y: 762, realX: 387 , realY: 738, sizeMult: 1, brightness: 1.4 },
  { id: 'doctorDoom',     name: "Doctor Doom's Fearfall",                      displayName: "Doctor Doom", icon: 'assets/logos/Doctor-dooms-fearfall-ride-logo-b.png', x: 305  , y: 695, realX: 329 , realY: 674, sizeMult: 1, brightness: 1.4 },
  { id: 'spiderMan',      name: 'The Amazing Adventures of Spider-Man',        displayName: "Spider Man", icon: 'assets/logos/Amazing-adventures-spider-man-ride-logo-b.png', x: 305, y: 607, realX: 310 , realY: 622, sizeMult: 1, brightness: 1.4 },
  { id: 'bilgeRat',       name: "Popeye & Bluto's Bilge-Rat Barges",           displayName: "Bilge-rat barges", icon: 'assets/logos/bilge_rat.png',            x: 321, y: 398, realX: 321, realY: 398, sizeMult: 1, brightness: 1.4 },
  { id: 'ripsawFalls',    name: "Dudley Do-Right's Ripsaw Falls",              displayName: "Ripsaw Falls", icon: 'assets/logos/Dudley-do-rights-ripsaw-falls-water-ride-logo-b.png', x: 166, y: 411, realX: 166, realY: 411, sizeMult: 1, brightness: 1.4 },
  { id: 'skullIsland',    name: 'Skull Island: Reign of Kong',                 displayName: "Skull Island", icon: 'assets/logos/Skull_Island-_Reign_of_Kong_Logo.png', x: 179, y: 246, realX: 179, realY: 246, sizeMult: 0.95, brightness: 1.6 },
  { id: 'velociCoaster',  name: 'Jurassic World VelociCoaster',                displayName: "VelociCoaster", icon: 'assets/logos/velocicoaster.png',        x: 475 , y: 325, realX: 475, realY: 325, sizeMult: 1, brightness: 1.4 },
  { id: 'riverAdventure', name: 'Jurassic Park River Adventure',               displayName: "River Adventure", icon: 'assets/logos/jurrasicPark.png',         x: 246, y: 164, realX: 329, realY: 194, sizeMult: 1, brightness: 1.6 },
  { id: 'hogwartsTrain',  name: 'Hogwarts Express',                            displayName: "Hogwarts Express", icon: 'assets/logos/express.png',              x: 728   , y: 331, realX: 793, realY: 288, sizeMult: 1, brightness: 0.8 },
  { id: 'hippogriff',     name: 'Flight of the Hippogriff',                    displayName: "Hippogriff", icon: 'assets/logos/hippogriph.png',           x: 657    , y: 106, realX: 587, realY: 152, sizeMult: 1, brightness: 1.4 },
  { id: 'hagrid',         name: "Hagrid's Magical Creatures Motorbike Adventure", displayName: "Hagrids", icon: 'assets/logos/Hagrid27s_Magical_Creatures_Motorbike_Adventure.png', x: 714  , y: 228, realX: 697, realY: 238, sizeMult: 1, brightness: 1.4 },
  { id: 'drSeussAirRide', name: 'High in the Sky Seuss Trolley Train Ride',    displayName: "Dr. Suess's Trolly", icon: 'assets/logos/seuss.png',                x: 684 , y: 531, realX: 680, realY: 578, sizeMult: 1.1, brightness: 1.4 },
  { id: 'caroSeussel',    name: 'Caro-Seuss-el',                               displayName: "Caro-Suess-el", icon: 'assets/logos/caro.png',                 x: 587   , y: 603, realX: 587, realY: 603, sizeMult: 1.1, brightness: 1.4 },
  { id: 'oneFishtwoFish', name: 'One Fish, Two Fish, Red Fish, Blue Fish',     displayName: "One Fish Two Fish", icon: 'assets/logos/blue.png',                 x: 720     , y: 655, realX: 650, realY: 626, sizeMult: 1, brightness: 1.4 },
  { id: 'catInTheHat',    name: 'The Cat in the Hat',                          displayName: "Cat in the Hat", icon: 'assets/logos/cat.png',                  x: 634 , y: 744, realX: 645, realY: 715, sizeMult: 1, brightness: 1.4 },
  { id: 'harryPotter',    name: 'Harry Potter and the Forbidden Journey',      displayName: "Forbidden Journey", icon: 'assets/logos/hogwarts.png',             x: 536  , y: 167, realX: 539, realY: 159, sizeMult: 1, brightness: 1.4 },
];
const MAP_NATIVE_W = 1000;
const MAP_NATIVE_H = 800;
const rideById = Object.fromEntries(RIDES.map(r => [r.id, r]));

// ── state ───────────────────────────────────────────────────────
const state = {
  visible: Object.fromEntries(RIDES.map(r => [r.id, true])),
  counts:  Object.fromEntries(RIDES.map(r => [r.id, 1])),
  lastCount: Object.fromEntries(RIDES.map(r => [r.id, 1])),
  locked:  Object.fromEntries(RIDES.map(r => [r.id, false])),
  lockBeforeBump: Object.fromEntries(RIDES.map(r => [r.id, false])),
  breaks: [],
  selectedStart: 'entrance',
  route: [],
  liveWaits: {},
  liveOpen: {},
  timePinned: {},
  maxCounts: Object.fromEntries(RIDES.map(r => [r.id, Infinity])),
  maxBeforeInfinity: Object.fromEntries(RIDES.map(r => [r.id, 0])),
  maxWasZeroBeforeLock: Object.fromEntries(RIDES.map(r => [r.id, false])),
  pinnedLocked: {},
};

function getInstanceIndex(route, pos) {
  const rideId = route[pos].rideId;
  let count = 0;
  for (let i = 0; i < pos; i++) if (route[i].rideId === rideId) count++;
  return count;
}

function getUniqueKey(rideId, instanceIndex) { return `${rideId}:${instanceIndex}`; }

// If a ride ends up pinned/selected at more distinct spots in the top bar
// than its sidebar count currently allows, bump that count up to match --
// otherwise the sidebar would be asking for fewer visits than the person
// just told the route to guarantee by pinning them.
function ensureMinCountMatchesPinnedInstances(rideId) {
  const pinnedInstanceCount = Object.keys(state.timePinned)
    .filter(k => k.startsWith(`${rideId}:`)).length;
  if (pinnedInstanceCount > state.counts[rideId]) {
    state.counts[rideId] = pinnedInstanceCount;
    state.lastCount[rideId] = pinnedInstanceCount;
    if (!state.visible[rideId]) state.visible[rideId] = true;
    if (state.maxCounts[rideId] !== Infinity && state.maxCounts[rideId] < pinnedInstanceCount) {
      state.maxCounts[rideId] = pinnedInstanceCount;
    }
  }
}

function minsToTime(mins) {
  if (mins == null) return '--';
  const total = Math.round(mins) % 1440;
  const h = Math.floor(total / 60);
  const m = total % 60;
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m).padStart(2, '0')} ${period}`;
}

// ── advanced / dark mode ─────────────────────────────────────────
const DARK_MODE_KEY = 'urp.darkMode';
const ADVANCED_MODE_KEY = 'urp.advancedMode';
const LIGHT_MAP_SRC = 'assets/lightMap.png';
const DARK_MAP_SRC  = 'assets/darkMap.png';

function getInitialDarkMode() {
  const stored = localStorage.getItem(DARK_MODE_KEY);
  if (stored === 'true')  return true;
  if (stored === 'false') return false;
  // No explicit choice saved yet -- match the browser/OS setting.
  return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

let darkModeOn = getInitialDarkMode();
let advancedModeOn = localStorage.getItem(ADVANCED_MODE_KEY) === 'true';

function applyDarkMode() {
  const mapPaneEl = document.getElementById('mapPane');
  mapPaneEl?.classList.toggle('map-dark', darkModeOn);
  mapViewportEl.classList.toggle('map-dark', darkModeOn);

  const wantedSrc = darkModeOn ? DARK_MAP_SRC : LIGHT_MAP_SRC;
  if (!mapImageEl.src.endsWith(wantedSrc)) mapImageEl.src = wantedSrc;

  document.getElementById('darkModeCheckbox')?.classList.toggle('checked', darkModeOn);
  const label = document.getElementById('darkModeLabel');
  if (label) label.textContent = darkModeOn ? 'Light Mode' : 'Dark Mode';
}

function applyAdvancedMode() {
  document.getElementById('advancedModeCheckbox')?.classList.toggle('checked', advancedModeOn);
  // Hook point for future advanced-mode behavior -- just persisted and reflected in the checkbox for now.
}

document.getElementById('advancedModeToggle')?.addEventListener('click', () => {
  advancedModeOn = !advancedModeOn;
  localStorage.setItem(ADVANCED_MODE_KEY, advancedModeOn);
  applyAdvancedMode();
});

document.getElementById('darkModeToggle')?.addEventListener('click', () => {
  darkModeOn = !darkModeOn;
  localStorage.setItem(DARK_MODE_KEY, darkModeOn);
  applyDarkMode();
});

let breakIdCounter = 0;
let dragSrcIdx = null;
let touchDragSrcIdx = null;
let touchDragClone   = null;
let touchStartX = 0, touchStartY = 0;
let touchDragging = false;

function clearConflictingSentinelPins(sentinelValue, exceptKey) {
  for (const [key, pin] of Object.entries(state.timePinned)) {
    if (key === exceptKey) continue;
    if (pin.targetMinutes === sentinelValue) {
      pin.targetMinutes = null;
    }
  }
}

function executeDrop(srcIdx, destIdx) {
  if (srcIdx === null || destIdx === null || srcIdx === destIdx) return;

  // First and last positions get sentinel targetMinutes so _reorder_for_time_pins
  // always places them at the extreme end of the day, keeping them there.
  const isFirst = destIdx === 0;
  const isLast  = destIdx === state.route.length - 1;
  const targetMinutes = isFirst ? 0
                      : isLast  ? 1440
                      : (state.route[destIdx]?.queueJoinMinutes ?? null);

  // Remove stale time-pin for the dragged stop
  const srcInstIdx = getInstanceIndex(state.route, srcIdx);
  const oldKey = getUniqueKey(state.route[srcIdx].rideId, srcInstIdx);
  delete state.timePinned[oldKey];

  // Reorder — moved always lands at index destIdx in the final array
  const moved = state.route.splice(srcIdx, 1)[0];
  state.route.splice(destIdx, 0, moved);

  // Attach time-pin at new position
  const newInstIdx = getInstanceIndex(state.route, destIdx);
  const newKey = getUniqueKey(moved.rideId, newInstIdx);
  state.timePinned[newKey] = {
    rideId:        moved.rideId,
    instanceIndex: newInstIdx,
    targetMinutes,
  };

  // If this drop claims the first or last slot, no other stop is allowed
  // to keep claiming that same slot — otherwise both stops would tell the
  // backend "put me first" (or "put me last") and only one request can win.
  if (isFirst) clearConflictingSentinelPins(0, newKey);
  if (isLast)  clearConflictingSentinelPins(1440, newKey);

  // Auto-lock the dragged ride if not already sidebar-locked
  if (!state.locked[moved.rideId]) {
    state.locked[moved.rideId] = true;
    state.pinnedLocked[moved.rideId] = true;
  }

  ensureMinCountMatchesPinnedInstances(moved.rideId);

  renderRouteBar();
  renderSidebarList();
}

const startOptions = [{ id: 'entrance', label: 'Entrance' },
  ...RIDES.map(r => ({ id: r.id, label: r.name }))];

// ── presets (persisted in localStorage) ────────────────────────
const PRESET_KEY = 'urp.presets';
let presets = JSON.parse(localStorage.getItem(PRESET_KEY) || '[]');
let presetIdCounter = presets.reduce((m, p) => Math.max(m, p.id), 0);
let selectedPresetId = null;

function savePresets() { localStorage.setItem(PRESET_KEY, JSON.stringify(presets)); }

function addPreset() {
  presetIdCounter += 1;
  presets.push({
    id: presetIdCounter,
    name: `Preset ${presets.length + 1}`,
    visible: { ...state.visible },
    counts: { ...state.counts },
    locked: { ...state.locked },
    lastCount: { ...state.lastCount },
    breaks: JSON.parse(JSON.stringify(state.breaks)),
    selectedStart: state.selectedStart,
    timePinned: JSON.parse(JSON.stringify(state.timePinned)),
    maxCounts: Object.fromEntries(Object.entries(state.maxCounts).map(([k,v]) => [k, v === Infinity ? null : v])),
    maxBeforeInfinity: { ...state.maxBeforeInfinity },
    maxWasZeroBeforeLock: { ...state.maxWasZeroBeforeLock },
    pinnedLocked: { ...state.pinnedLocked },
  });
  selectedPresetId = presetIdCounter;
  savePresets();
  renderPresetDropdown();
}

function deletePreset(id) {
  presets = presets.filter(p => p.id !== id);
  presets.forEach((p, i) => { p.name = `Preset ${i + 1}`; });
  if (selectedPresetId === id) selectedPresetId = null;
  savePresets();
  renderPresetDropdown();
}

function applyPreset(id) {
  const p = presets.find(pr => pr.id === id);
  if (!p) return;
  RIDES.forEach(r => {
    if (r.id in p.visible)   state.visible[r.id]   = p.visible[r.id];
    if (r.id in p.counts)    state.counts[r.id]    = p.counts[r.id];
    if (r.id in p.locked)    state.locked[r.id]    = p.locked[r.id];
    if (r.id in p.lastCount) state.lastCount[r.id] = p.lastCount[r.id];
  });
  state.breaks = JSON.parse(JSON.stringify(p.breaks));
  state.selectedStart = p.selectedStart;
  state.timePinned = JSON.parse(JSON.stringify(p.timePinned || {}));
  RIDES.forEach(r => {
    const savedMax = (p.maxCounts || {})[r.id];
    state.maxCounts[r.id] = (savedMax === null || savedMax === undefined) ? Infinity : savedMax;
    state.maxBeforeInfinity[r.id] = (p.maxBeforeInfinity || {})[r.id] ?? 0;
    state.maxWasZeroBeforeLock[r.id] = (p.maxWasZeroBeforeLock || {})[r.id] ?? false;
  });
  state.pinnedLocked = { ...(p.pinnedLocked || {}) };
  selectedPresetId = p.id;
  renderStartDropdown();
  renderSidebarList();
  renderPresetDropdown();
}

// ── DOM refs ────────────────────────────────────────────────────
const $ = sel => document.querySelector(sel);
const sidebarEl        = $('#sidebar');
const topBarEl          = $('#topBar');
const sidebarListEl     = $('#sidebarList');
const popupEl           = $('#popup');
const pinLayerEl        = $('#pinLayer');
const mapImageEl        = $('#mapImage');
const mapInnerEl        = $('#mapInner');
const mapViewportEl     = $('#mapViewport');
const routeItemsEl      = $('#routeItems');
const routePlaceholderEl= $('#routePlaceholder');
const mapPaneEl = $('#mapPane');

// ═══════════════ DROPDOWNS ═══════════════

function setupDropdown({ dropdown }) {
  dropdown.addEventListener('click', e => {
    const isBtn = e.target.closest('.dropdown-btn');
    if (isBtn) {
      const wasOpen = dropdown.classList.contains('open');
      closeAllDropdowns();
      if (!wasOpen) dropdown.classList.add('open');
    }
  });
}

function closeAllDropdowns() {
  document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
}

document.addEventListener('click', e => {
  if (!e.target.closest('.dropdown')) closeAllDropdowns();
});

function renderStartDropdown() {
  const list = $('#startDropdownList');
  list.innerHTML = '';
  startOptions.forEach(opt => {
    const li = document.createElement('li');
    li.className = opt.id === state.selectedStart ? 'selected' : '';
    const span = document.createElement('span');
    span.className = 'item-label';
    span.textContent = opt.label.replace(/\n/g, ' ');
    li.appendChild(span);
    li.addEventListener('click', () => {
      state.selectedStart = opt.id;
      renderStartDropdown();
      closeAllDropdowns();
    });
    list.appendChild(li);
  });
  $('#startDropdownLabel').textContent = startOptions.find(o => o.id === state.selectedStart)?.label || 'Entrance';
}

function renderPresetDropdown() {
  const list = $('#presetDropdownList');
  list.innerHTML = '';
  if (!presets.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = 'No presets saved';
    list.appendChild(li);
  } else {
    presets.forEach(p => {
      const li = document.createElement('li');
      li.className = p.id === selectedPresetId ? 'selected' : '';
      const span = document.createElement('span');
      span.className = 'item-label';
      span.textContent = p.name;
      span.addEventListener('click', () => { applyPreset(p.id); closeAllDropdowns(); });
      const x = document.createElement('button');
      x.className = 'mini-x';
      x.textContent = '✕';
      x.addEventListener('click', ev => { ev.stopPropagation(); deletePreset(p.id); });
      li.appendChild(span);
      li.appendChild(x);
      list.appendChild(li);
    });
  }
  const label = presets.find(p => p.id === selectedPresetId)?.name
    || (presets.length ? 'Select preset…' : '');
  $('#presetDropdownLabel').textContent = label;
}

setupDropdown({ dropdown: $('#startDropdown') });
setupDropdown({ dropdown: $('#presetDropdown') });

// ═══════════════ BREAKS ═══════════════

function parseTimeInput(text) {
  const m = /^(\d{1,2})(?::(\d{2}))?$/.exec(text.trim());
  if (!m) return null;
  const hour = parseInt(m[1], 10);
  const minute = m[2] ? parseInt(m[2], 10) : 0;
  if (hour < 1 || hour > 12 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

function toAmPm(hour, minute) {
  let period, hour24;
  if ([9, 10, 11].includes(hour)) { period = 'AM'; hour24 = hour; }
  else { period = 'PM'; hour24 = hour === 12 ? 12 : hour + 12; }
  const totalMinutes = hour24 * 60 + minute;
  const label = `${hour}:${String(minute).padStart(2, '0')} ${period}`;
  return { totalMinutes, label };
}

function flashTimeError() {
  const t1 = $('#time1Input'), t2 = $('#time2Input');
  t1.classList.add('error'); t2.classList.add('error');
  setTimeout(() => { t1.classList.remove('error'); t2.classList.remove('error'); t1.value = ''; t2.value = ''; }, 1400);
}

$('#generateBreakBtn').addEventListener('click', () => {
  const t1 = parseTimeInput($('#time1Input').value);
  const t2 = parseTimeInput($('#time2Input').value);
  if (!t1 || !t2) return flashTimeError();
  const a = toAmPm(t1.hour, t1.minute);
  const b = toAmPm(t2.hour, t2.minute);
  if (b.totalMinutes <= a.totalMinutes) return flashTimeError();
  breakIdCounter += 1;
  state.breaks.unshift({
    id: breakIdCounter,
    label: `Break: ${a.label} – ${b.label}`,
    startMin: a.totalMinutes,
    endMin: b.totalMinutes,
  });
  $('#time1Input').value = '';
  $('#time2Input').value = '';
  renderSidebarList();
});

$('#addPresetBtn').addEventListener('click', addPreset);

// ═══════════════ SIDEBAR RIDE LIST ═══════════════

function renderSidebarList() {
  sidebarListEl.innerHTML = '';

  state.breaks.forEach(b => {
    const row = document.createElement('div');
    row.className = 'row break-row';
    const label = document.createElement('span');
    label.className = 'break-row-label';
    label.textContent = b.label;
    const x = document.createElement('button');
    x.className = 'mini-x';
    x.textContent = '✕';
    x.addEventListener('click', () => {
      state.breaks = state.breaks.filter(br => br.id !== b.id);
      renderSidebarList();
    });
    row.appendChild(x);
    row.appendChild(label);
    sidebarListEl.appendChild(row);
  });

  RIDES.forEach(r => {
    const row = document.createElement('div');
    row.className = 'row';

    const cb = document.createElement('div');
    cb.className = 'checkbox' + (state.visible[r.id] ? ' checked' : '');
    cb.addEventListener('click', () => {
      state.visible[r.id] = !state.visible[r.id];
      if (state.visible[r.id]) {
        state.counts[r.id] = state.lastCount[r.id];
      } else {
        state.lastCount[r.id] = state.counts[r.id];
        state.counts[r.id] = 0;
        state.locked[r.id] = false;
        if (popupState.rideId === r.id) hidePopup();
      }
      renderSidebarList();
      renderPins();
    });

    const name = document.createElement('span');
    name.className = 'ride-name';
    // displayName (if set on a RIDES entry) overrides just the sidebar
    // label -- everything else (popup title... see showPopup below,
    // pin/img alt text, route-pill fallback text) still reads r.name.
    name.textContent = (r.displayName ?? r.name).replace(/\n/g, ' ');

    // ── min (white) spinner ──────────────────────────────────────
    const spinner = document.createElement('div');
    spinner.className = 'spinner';

    const down = document.createElement('button');
    down.className = 'spin-btn';
    down.disabled = state.counts[r.id] <= 0;
    down.innerHTML = '<svg viewBox="0 0 10 10"><polygon points="1,2 9,2 5,8"/></svg>';
    down.addEventListener('click', () => {
      const old = state.counts[r.id];
      const next = Math.max(0, old - 1);
      state.counts[r.id] = next;
      if (old === 2 && next === 1) {
        state.locked[r.id] = state.lockBeforeBump[r.id];
        if (!state.lockBeforeBump[r.id] && state.maxWasZeroBeforeLock[r.id]) {
          state.maxCounts[r.id] = 0;
          state.maxWasZeroBeforeLock[r.id] = false;
        }
      }
      if (next === 0 && old > 0) {
        state.lastCount[r.id] = old;
        state.visible[r.id] = false;
        state.locked[r.id] = false;
        if (popupState.rideId === r.id) hidePopup();
      }
      renderSidebarList();
      renderPins();
    });

    const count = document.createElement('span');
    count.className = 'spin-count';
    count.textContent = state.counts[r.id];

    const up = document.createElement('button');
    up.className = 'spin-btn';
    up.innerHTML = '<svg viewBox="0 0 10 10"><polygon points="1,8 9,8 5,2"/></svg>';
    up.addEventListener('click', () => {
      const old = state.counts[r.id];
      state.counts[r.id] = old + 1;
      if (!state.visible[r.id]) state.visible[r.id] = true;
      if (old === 1) {
        state.lockBeforeBump[r.id] = state.locked[r.id];
        state.locked[r.id] = true;
        if (state.maxCounts[r.id] === 0) {
          state.maxWasZeroBeforeLock[r.id] = true;
          state.maxCounts[r.id] = 1;
        } else {
          state.maxWasZeroBeforeLock[r.id] = false;
        }
      }
      renderSidebarList();
      renderPins();
    });

    spinner.append(down, count, up);

    // ── max (maroon) spinner ─────────────────────────────────────
    const maxSpinner = document.createElement('div');
    maxSpinner.className = 'spinner';

    const maxDown = document.createElement('button');
    maxDown.className = 'spin-btn max-spin-btn';
    maxDown.disabled = state.maxCounts[r.id] !== Infinity && (
      state.maxCounts[r.id] === 0 ||
      (state.locked[r.id] && state.maxCounts[r.id] <= 1)
    );
    maxDown.innerHTML = '<svg viewBox="0 0 10 10"><polygon points="1,2 9,2 5,8"/></svg>';
    maxDown.addEventListener('click', () => {
      const floor = state.locked[r.id] ? 1 : 0;
      if (state.maxCounts[r.id] === Infinity) {
        state.maxCounts[r.id] = Math.max(floor, state.maxBeforeInfinity[r.id] || 0);
      } else {
        state.maxCounts[r.id] = Math.max(floor, state.maxCounts[r.id] - 1);
      }
      renderSidebarList();
    });

    const maxCountEl = document.createElement('span');
    maxCountEl.className = 'spin-count max-count';
    maxCountEl.textContent = state.maxCounts[r.id] === Infinity ? '∞' : state.maxCounts[r.id];

    const maxUp = document.createElement('button');
    maxUp.className = 'spin-btn max-spin-btn';
    maxUp.innerHTML = '<svg viewBox="0 0 10 10"><polygon points="1,8 9,8 5,2"/></svg>';
    maxUp.addEventListener('click', () => {
      if (state.maxCounts[r.id] === Infinity) {
        state.maxCounts[r.id] = (state.maxBeforeInfinity[r.id] > 0 ? state.maxBeforeInfinity[r.id] : 0) + 1;
      } else {
        state.maxCounts[r.id]++;
      }
      renderSidebarList();
    });

    maxSpinner.append(maxDown, maxCountEl, maxUp);

    const infBtn = document.createElement('button');
    infBtn.className = 'infinity-btn' + (state.maxCounts[r.id] === Infinity ? ' active' : '');
    infBtn.textContent = '∞';
    infBtn.title = 'No maximum';
    infBtn.addEventListener('click', () => {
      if (state.maxCounts[r.id] !== Infinity) {
        state.maxBeforeInfinity[r.id] = state.maxCounts[r.id];
        state.maxCounts[r.id] = Infinity;
        renderSidebarList();
      }
    });

    // ── lock button ──────────────────────────────────────────────
    const lockable = state.visible[r.id] && state.counts[r.id] > 0;
    if (!lockable) state.locked[r.id] = false;
    const lock = document.createElement('button');
    lock.className = 'lock-btn' + (state.locked[r.id] ? ' locked' : '') + (lockable ? '' : ' disabled');
    lock.innerHTML = state.locked[r.id]
      ? '<svg viewBox="0 0 14 14"><rect x="3" y="6" width="8" height="6" rx="1"/><path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2"/></svg>'
      : '<svg viewBox="0 0 14 14"><rect x="3" y="6" width="8" height="6" rx="1"/><path d="M4.5 6V4a2.5 2.5 0 0 1 5 0"/></svg>';
    lock.addEventListener('click', () => {
      if (!lockable) return;
      const newLocked = !state.locked[r.id];
      state.locked[r.id] = newLocked;
      if (newLocked) {
        if (state.maxCounts[r.id] === 0) {
          state.maxWasZeroBeforeLock[r.id] = true;
          state.maxCounts[r.id] = 1;
        } else {
          state.maxWasZeroBeforeLock[r.id] = false;
        }
      } else {
        if (state.maxWasZeroBeforeLock[r.id]) {
          state.maxCounts[r.id] = 0;
          state.maxWasZeroBeforeLock[r.id] = false;
        }
      }
      renderSidebarList();
    });

    row.append(cb, name, spinner, maxSpinner, infBtn, lock);
    sidebarListEl.appendChild(row);
  });
}

// ═══════════════ MAP PINS + POPUP ═══════════════

const popupState = { rideId: null, anchorEl: null };

let pinElements = [];


function renderPins() {
  pinLayerEl.innerHTML = '';
  pinElements = [];
  RIDES.forEach(r => {
    if (!state.visible[r.id]) return;
    const pin = document.createElement('button');
    pin.className = 'pin';
    if (state.liveOpen[r.id] === false) pin.classList.add('closed');
    const img = document.createElement('img');
    img.src = r.icon;
    img.alt = r.name;

    img.draggable = false;
    img.style.setProperty('--icon-brightness', r.brightness ?? 1.4);
    img.onerror = () => { img.style.display = 'none'; pin.textContent = r.name.split(' ')[0]; };
    pin.appendChild(img);


    pin.addEventListener('contextmenu', e => e.preventDefault());

    const pinEntry = { el: pin, rideId: r.id, mx: r.x, my: r.y, sizeMult: r.sizeMult ?? 1 };
    pinElements.push(pinEntry);

    pin.addEventListener('click', e => {
      e.stopPropagation();
      const now = Date.now();
      if (now - lastPinTapTime < DOUBLE_TAP_MS && lastPinTapRideId === r.id) {
        lastPinTapTime = 0;
        lastPinTapRideId = null;
        hidePopup();
        toggleWaitBubbles();
        return;
      }
      lastPinTapTime = now;
      lastPinTapRideId = r.id;
      showPopup(r.id, pin);
    });

    pinLayerEl.appendChild(pin);
  });
  updatePinLayout();
}

function showPopup(rideId, anchorEl) {
  popupState.rideId = rideId;
  popupState.anchorEl = anchorEl;
  const r = rideById[rideId];
  const wait = state.liveWaits[rideId];
  const isOpen = state.liveOpen[rideId];
  let waitLine, waitCls = '';
  if (wait == null && isOpen !== false) { waitLine = 'Loading…'; }
  else if (isOpen === false) { waitLine = 'Ride is currently closed'; waitCls = 'closed'; }
  else { waitLine = `Wait: ${wait} min`; }

  popupEl.innerHTML = `${(r.displayName ?? r.name).replace(/\n/g, '<br>')}<div class="wait-line ${waitCls}">${waitLine}</div>`;
  popupEl.classList.toggle('closed', isOpen === false);
  popupEl.classList.remove('hidden');
  positionPopup(anchorEl);
}

function positionPopup(anchorEl) {
  if (!anchorEl || popupState.rideId == null) return;
  const pinRect = anchorEl.getBoundingClientRect();
  popupEl.style.left = (pinRect.left + pinRect.width / 2) + 'px';
  popupEl.style.top  = pinRect.top + 'px';
}

function hidePopup() {
  popupState.rideId = null;
  popupState.anchorEl = null;
  popupEl.classList.add('hidden');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.pin') && !e.target.closest('.popup')) hidePopup();

  if (showWaitBubbles
      && !e.target.closest('.pin')
      && !e.target.closest('#sidebar')
      && !e.target.closest('#topBar')
      && !e.target.closest('#bottomBar')
      && !e.target.closest('.edge-toggle')
      && !e.target.closest('.dropdown')) {
    toggleWaitBubbles();
  }
});

// ═══════════════ MAP ZOOM & PAN ═══════════════

const MIN_MAP_ZOOM = 1;
const MAX_MAP_ZOOM = 4;

function lerp(a, b, t) { return a + (b - a) * t; }

// 0 at fully zoomed out, 1 at fully zoomed in, eased so the shift feels
// gradual rather than linear/abrupt.
function zoomT() {
  const raw = (mapZoom - MIN_MAP_ZOOM) / (MAX_MAP_ZOOM - MIN_MAP_ZOOM);
  const c = Math.min(1, Math.max(0, raw));
  return c * c * (3 - 2 * c);
}


const WHEEL_ZOOM_RATIO = 1.12; 

const WHEEL_ZOOM_SENSITIVITY = 0.0015;

let mapZoom = 1;
let mapPanX = 0;
let mapPanY = 0;
let mapFitWidth = 0;

const PIN_SIZE = 54 * 0.9 * 1.1;

// ── all-rides wait bubbles (toggled by double-tapping any wait chip) ──
const waitBubbleLayerEl = document.getElementById('waitBubbleLayer');
let showWaitBubbles = false;
let waitBubbleElements = [];
let lastWaitChipTapTime = 0; 
const DOUBLE_TAP_MS = 350;
let lastPinTapTime = 0;
let lastPinTapRideId = null;

function renderWaitBubbles() {
  waitBubbleLayerEl.innerHTML = '';
  waitBubbleElements = [];
  if (!showWaitBubbles) { return; }
  RIDES.forEach(r => {
    const wait = state.liveWaits[r.id];
    const isOpen = state.liveOpen[r.id];
    if (wait == null && isOpen !== false) return;
    const bubble = document.createElement('div');
    bubble.className = 'wait-bubble' + (isOpen === false ? ' closed' : '');
    bubble.textContent = isOpen === false ? 'Closed' : `${wait}m`;
    waitBubbleLayerEl.appendChild(bubble);
    waitBubbleElements.push({ el: bubble, rideId: r.id });
  });
  updateBubbleLayout();
}

function updateBubbleLayout() {
  if (!mapFitWidth) return;
  const fitH = mapFitWidth * (MAP_NATIVE_H / MAP_NATIVE_W);
  const t = zoomT();
  waitBubbleElements.forEach(({ el, rideId }) => {
    const r = rideById[rideId];
    const centerX = mapPanX + (lerp(r.x, r.realX, t) / MAP_NATIVE_W) * mapFitWidth * mapZoom;
    const centerY = mapPanY + (lerp(r.y, r.realY, t) / MAP_NATIVE_H) * fitH * mapZoom;
    el.style.left = centerX + 'px';
    el.style.top  = (centerY - PIN_SIZE / 2) + 'px'; 
  });
}

function toggleWaitBubbles() {
  showWaitBubbles = !showWaitBubbles;
  renderWaitBubbles();
}

function pinSizeForZoom() {
  return PIN_SIZE;
}

function updatePinLayout() {
  if (!mapFitWidth) return;
  const fitH = mapFitWidth * (MAP_NATIVE_H / MAP_NATIVE_W);
  const t = zoomT();
  pinElements.forEach(entry => {
    const r = rideById[entry.rideId];
    const mx = lerp(r.x, r.realX, t);
    const my = lerp(r.y, r.realY, t);
    entry.mx = mx;
    entry.my = my;

    const size = PIN_SIZE * (entry.sizeMult ?? 1);
    entry.el.style.width  = size + 'px';
    entry.el.style.height = size + 'px';
    entry.el.style.left   = (mapPanX + (mx / MAP_NATIVE_W) * mapFitWidth * mapZoom) + 'px';
    entry.el.style.top    = (mapPanY + (my / MAP_NATIVE_H) * fitH * mapZoom) + 'px';
  });

  if (popupState.rideId && popupState.anchorEl) {
    positionPopup(popupState.anchorEl);
  }

  updateBubbleLayout();
}


let mapViewportRect = mapViewportEl.getBoundingClientRect();
function refreshMapViewportRect() { mapViewportRect = mapViewportEl.getBoundingClientRect(); }

function computeMapFitWidth() {
  const natural = mapImageEl.naturalWidth || MAP_NATIVE_W;
  const available = mapViewportEl.clientWidth || natural;
  mapFitWidth = Math.min(natural, available);
  mapImageEl.style.maxWidth = 'none';
  mapImageEl.style.width = mapFitWidth + 'px';
}

// Keeps the map from ever being panned/zoomed off-screen. If the scaled
// image is smaller than the viewport on an axis, it's centered on that
// axis (no free panning needed); if it's bigger, panning is clamped so
// neither edge of the image can pull inward past the viewport's edge.
function clampMapPan() {
  const viewportW = mapViewportEl.clientWidth;
  const viewportH = mapViewportEl.clientHeight;
  const baseW = mapImageEl.offsetWidth || mapFitWidth;
  const baseH = mapImageEl.offsetHeight || (baseW * (MAP_NATIVE_H / MAP_NATIVE_W));
  const scaledW = baseW * mapZoom;
  const scaledH = baseH * mapZoom;

  if (scaledW <= viewportW) {
    mapPanX = (viewportW - scaledW) / 2;
  } else {
    mapPanX = Math.min(0, Math.max(viewportW - scaledW, mapPanX));
  }

  if (scaledH <= viewportH) {
    mapPanY = (viewportH - scaledH) / 2;
  } else {
    mapPanY = Math.min(0, Math.max(viewportH - scaledH, mapPanY));
  }
}

function applyMapTransform() {
  mapInnerEl.style.transform = `translate(${mapPanX}px, ${mapPanY}px) scale(${mapZoom})`;
  updatePinLayout();
}

function clampZoom(z) {
  return Math.min(MAX_MAP_ZOOM, Math.max(MIN_MAP_ZOOM, z));
}

// ── zoom/pan gesture engine ──
function zoomAtPoint(targetZoomRaw, clientX, clientY, baseZoom, basePanX, basePanY) {
  const targetZoom = clampZoom(targetZoomRaw);
  const rect = mapViewportRect;
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  const imgX = (px - basePanX) / baseZoom;
  const imgY = (py - basePanY) / baseZoom;
  mapZoom = targetZoom;
  mapPanX = px - imgX * mapZoom;
  mapPanY = py - imgY * mapZoom;
  clampMapPan();
  applyMapTransform();
}

// ── wheel / trackpad zoom, centered on the cursor ──
let wheelRatioAccum = 1;
let wheelClientX = 0, wheelClientY = 0;
let wheelFrameQueued = false;

mapViewportEl.addEventListener('wheel', e => {
  e.preventDefault();
  const deltaY = Math.max(-200, Math.min(200, e.deltaY));
  wheelRatioAccum *= Math.exp(-deltaY * WHEEL_ZOOM_SENSITIVITY);
  wheelClientX = e.clientX;
  wheelClientY = e.clientY;
  if (!wheelFrameQueued) {
    wheelFrameQueued = true;
    requestAnimationFrame(() => {
      wheelFrameQueued = false;
      const ratio = wheelRatioAccum;
      wheelRatioAccum = 1;
      refreshMapViewportRect();
      zoomAtPoint(mapZoom * ratio, wheelClientX, wheelClientY, mapZoom, mapPanX, mapPanY);
    });
  }
}, { passive: false });

let zoomAnimClearTimer = null;
mapImageEl.addEventListener('dblclick', e => {
  refreshMapViewportRect();
  const targetZoom = mapZoom >= MAX_MAP_ZOOM - 0.001
    ? MIN_MAP_ZOOM
    : Math.min(MAX_MAP_ZOOM, mapZoom * WHEEL_ZOOM_RATIO * WHEEL_ZOOM_RATIO);
  mapInnerEl.classList.add('map-zoom-anim');
  pinLayerEl.classList.add('pin-zoom-anim');
  waitBubbleLayerEl.classList.add('pin-zoom-anim');
  zoomAtPoint(targetZoom, e.clientX, e.clientY, mapZoom, mapPanX, mapPanY);
  clearTimeout(zoomAnimClearTimer);
  zoomAnimClearTimer = setTimeout(() => {
    mapInnerEl.classList.remove('map-zoom-anim');
    pinLayerEl.classList.remove('pin-zoom-anim');
    waitBubbleLayerEl.classList.remove('pin-zoom-anim');
  }, 260);
});

// ── mouse drag-to-pan ──
let panPointerId = null;
let panStartX = 0, panStartY = 0, panStartPanX = 0, panStartPanY = 0;
let isPanning = false;

mapViewportEl.addEventListener('pointerdown', e => {
  if (e.pointerType !== 'mouse') return;
  if (e.target.closest('.pin') || e.target.closest('.popup')) return;
  refreshMapViewportRect();
  panPointerId = e.pointerId;
  panStartX = e.clientX;
  panStartY = e.clientY;
  panStartPanX = mapPanX;
  panStartPanY = mapPanY;
  isPanning = false;
});

mapViewportEl.addEventListener('pointermove', e => {
  if (panPointerId !== e.pointerId) return;
  const dx = e.clientX - panStartX;
  const dy = e.clientY - panStartY;
  if (!isPanning) {
    if (Math.hypot(dx, dy) < 6) return;
    isPanning = true;
    mapViewportEl.setPointerCapture(panPointerId);
    mapViewportEl.classList.add('panning');
  }
  mapPanX = panStartPanX + dx;
  mapPanY = panStartPanY + dy;
  clampMapPan();
  applyMapTransform();
});

function endMapPan(e) {
  if (panPointerId !== e.pointerId) return;
  if (isPanning) mapViewportEl.releasePointerCapture(panPointerId);
  panPointerId = null;
  isPanning = false;
  mapViewportEl.classList.remove('panning');
}
mapViewportEl.addEventListener('pointerup', endMapPan);
mapViewportEl.addEventListener('pointercancel', endMapPan);

// ── touch: single-finger pan, two-finger pinch-to-zoom ──
let t1Id = null, t2Id = null;
let t1 = { x: 0, y: 0 }, t2 = { x: 0, y: 0 };
let panBase = null;
let pinchBase = null; 
let touchFlushPending = false;

function startPanBase() {
  pinchBase = null;
  panBase = { startX: t1.x, startY: t1.y, startPanX: mapPanX, startPanY: mapPanY };
}

function startPinchBase() {
  panBase = null;
  const midX = (t1.x + t2.x) / 2;
  const midY = (t1.y + t2.y) / 2;
  const dist = Math.hypot(t2.x - t1.x, t2.y - t1.y);
  const rect = mapViewportRect;
  pinchBase = {
    imgX: (midX - rect.left - mapPanX) / mapZoom,
    imgY: (midY - rect.top  - mapPanY) / mapZoom,
    startDist: dist,
    startZoom: mapZoom,
  };
}

function flushTouchGesture() {
  touchFlushPending = false;
  if (pinchBase) {
    const midX = (t1.x + t2.x) / 2;
    const midY = (t1.y + t2.y) / 2;
    const dist = Math.hypot(t2.x - t1.x, t2.y - t1.y);
    if (pinchBase.startDist < 8 || dist < 8) return;
    const newZoom = clampZoom(pinchBase.startZoom * (dist / pinchBase.startDist));
    const rect = mapViewportRect;
    mapZoom = newZoom;
    mapPanX = (midX - rect.left) - pinchBase.imgX * newZoom;
    mapPanY = (midY - rect.top)  - pinchBase.imgY * newZoom;
    clampMapPan();
    applyMapTransform();
  } else if (panBase) {
    mapPanX = panBase.startPanX + (t1.x - panBase.startX);
    mapPanY = panBase.startPanY + (t1.y - panBase.startY);
    clampMapPan();
    applyMapTransform();
  }
}

function scheduleTouchFlush() {
  if (!touchFlushPending) {
    touchFlushPending = true;
    requestAnimationFrame(flushTouchGesture);
  }
}

mapViewportEl.addEventListener('touchstart', e => {
  refreshMapViewportRect();
  for (let i = 0; i < e.changedTouches.length; i++) {
    const t = e.changedTouches[i];
    if (t1Id === null) {
      t1Id = t.identifier; t1 = { x: t.clientX, y: t.clientY };
    } else if (t2Id === null && t.identifier !== t1Id) {
      t2Id = t.identifier; t2 = { x: t.clientX, y: t.clientY };
    }
  }
  if (t2Id !== null) startPinchBase();
  else startPanBase();
}, { passive: true });

mapViewportEl.addEventListener('touchmove', e => {
  if (!pinchBase && e.target.closest('.pin')) return;
  e.preventDefault();
  for (let i = 0; i < e.changedTouches.length; i++) {
    const t = e.changedTouches[i];
    if (t.identifier === t1Id)      t1 = { x: t.clientX, y: t.clientY };
    else if (t.identifier === t2Id) t2 = { x: t.clientX, y: t.clientY };
  }
  scheduleTouchFlush();
}, { passive: false });

mapViewportEl.addEventListener('touchend', e => {
  for (let i = 0; i < e.changedTouches.length; i++) {
    const id = e.changedTouches[i].identifier;
    if (id === t1Id) {
      if (t2Id !== null) { t1Id = t2Id; t1 = { ...t2 }; t2Id = null; }
      else t1Id = null;
    } else if (id === t2Id) {
      t2Id = null;
    }
  }
  if (t1Id !== null && t2Id === null) startPanBase();
  else if (t1Id === null) { panBase = null; pinchBase = null; }
}, { passive: true });

mapViewportEl.addEventListener('touchcancel', () => {
  t1Id = null; t2Id = null;
  panBase = null; pinchBase = null;
}, { passive: true });

// ═══════════════ TOP ROUTE BAR ═══════════════
function renderRouteBar() {
  if (!state.route.length) {
    routePlaceholderEl.style.display = 'block';
    routeItemsEl.classList.remove('active');
    routeItemsEl.innerHTML = '';
    return;
  }
  routePlaceholderEl.style.display = 'none';
  routeItemsEl.classList.add('active');
  routeItemsEl.innerHTML = '';

  const isMobile = window.matchMedia('(max-width: 760px)').matches;
  const bigRow   = isMobile ? 4 : 6;
  const smallRow = isMobile ? 3 : 5;
  const total    = state.route.length;

  const rows = [];
  if (total <= bigRow) {
    // Single row — everything fits
    rows.push({ start: 0, end: total });
  } else if (total <= bigRow * 2) {
    // Two rows — first fills to bigRow, second gets the rest, no alternating
    rows.push({ start: 0,      end: bigRow });
    rows.push({ start: bigRow, end: total  });
  } else {
    // 3+ rows — alternating bigRow / smallRow pattern
    let cursor = 0, parity = 0;
    while (cursor < total) {
      const size = parity % 2 === 0 ? bigRow : smallRow;
      rows.push({ start: cursor, end: Math.min(cursor + size, total) });
      cursor += size;
      parity++;
    }
  }

  rows.forEach(({ start, end }) => {
    const rowEl = document.createElement('div');
    rowEl.className = 'route-row';

    for (let i = start; i < end; i++) {
      const stop = state.route[i];
      const r = rideById[stop.rideId];
      if (!r) continue;

      const instIdx    = getInstanceIndex(state.route, i);
      const uniqueKey  = getUniqueKey(stop.rideId, instIdx);
      const pinEntry   = state.timePinned[uniqueKey];
      const isLocked   = pinEntry && pinEntry.targetMinutes !== null;
      const isHighlighted = !!pinEntry;

      const wrap = document.createElement('div');
      wrap.className = 'route-stop';
      wrap.draggable = true;
      wrap.dataset.idx = i;

      // ── mouse drag ───────────────────────────────────────────
      wrap.addEventListener('dragstart', e => {
        dragSrcIdx = i;
        wrap.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      wrap.addEventListener('dragend', () => {
        dragSrcIdx = null;
        document.querySelectorAll('.route-stop').forEach(el =>
          el.classList.remove('dragging', 'drag-over'));
      });

      wrap.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (dragSrcIdx !== null && dragSrcIdx !== i) {
          document.querySelectorAll('.route-stop').forEach(el => el.classList.remove('drag-over'));
          wrap.classList.add('drag-over');
        }
      });

      wrap.addEventListener('dragleave', () => wrap.classList.remove('drag-over'));

      wrap.addEventListener('drop', e => {
        e.preventDefault();
        wrap.classList.remove('drag-over');
        const src = dragSrcIdx;
        dragSrcIdx = null;
        executeDrop(src, i);
      });

      // ── touch drag ───────────────────────────────────────────
      wrap.addEventListener('touchstart', e => {
        const touch = e.touches[0];
        touchStartX     = touch.clientX;
        touchStartY     = touch.clientY;
        touchDragSrcIdx = i;
        touchDragging   = false;
      }, { passive: true });

      wrap.addEventListener('touchmove', e => {
        if (touchDragSrcIdx === null) return;
        const touch = e.touches[0];
        const dx = touch.clientX - touchStartX;
        const dy = touch.clientY - touchStartY;

        if (!touchDragging) {
          if (Math.hypot(dx, dy) < 8) return;
          touchDragging = true;
          wrap.classList.add('dragging');
          touchDragClone = wrap.cloneNode(true);
          Object.assign(touchDragClone.style, {
            position: 'fixed', pointerEvents: 'none', opacity: '0.85',
            zIndex: '9999', width: wrap.offsetWidth + 'px',
            transform: 'scale(1.05)', transition: 'none',
            left: (touch.clientX - wrap.offsetWidth / 2) + 'px',
            top:  (touch.clientY - 30) + 'px',
          });
          document.body.appendChild(touchDragClone);
        }

        e.preventDefault();
        touchDragClone.style.left = (touch.clientX - touchDragClone.offsetWidth / 2) + 'px';
        touchDragClone.style.top  = (touch.clientY - 30) + 'px';

        if (touchDragClone) touchDragClone.style.visibility = 'hidden';
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        if (touchDragClone) touchDragClone.style.visibility = '';
        const overStop = el?.closest('.route-stop');
        document.querySelectorAll('.route-stop').forEach(s => s.classList.remove('drag-over'));
        if (overStop && overStop !== wrap) overStop.classList.add('drag-over');
      }, { passive: false });

      wrap.addEventListener('touchend', e => {
        if (!touchDragging) {
          touchDragSrcIdx = null;
          return;
        }
        const touch = e.changedTouches[0];
        if (touchDragClone) touchDragClone.style.visibility = 'hidden';
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        touchDragClone?.remove();
        touchDragClone = null;
        wrap.classList.remove('dragging');
        document.querySelectorAll('.route-stop').forEach(s => s.classList.remove('drag-over'));
        const overStop = el?.closest('.route-stop');
        const dropIdx  = overStop ? parseInt(overStop.dataset.idx) : -1;
        const src = touchDragSrcIdx;
        touchDragSrcIdx = null;
        touchDragging   = false;
        if (dropIdx >= 0 && dropIdx !== src) executeDrop(src, dropIdx);
      });

      // ── card ─────────────────────────────────────────────────
      const card = document.createElement('div');
      card.className = 'route-stop-card';

      const pill = document.createElement('div');
      pill.className = 'route-pill'
        + (isLocked ? ' time-locked' : isHighlighted ? ' highlighted' : '');

      let pointerDownX = 0, pointerDownY = 0;
      pill.addEventListener('pointerdown', e => { pointerDownX = e.clientX; pointerDownY = e.clientY; });
      pill.addEventListener('pointerup', e => {
        const dist = Math.hypot(e.clientX - pointerDownX, e.clientY - pointerDownY);
        if (dist > 8) return;
        if (pinEntry) {
          delete state.timePinned[uniqueKey];
          const anyStillPinned = Object.keys(state.timePinned).some(k => k.startsWith(`${stop.rideId}:`));
          if (!anyStillPinned && state.pinnedLocked[stop.rideId]) {
            state.locked[stop.rideId] = false;
            delete state.pinnedLocked[stop.rideId];
          }
        } else {
          const isFirst = i === 0;
          const isLast  = i === state.route.length - 1;
          state.timePinned[uniqueKey] = {
            rideId: stop.rideId,
            instanceIndex: instIdx,
            targetMinutes: isFirst ? 0 : isLast ? 1440 : (stop.queueJoinMinutes ?? null),
          };
          if (isFirst) clearConflictingSentinelPins(0, uniqueKey);
          if (isLast)  clearConflictingSentinelPins(1440, uniqueKey);
          if (!state.locked[stop.rideId]) {
            state.locked[stop.rideId] = true;
            state.pinnedLocked[stop.rideId] = true;
          }
          ensureMinCountMatchesPinnedInstances(stop.rideId);
        }
        renderRouteBar();
        renderSidebarList();
      });

      const img = document.createElement('img');
      img.src = r.icon;
      img.alt = r.name;
      img.draggable = false;
      img.onerror = () => { img.remove(); pill.innerHTML = `<span>${r.name.split(' ')[0]}</span>`; };
      pill.appendChild(img);

      const chip = document.createElement('span');
      chip.className = 'wait-chip';
      chip.textContent = stop.predictedWait == null ? '--' : `${Math.round(stop.predictedWait)}m`;
      chip.addEventListener('click', e => {
        e.stopPropagation();
        const now = Date.now();
        if (now - lastWaitChipTapTime < DOUBLE_TAP_MS) {
          lastWaitChipTapTime = 0;
          toggleWaitBubbles();
        } else {
          lastWaitChipTapTime = now;
        }
      });

      const timeChip = document.createElement('span');
      timeChip.className = 'time-chip';
      timeChip.textContent = minsToTime(stop.queueJoinMinutes);

      const remove = document.createElement('button');
      remove.className = 'stop-remove';
      remove.textContent = '✕';
      remove.addEventListener('click', () => {
        delete state.timePinned[uniqueKey];
        state.route.splice(i, 1);
        const remaining = state.route.filter(s => s.rideId === stop.rideId).length;
        state.maxBeforeInfinity[stop.rideId] = remaining;
        state.maxCounts[stop.rideId] = remaining;
        const anyStillPinned = Object.keys(state.timePinned).some(k => k.startsWith(`${stop.rideId}:`));
        if (!anyStillPinned && state.pinnedLocked[stop.rideId]) {
          state.locked[stop.rideId] = false;
          delete state.pinnedLocked[stop.rideId];
        }
        if (remaining === 0) {
          state.visible[stop.rideId] = false;
          state.locked[stop.rideId] = false;
          state.counts[stop.rideId] = 0;
          delete state.pinnedLocked[stop.rideId];
        }
        renderRouteBar();
        renderSidebarList();
        renderPins();
      });

      const chipGroup = document.createElement('div');
      chipGroup.className = 'chip-group';
      chipGroup.append(chip, timeChip);
      card.append(pill, chipGroup, remove);
      wrap.appendChild(card);
      rowEl.appendChild(wrap);

      // Arrow between stops within this row only (not after the last in the row)
      if (i < end - 1) {
        const arrow = document.createElement('span');
        arrow.className = 'route-arrow';
        arrow.textContent = '→';
        rowEl.appendChild(arrow);
      }
    }

    routeItemsEl.appendChild(rowEl);
  });
}

// ═══════════════ ROUTE GENERATION ═══════════════

function extractRideIdAndWait(entry) {
  if (Array.isArray(entry)) {
    return {
      rideId:            entry.length > 0 ? entry[0] : undefined,
      predictedWait:     entry.length > 1 ? entry[1] : null,
      queueJoinMinutes:  entry.length > 2 ? entry[2] : null,
    };
  }
  if (entry && typeof entry === 'object') {
    return {
      rideId:           entry.ride_id ?? entry.id ?? entry.ride,
      predictedWait:    entry.predicted_wait ?? entry.predicted_wait_minutes ?? entry.wait ?? null,
      queueJoinMinutes: entry.queue_join_minutes ?? null,
    };
  }
  return { rideId: entry, predictedWait: null, queueJoinMinutes: null };
}

let routeGenerating = false;

async function generateRoute(triggerBtn) {
  if (routeGenerating) return;
  routeGenerating = true;

  const btns = [document.getElementById('getRouteBtn'), document.getElementById('generateRouteBtn')];
  btns.forEach(b => { if (b) b.disabled = true; });

  const ride_counts = {};
  RIDES.forEach(r => { if (state.visible[r.id] && state.counts[r.id] > 0) ride_counts[r.id] = state.counts[r.id]; });

  const ride_locked = {};
  RIDES.forEach(r => { if (state.locked[r.id]) ride_locked[r.id] = true; });

  const closed_ride_keys = RIDES.filter(r => state.liveOpen[r.id] === false).map(r => r.id);
  const breaks = state.breaks.map(b => [b.startMin, b.endMin]);

  const time_pinned = Object.values(state.timePinned)
    .filter(p => p.targetMinutes !== null)
    .map(p => {
      const routeIdx = state.route.findIndex((stop, idx) =>
        stop.rideId === p.rideId && getInstanceIndex(state.route, idx) === p.instanceIndex
      );
      return {
        ride_key:       p.rideId,
        instance_index: p.instanceIndex,
        target_minutes: p.targetMinutes,
        route_index:    routeIdx,
      };
    });

  triggerBtn.classList.add('flash');
  setTimeout(() => triggerBtn.classList.remove('flash'), 220);

  const allCheckedClosed = Object.keys(ride_counts).length > 0 &&
    Object.keys(ride_counts).every(id => state.liveOpen[id] === false);
  if (allCheckedClosed) {
    routePlaceholderEl.textContent = 'All rides are currently closed.';
    routePlaceholderEl.style.color = 'var(--danger)';
    routePlaceholderEl.style.display = 'block';
    routeItemsEl.classList.remove('active');
    routeGenerating = false;
    btns.forEach(b => { if (b) b.disabled = false; });
    return;
  }
  routePlaceholderEl.style.color = '';
  // Always show a loading state regardless of whether a route already exists
  routePlaceholderEl.textContent = 'Generating…';
  routePlaceholderEl.style.display = 'block';
  routeItemsEl.classList.remove('active');

  try {
    const res = await fetch(`${API_BASE}/api/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ride_counts, ride_locked, closed_ride_keys, breaks,
        start_key: state.selectedStart,
        live_waits: state.liveWaits,
        time_pinned,
        max_counts: Object.fromEntries(
          RIDES
            .filter(r => state.visible[r.id] && state.counts[r.id] > 0)
            .map(r => [r.id, state.maxCounts[r.id] === Infinity ? null : state.maxCounts[r.id]])
        ),
      }),
    });

    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) ? data.error : `route request failed: ${res.status}`);
    if (!Array.isArray(data)) throw new Error('Unexpected response from route service.');

    state.route = data.map(extractRideIdAndWait);

    const oldPins = Object.values(state.timePinned);
    const newTP = {};

    function pinAt(idx, targetMinutes) {
      if (idx < 0 || idx >= state.route.length) return;
      const rid  = state.route[idx].rideId;
      const inst = getInstanceIndex(state.route, idx);
      newTP[getUniqueKey(rid, inst)] = { rideId: rid, instanceIndex: inst, targetMinutes };
    }

    oldPins.forEach(pin => {
      if (pin.targetMinutes === 0) {
        if (state.route[0]?.rideId === pin.rideId) pinAt(0, 0);
      } else if (pin.targetMinutes === 1440) {
        const lastIdx = state.route.length - 1;
        if (state.route[lastIdx]?.rideId === pin.rideId) pinAt(lastIdx, 1440);
      } else if (pin.targetMinutes !== null) {
        let bestIdx = -1, bestDist = Infinity;
        state.route.forEach((stop, idx) => {
          if (stop.rideId !== pin.rideId) return;
          const qjm = stop.queueJoinMinutes;
          const dist = qjm == null ? Infinity : Math.abs(qjm - pin.targetMinutes);
          if (dist < bestDist) { bestDist = dist; bestIdx = idx; }
        });
        if (bestIdx >= 0) pinAt(bestIdx, pin.targetMinutes);
      } else {
        const occurrences = [];
        state.route.forEach((stop, idx) => { if (stop.rideId === pin.rideId) occurrences.push(idx); });
        if (occurrences.length) {
          const idx = occurrences[Math.min(pin.instanceIndex, occurrences.length - 1)];
          pinAt(idx, null);
        }
      }
    });

    state.timePinned = newTP;

    const stillPinnedRideIds = new Set(Object.values(newTP).map(p => p.rideId));
    Object.keys(state.pinnedLocked).forEach(rideId => {
      if (!stillPinnedRideIds.has(rideId)) {
        state.locked[rideId] = false;
        delete state.pinnedLocked[rideId];
      }
    });

    if (!state.route.length) {
      routePlaceholderEl.textContent = 'Nothing fit before closing — try unchecking a few rides or starting earlier.';
    }
  } catch (err) {
    console.error(err);
    state.route = [];
    routePlaceholderEl.textContent = `Couldn't generate a route: ${err.message}`;
  } finally {
    routeGenerating = false;
    btns.forEach(b => { if (b) b.disabled = false; });
    renderRouteBar();
  }
}

$('#getRouteBtn').addEventListener('click', () => generateRoute($('#getRouteBtn')));
$('#generateRouteBtn').addEventListener('click', () => generateRoute($('#generateRouteBtn')));



// ═══════════════ LIVE STATUS POLLING ═══════════════

async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/rides`);
    if (!res.ok) return;
    const data = await res.json();
    const waits = {}, open = {};
    RIDES.forEach(r => {
      const entry = data[r.id];
      if (entry && typeof entry.waittime === 'number') {
        waits[r.id] = entry.waittime;
        open[r.id] = entry.is_open === false ? false : true;
      } else {
        waits[r.id] = null;
        open[r.id] = null; // unknown — don't treat as closed
      }
    });
    state.liveWaits = waits;
    state.liveOpen  = open;
    renderPins();
    if (showWaitBubbles) renderWaitBubbles(); // keep bubble text fresh while they're showing
    if (popupState.rideId) showPopup(popupState.rideId, [...pinLayerEl.children].find(p => p.querySelector('img')?.alt === rideById[popupState.rideId]?.name));
  } catch (err) {
    // best-effort; app still works with unknown wait times
  }
}

// ═══════════════ COLLAPSE TOGGLES ═══════════════

$('#sidebarToggle').addEventListener('click', () => sidebarEl.classList.toggle('collapsed'));

$('#topBarToggle').addEventListener('click', () => {
  topBarEl.classList.toggle('collapsed');
});

topBarEl.addEventListener('transitionend', (e) => {
  if (e.propertyName === 'grid-template-rows') updateTogglePositions();
});

function getBackButtonGap() {
  const backBtnEl = document.getElementById('backBtn');
  return parseFloat(getComputedStyle(backBtnEl).paddingBottom) || 10;
}

const MIN_MAP_HEIGHT = 64;

// Reserves the same safe-area gap below the back button as the space
// above it, by giving #bottomBar a min-height of (button height + gap)
// instead of leaving that gap as blank margin above the bar. That way
// the button -- centered via align-items on #bottomBar -- sits centered
// in the full space between the bottom of the map and the bottom of the
// screen, rather than being pushed low with a dead gap above it.
function updateBottomBarMinHeight() {
  const backBtnEl = document.getElementById('backBtn');
  const gap = getBackButtonGap();
  // Reserve the gap on BOTH sides of the button -- above it (between the
  // button and the map) and below it (between the button and the screen
  // edge) -- so centering produces a real, visible symmetric strip
  // instead of collapsing back down to just the button's own size.
  const minHeight = backBtnEl.offsetHeight + gap * 2;
  mapPaneEl.style.setProperty('--bottombar-min-h', minHeight + 'px');
  return minHeight;
}

function updateTogglePositions() {
  const sidebarToggle = document.getElementById('sidebarToggle');
  const topBarToggleEl = document.getElementById('topBarToggle');

  const toggleTop = topBarEl.offsetHeight;
  topBarToggleEl.style.top = toggleTop + 'px';


  const toggleBottom = toggleTop + topBarToggleEl.offsetHeight;

  const gap = getBackButtonGap();
  const bottomBarMinHeight = updateBottomBarMinHeight();
  const available = mapPaneEl.clientHeight - bottomBarMinHeight;
  const maxTopOffset = Math.max(0, available - gap - MIN_MAP_HEIGHT);
  const topOffset = Math.min(toggleBottom, maxTopOffset);

  mapPaneEl.style.setProperty('--map-top-offset', topOffset + 'px');


  if (typeof clampMapPan === 'function' && mapFitWidth) {
    clampMapPan();
    applyMapTransform();
  }

if (sidebarToggle) {
  // Prefer the vertical center of the map pane, but never let the
  // toggle sit inside the top bar's own space -- push it down below
  // the top bar's bottom edge instead. If the top bar (plus the
  // bottom bar's reserved space) leaves no room to fully clear it,
  // stop at the lowest point available; the z-index bump in CSS then
  // keeps the toggle visible ON TOP of the top bar instead of
  // disappearing underneath it.
  const half = sidebarToggle.offsetHeight / 2;
  const minTop = topBarEl.offsetHeight + half;
  const maxTop = mapPaneEl.clientHeight - bottomBarMinHeight - half;
  let top = Math.max(mapPaneEl.clientHeight / 2, minTop);
  top = Math.min(top, maxTop);
  sidebarToggle.style.top = top + 'px';
}
}

function updateTopBarMaxHeight() {
  const bottomBarMinHeight = updateBottomBarMinHeight();
  const topBarToggleEl = document.getElementById('topBarToggle');
  const gap = getBackButtonGap();


  const reserved = bottomBarMinHeight + topBarToggleEl.offsetHeight + gap;
  const maxH = mapPaneEl.clientHeight - reserved;
  mapPaneEl.style.setProperty('--topbar-max-h', Math.max(0, maxH) + 'px');
}

const topBarResizeObserver = new ResizeObserver(updateTogglePositions);
topBarResizeObserver.observe(topBarEl);
// ═══════════════ INIT ═══════════════

function init() {
  updateTopBarMaxHeight();
  renderStartDropdown();
  renderPresetDropdown();
  renderSidebarList();

  applyDarkMode();
  applyAdvancedMode();

  function refreshMapImageSizing() {
    computeMapFitWidth();
    refreshMapViewportRect();
    clampMapPan();
    applyMapTransform();
  }
  mapImageEl.addEventListener('load', refreshMapImageSizing);

  if (mapImageEl.complete) {
    refreshMapImageSizing();
  }

  renderPins();
  renderRouteBar();
  pollStatus();
  updateTogglePositions(); 


  if (window.matchMedia('(max-width: 760px)').matches) {
    sidebarEl.classList.add('collapsed');
  }

  window.addEventListener('resize', () => {
    if (popupState.rideId) hidePopup();
    updateTopBarMaxHeight();
    updateTogglePositions();
    computeMapFitWidth();
    refreshMapViewportRect();
    clampMapPan();
    applyMapTransform();
  });
}

init();