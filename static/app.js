/* ════════════════════════════════════════════════════════════════
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
  { id: 'hulk',           name: 'The Incredible Hulk Coaster',                 icon: 'assets/logos/hulk_logo.png',            x: 488, y: 620 },
  { id: 'stormForce',     name: 'Storm Force Accelatron',                      icon: 'assets/logos/stormForce_logo.png',      x: 469, y: 654 },
  { id: 'doctorDoom',     name: "Doctor Doom's Fearfall",                      icon: 'assets/logos/Doctor-dooms-fearfall-ride-logo-b.png', x: 411, y: 572 },
  { id: 'spiderMan',      name: 'The Amazing Adventures of Spider-Man',        icon: 'assets/logos/Amazing-adventures-spider-man-ride-logo-b.png', x: 418, y: 527 },
  { id: 'bilgeRat',       name: "Popeye & Bluto's Bilge-Rat Barges",           icon: 'assets/logos/bilge_rat.png',            x: 394, y: 380 },
  { id: 'ripsawFalls',    name: "Dudley Do-Right's Ripsaw Falls",              icon: 'assets/logos/Dudley-do-rights-ripsaw-falls-water-ride-logo-b.png', x: 276, y: 379 },
  { id: 'skullIsland',    name: 'Skull Island: Reign of Kong',                 icon: 'assets/logos/Skull_Island-_Reign_of_Kong_Logo.png', x: 271, y: 246 },
  { id: 'velociCoaster',  name: 'Jurassic World VelociCoaster',                icon: 'assets/logos/velocicoaster.png',        x: 514, y: 308 },
  { id: 'riverAdventure', name: 'Jurassic Park River Adventure',               icon: 'assets/logos/jurrasicPark.png',         x: 412, y: 217 },
  { id: 'hogwartsTrain',  name: 'Hogwarts Express',                            icon: 'assets/logos/express.png',              x: 832, y: 262 },
  { id: 'hippogriff',     name: 'Flight of the Hippogriff',                    icon: 'assets/logos/hippogriph.png',           x: 668, y: 165 },
  { id: 'hagrid',         name: "Hagrid's Magical Creatures Motorbike Adventure", icon: 'assets/logos/Hagrid27s_Magical_Creatures_Motorbike_Adventure.png', x: 742, y: 218 },
  { id: 'drSeussAirRide', name: 'High in the Sky Seuss Trolley Train Ride',    icon: 'assets/logos/seuss.png',                x: 715, y: 495 },
  { id: 'caroSeussel',    name: 'Caro-Seuss-el',                               icon: 'assets/logos/caro.png',                 x: 715, y: 495 },
  { id: 'oneFishtwoFish', name: 'One Fish, Two Fish, Red Fish, Blue Fish',     icon: 'assets/logos/blue.png',                 x: 741, y: 562 },
  { id: 'catInTheHat',    name: 'The Cat in the Hat',                          icon: 'assets/logos/cat.png',                  x: 683, y: 631 },
  { id: 'harryPotter',    name: 'Harry Potter and the Forbidden Journey',      icon: 'assets/logos/hogwarts.png',             x: 595, y: 182 },
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
  breaks: [],          // { id, label, startMin, endMin }
  selectedStart: 'entrance',
  route: [],            // [{ rideId, predictedWait }]
  liveWaits: {},         // rideId -> minutes|null
  liveOpen: {},           // rideId -> bool|null
  selectedStops: new Set(), // rideIds the user has highlighted
};

let breakIdCounter = 0;
let dragSrcIdx = null;

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
const routeItemsEl      = $('#routeItems');
const routePlaceholderEl= $('#routePlaceholder');

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
    name.textContent = r.name.replace(/\n/g, ' ');

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
      if (old === 2 && next === 1) state.locked[r.id] = state.lockBeforeBump[r.id];
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
      if (old === 1) { state.lockBeforeBump[r.id] = state.locked[r.id]; state.locked[r.id] = true; }
      renderSidebarList();
      renderPins();
    });

    spinner.append(down, count, up);

    const lockable = state.visible[r.id] && state.counts[r.id] > 0;
    if (!lockable) state.locked[r.id] = false;
    const lock = document.createElement('button');
    lock.className = 'lock-btn' + (state.locked[r.id] ? ' locked' : '') + (lockable ? '' : ' disabled');
    lock.innerHTML = state.locked[r.id]
      ? '<svg viewBox="0 0 14 14"><rect x="3" y="6" width="8" height="6" rx="1"/><path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2"/></svg>'
      : '<svg viewBox="0 0 14 14"><rect x="3" y="6" width="8" height="6" rx="1"/><path d="M4.5 6V4a2.5 2.5 0 0 1 5 0"/></svg>';
    lock.addEventListener('click', () => {
      if (!lockable) return;
      state.locked[r.id] = !state.locked[r.id];
      renderSidebarList();
    });

    row.append(cb, name, spinner, lock);
    sidebarListEl.appendChild(row);
  });
}

// ═══════════════ MAP PINS + POPUP ═══════════════

const popupState = { rideId: null };

function renderPins() {
  pinLayerEl.innerHTML = '';
  RIDES.forEach(r => {
    if (!state.visible[r.id]) return;
    const pin = document.createElement('button');
    pin.className = 'pin';
    if (state.liveOpen[r.id] === false) pin.classList.add('closed');
    pin.style.left = (r.x / MAP_NATIVE_W * 100) + '%';
    pin.style.top  = (r.y / MAP_NATIVE_H * 100) + '%';
    const img = document.createElement('img');
    img.src = r.icon;
    img.alt = r.name;
    img.onerror = () => { img.style.display = 'none'; pin.textContent = r.name.split(' ')[0]; };
    pin.appendChild(img);
    pin.addEventListener('click', e => { e.stopPropagation(); showPopup(r.id, pin); });
    pinLayerEl.appendChild(pin);
  });
}

function showPopup(rideId, anchorEl) {
  popupState.rideId = rideId;
  const r = rideById[rideId];
  const wait = state.liveWaits[rideId];
  const isOpen = state.liveOpen[rideId];
  let waitLine, waitCls = '';
  if (wait == null && isOpen !== false) { waitLine = 'Loading…'; }
  else if (isOpen === false) { waitLine = 'Ride is currently closed'; waitCls = 'closed'; }
  else { waitLine = `Wait: ${wait} min`; }

  popupEl.innerHTML = `${r.name.replace(/\n/g, '<br>')}<div class="wait-line ${waitCls}">${waitLine}</div>`;
  popupEl.classList.remove('hidden');
  positionPopup(anchorEl);
}

function positionPopup(anchorEl) {
  if (!anchorEl || popupState.rideId == null) return;
  // getBoundingClientRect() is already relative to the browser viewport,
  // accounting for every ancestor's offset AND scroll automatically — no
  // need to subtract #mapViewport's rect or add its scroll manually. The
  // old code computed coordinates relative to #mapViewport, but #popup is
  // actually a child of #app (position: relative), which is #popup's real
  // positioning ancestor. That mismatch silently shifted every popup up
  // and to the left by the sidebar width / topbar height, pushing many of
  // them off-screen or behind other elements. Using `position: fixed` on
  // .popup (see styles.css) plus the pin's own rect directly sidesteps the
  // whole ancestor-offset problem.
  const pinRect = anchorEl.getBoundingClientRect();
  popupEl.style.left = (pinRect.left + pinRect.width / 2) + 'px';
  popupEl.style.top  = pinRect.top + 'px';
}

function hidePopup() {
  popupState.rideId = null;
  popupEl.classList.add('hidden');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.pin') && !e.target.closest('.popup')) hidePopup();
});

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

  state.route.forEach((stop, i) => {
    const r = rideById[stop.rideId];
    if (!r) return;

    const wrap = document.createElement('div');
    wrap.className = 'route-stop';
    wrap.draggable = true;
    wrap.dataset.idx = i;

    // ── drag events ──────────────────────────────────
    wrap.addEventListener('dragstart', e => {
      dragSrcIdx = i;
      wrap.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });

    wrap.addEventListener('dragend', () => {
      dragSrcIdx = null;
      document.querySelectorAll('.route-stop').forEach(el => {
        el.classList.remove('dragging', 'drag-over');
      });
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
      if (dragSrcIdx === null || dragSrcIdx === i) return;

      // Reorder state.route in place
      const moved = state.route.splice(dragSrcIdx, 1)[0];
      state.route.splice(i, 0, moved);
      dragSrcIdx = null;
      renderRouteBar();
    });

    // ── card (pill + chip + remove) ──────────────────
    const card = document.createElement('div');
    card.className = 'route-stop-card';

    const pill = document.createElement('div');
    pill.className = 'route-pill' + (state.selectedStops.has(stop.rideId) ? ' highlighted' : '');

    // Click the pill to toggle highlight; suppress if it was a drag
    let pointerMoved = false;
    pill.addEventListener('pointerdown', () => { pointerMoved = false; });
    pill.addEventListener('pointermove', () => { pointerMoved = true; });
    pill.addEventListener('pointerup', () => {
      if (pointerMoved) return;
      if (state.selectedStops.has(stop.rideId)) {
        state.selectedStops.delete(stop.rideId);
      } else {
        state.selectedStops.add(stop.rideId);
      }
      renderRouteBar();
    });

    // Also highlight when the stop is dropped onto a new position
    wrap.addEventListener('drop', () => {
      state.selectedStops.add(stop.rideId);
    }, { once: true });

    const img = document.createElement('img');
    img.src = r.icon;
    img.alt = r.name;
    img.draggable = false; // let the parent <div> handle dragging
    img.onerror = () => { img.remove(); pill.innerHTML = `<span>${r.name.split(' ')[0]}</span>`; };
    pill.appendChild(img);

    const chip = document.createElement('span');
    chip.className = 'wait-chip';
    chip.textContent = stop.predictedWait == null ? '--' : `${Math.round(stop.predictedWait)}m`;

    const remove = document.createElement('button');
    remove.className = 'stop-remove';
    remove.textContent = '✕';
    remove.addEventListener('click', () => {
      state.selectedStops.delete(stop.rideId);
      state.route = state.route.filter(s => s.rideId !== stop.rideId);
      state.visible[stop.rideId] = false;
      state.locked[stop.rideId] = false;
      state.counts[stop.rideId] = 0;
      renderRouteBar();
      renderSidebarList();
      renderPins();
    });

    card.append(pill, chip, remove);
    wrap.appendChild(card);

    if (i < state.route.length - 1) {
      const arrow = document.createElement('span');
      arrow.className = 'route-arrow';
      arrow.textContent = '→';
      wrap.appendChild(arrow);
    }
    routeItemsEl.appendChild(wrap);
  });
}

// ═══════════════ ROUTE GENERATION ═══════════════

/**
 * Normalizes one entry of the /api/route response into { rideId, predictedWait }.
 *
 * compute_and_print_route() returns a list of (ride_key, predicted_wait)
 * TUPLES. Flask's jsonify() serializes each tuple as a plain JSON ARRAY,
 * e.g. ["hulk", 45.2] — not an object with a `.ride_id` property. The
 * previous version of this function only handled the object shape
 * (`entry.ride_id`), so `rideId` came back `undefined` for every single
 * stop, renderRouteBar() silently skipped all of them (rideById[undefined]
 * is falsy), and the top bar rendered as blank even though a route had
 * been computed successfully. This mirrors frontEnd.py's
 * `_extract_ride_id_and_predicted_wait`, which already handled all three
 * shapes the backend might send (string / tuple-array / dict) — app.js
 * just never got the same treatment.
 */
function extractRideIdAndWait(entry) {
  if (Array.isArray(entry)) {
    return {
      rideId: entry.length > 0 ? entry[0] : undefined,
      predictedWait: entry.length > 1 ? entry[1] : null,
    };
  }
  if (entry && typeof entry === 'object') {
    return {
      rideId: entry.ride_id ?? entry.id ?? entry.ride,
      predictedWait: entry.predicted_wait ?? entry.predicted_wait_minutes ?? entry.wait ?? null,
    };
  }
  // plain ride_id string
  return { rideId: entry, predictedWait: null };
}

async function generateRoute(triggerBtn) {
  const ride_counts = {};
  RIDES.forEach(r => { if (state.visible[r.id] && state.counts[r.id] > 0) ride_counts[r.id] = state.counts[r.id]; });

  // IMPORTANT: this must be an OBJECT ({ rideId: true, ... }), not an
  // array. routeOptimizer.py does `ride_locked.get(key)` on this value --
  // sending an array made every route request throw
  // AttributeError: 'list' object has no attribute 'get', which is why
  // "Generate Route" used to hang on "Generating…" forever (the backend
  // call was failing every time a ride ended up locked, which happens
  // automatically once its count is bumped above 1).
  const ride_locked = {};
  RIDES.forEach(r => { if (state.locked[r.id]) ride_locked[r.id] = true; });

  const closed_ride_keys = RIDES.filter(r => state.liveOpen[r.id] === false).map(r => r.id);
  const breaks = state.breaks.map(b => [b.startMin, b.endMin]);

  triggerBtn.classList.add('flash');
  routePlaceholderEl.textContent = 'Generating…';
  routePlaceholderEl.style.display = state.route.length ? 'none' : 'block';
  setTimeout(() => triggerBtn.classList.remove('flash'), 220);

  try {
    const res = await fetch(`${API_BASE}/api/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ride_counts, ride_locked, closed_ride_keys, breaks,
        start_key: state.selectedStart,
        live_waits: state.liveWaits,
      }),
    });

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const message = (data && data.error) ? data.error : `route request failed: ${res.status}`;
      throw new Error(message);
    }
    if (!Array.isArray(data)) {
      throw new Error('Unexpected response from route service.');
    }

    state.route = data.map(extractRideIdAndWait);

    if (!state.route.length) {
      routePlaceholderEl.textContent = 'Nothing fit before closing — try uncheck a few rides or start earlier.';
    }
  } catch (err) {
    console.error(err);
    state.route = [];
    routePlaceholderEl.textContent = `Couldn't generate a route: ${err.message}`;
  } finally {
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
    // data shape: { "<rideId>": { waittime, is_open }, ... } — a ride
    // missing from this dict is "unknown" (the poller hasn't reported it
    // yet), not "closed".
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
    if (popupState.rideId) showPopup(popupState.rideId, [...pinLayerEl.children].find(p => p.querySelector('img')?.alt === rideById[popupState.rideId]?.name));
  } catch (err) {
    // best-effort; app still works with unknown wait times
  }
}

// ═══════════════ COLLAPSE TOGGLES ═══════════════

$('#sidebarToggle').addEventListener('click', () => sidebarEl.classList.toggle('collapsed'));
$('#topBarToggle').addEventListener('click', () => topBarEl.classList.toggle('collapsed'));

// ═══════════════ INIT ═══════════════

function init() {
  renderStartDropdown();
  renderPresetDropdown();
  renderSidebarList();
  renderPins();
  renderRouteBar();
  pollStatus();
  setInterval(pollStatus, STATUS_POLL_MS);
  window.addEventListener('resize', () => { if (popupState.rideId) hidePopup(); });
}

init();