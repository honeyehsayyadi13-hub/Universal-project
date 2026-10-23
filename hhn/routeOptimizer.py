"""
route_optimizer.py (the main algorithm)

Computes the best order to visit a selected set of rides using:
  - Historical wait-time data (Supabase 'ride_waits' table) to predict
    future wait times, based on time-of-day / day-of-week patterns.
  - Static walk-time data (Supabase 'walk_times' table) to account for
    travel time between rides.
  - Ride-duration data (Supabase 'ride_duration' table) to account for
    how long you're actually on the ride once you board.

Rules this version enforces:
  1. Currently-closed rides are dropped completely, no matter what the
     sidebar says about them (checked, locked, counted-up -- doesn't
     matter, closed means closed).
  2. A LOCKED ride is force-included at its best possible slot, even if
     that isn't the globally "optimal" pick. A ride checked to go more
     than once (count > 1) has those extra visits force-attempted too.
     If there isn't enough daylight to fit everything that's forced,
     the counted-up EXTRA visits are sacrificed first; only after every
     extra is gone do LOCKED base visits start getting dropped.
  3. Ride duration (time actually spent on the ride) is added on top of
     wait time when simulating the day.
  4. Breaks (guest-entered time windows) block out the schedule -- you
     can't walk into a queue during a break; the plan waits until the
     break ends, then adds a short post-break buffer before any walking
     to the next ride starts (see POST_BREAK_BUFFER_MIN below).
  5. Wait-time predictions are anchored to today's live reading (see
     `Data.ride_waits` / the `live_waits` argument below) and decay
     toward the plain historical time-of-day curve the further out the
     prediction reaches.
  6. Time-pinned rides (from drag-to-slot or click-to-lock) are forced
     to specific times of day or positions (first/last), as long as
     doing so doesn't cause other forced rides to drop before closing.
     A ride pinned first/last is a HARD constraint and is honored
     unconditionally, even overriding rule 1's ordinary elimination if
     needed -- see _reorder_for_time_pins.
  7. The plan doesn't stop the moment every checked/locked/counted ride
     has been visited once -- it keeps cycling back through every
     selected ride, for as long as there's still daylight left, so the
     schedule runs all the way to park close instead of stopping early.

Call `compute_and_print_route(...)` from a button press on the
frontend. Results are returned as a list of
(ride_key, predicted_wait, queue_join_minutes) tuples for the rides that
actually fit before closing.

Returns `None` if the route couldn't be computed at all (bad/missing
selection, Supabase unreachable, etc.) -- callers should treat `None`
as "no change", as opposed to `[]` which means "computed successfully,
but nothing fit."

Install:
    pip install supabase

Environment variables required:
    SUPABASE_URL
    SUPABASE_KEY
"""

import os
import math
import itertools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import threading
import time

# Per-request earliest queue-join times for force-opened rides ({db_id: datetime}).
_ctx = threading.local()

from supabase import create_client, Client


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

_supabase_client = None


def _get_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "Missing SUPABASE_URL / SUPABASE_KEY environment variables. "
                "Set them before calling the optimizer, e.g.:\n"
                '  export SUPABASE_URL="https://xxxx.supabase.co"\n'
                '  export SUPABASE_KEY="your-anon-or-service-key"'
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ── tunables ──────────────────────────────────────────────────────────
TIME_KERNEL_BANDWIDTH_MIN = 45   # width of the time-of-day matching window
SAME_DAY_WEIGHT = 1.0            # weight boost for samples on the same weekday
WEEKEND_GROUP_WEIGHT = 0.6       # weight when both days are weekend (or both weekday)
DIFF_DAY_WEIGHT = 0.35           # weight for a weekday-vs-weekend mismatch
WEEKEND_DAYS = {4, 5}            # Saturday, Sunday (Monday == 0)
RECENCY_HALF_LIFE_DAYS = 45      # historical samples lose half their weight every 45 days
ANCHOR_MODE = "ratio"            # "ratio" or "add" -- how the live reading shifts the historical curve
ANCHOR_DECAY_HOURS = 3.0         # how many hours out we keep trusting today's live reading
MIN_MEANINGFUL_BASELINE_MIN = 3.0 # min historical baseline for ratio-based anchoring
ANCHOR_RATIO_MIN = 0.15          # min ratio clamp for live anchor
ANCHOR_RATIO_MAX = 4.0           # max ratio clamp for live anchor
DEFAULT_WAIT_MIN = 30            # fallback if a ride has zero usable history
DEFAULT_WALK_MIN = 10            # fallback if a ride pair has no walk_times row
DEFAULT_RIDE_DURATION_MIN = 3    # fallback if a ride has no ride_duration row
BRUTE_FORCE_LIMIT = 7            # exact solve (permutations) up to this many stops
MAX_2OPT_PASSES = 3              # cap full 2-opt sweeps for larger stop lists
DEFAULT_PARK_CLOSE_HOUR = 2     # 8:00 PM -- fallback used only when live park hours can't be fetched
DEFAULT_PARK_CLOSE_MINUTE = 0
HISTORY_WINDOW_DAYS = 150        # only learn from the most recent ~5 months of readings
HISTORY_PAGE_SIZE = 1000         # Supabase returns at most 1000 rows per request
HISTORY_REFRESH_SEC = 600        # re-check Supabase for new readings at most every 10 min
MIN_HISTORY_WEIGHT = 10.0        # need ~this many effective samples near the target time, else "no history"
CROWD_TAU_OWN_HOURS = 3.0        # a ride's own live ratio fades toward the park-wide ratio over this long
CROWD_TAU_PARK_HOURS = 16.0      # the park-wide ratio fades toward "normal" (1.0) over this long
CROWD_RATIO_MIN = 0.3
CROWD_RATIO_MAX = 4.0
CROWD_MIN_RIDES = 5              # need at least this many open rides with live data to trust the park factor
USE_PARK_FACTOR = False          # tested: no clear gain on the strict hit-rate metric
ANCHOR_DECAY_HOURS_RATIO = 12.0  # how long a ride's own live ratio lasts (tested: 12h beat 3h)
HISTORY_BIN_MIN = 5              # history is bucketed into 5-minute time-of-day bins
ENTRANCE_DB_ID = 0               # matches the "id" of the entrance row in `rides`
FORCE_OPEN_BUFFER_MIN = 30       # a force-opened ride can't be queued sooner than this from now
POST_BREAK_BUFFER_MIN = 2        # time to get moving again after a break ends
PARK_TIMEZONE = ZoneInfo("America/New_York")  # Universal Orlando is Eastern time
MAX_DRAG_DRIFT_MIN = 30          # a dragged-and-dropped ride must land within this many
                                  # minutes of the queue-join time of whatever ride it
                                  # displaced, whenever a slot like that exists at all

# ── ride importance ranking ──────────────────────────────────────────
OPERATING_DAY_START_HOUR = 6     # HHN runs past midnight: the "operating day" is 6 AM -> 6 AM


def _op_date(dt):
    """The operating date a timestamp belongs to (1 AM Saturday still counts as Friday night)."""
    return (dt - timedelta(hours=OPERATING_DAY_START_HOUR)).date()


def _priority_fill_weights(ride_priority_order, checked_keys):
    """
    Turns a full ride_key ranking (most -> least important) into a
    {ride_key: weight} map for _fill_until_close's round-robin fill.
    """
    order = list(ride_priority_order or [])
    rank = {key: i for i, key in enumerate(order)}
    fallback_rank = len(order)
    weights = {}
    for key in checked_keys:
        r = rank.get(key, fallback_rank)
        weights[key] = float(fallback_rank - r) + 1.0
    return weights


# ── data loading ─────────────────────────────────────────────────────
_static_cache = {}
STATIC_TTL_SEC = 600      # walk times / ride list / durations are re-read every 10 min
last_timing = {}          # filled in by each route request (see /api/debug-last)


def _cached(name, fn):
    hit = _static_cache.get(name)
    if hit and time.time() - hit[0] < STATIC_TTL_SEC:
        return hit[1]
    val = fn()
    _static_cache[name] = (time.time(), val)
    return val


def _load_ride_id_map():
    return _cached("ride_map", _load_ride_id_map_uncached)


def _load_ride_id_map_uncached():
    """Return (key_to_id, id_to_key) using the short keys in `rides.name`."""
    resp = _get_client().table("rides").select("id, name").execute()
    key_to_id, id_to_key = {}, {}
    for row in resp.data:
        key_to_id[row["name"]] = row["id"]
        id_to_key[row["id"]] = row["name"]
    return key_to_id, id_to_key


def _parse_ts(ts):
    """Parse a Supabase timestamp into a NAIVE datetime in the park's local timezone."""
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(PARK_TIMEZONE).replace(tzinfo=None)
    return dt


_history_cache = {}        # db_id -> [(naive park-time timestamp, waittime), ...]
_history_last_raw = {}     # db_id -> raw timestamp string of the newest row fetched
_history_fetched_at = {}   # db_id -> time.time() of the last refresh
_history_lock = threading.Lock()


def _fetch_ride_rows(db_id, after_raw=None):
    """Page through ride_waits for one ride (Supabase caps each response at 1000 rows).
    First call pulls the last HISTORY_WINDOW_DAYS days; later calls pull only newer rows."""
    client = _get_client()
    cutoff = (datetime.now(PARK_TIMEZONE) - timedelta(days=HISTORY_WINDOW_DAYS)).isoformat()
    out, start = [], 0
    while True:
        q = (
            client.table("ride_waits")
            .select("ride_id, timestamp, waittime, issue_with_ride")
            .eq("ride_id", db_id)
        )
        q = q.gt("timestamp", after_raw) if after_raw else q.gte("timestamp", cutoff)
        resp = q.order("timestamp").range(start, start + HISTORY_PAGE_SIZE - 1).execute()
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < HISTORY_PAGE_SIZE:
            break
        start += HISTORY_PAGE_SIZE
    return out


def _load_wait_history(db_ids):
    """Return {db_id: [(timestamp, waittime), ...]} using valid, non-issue rows.
    History is kept in memory and only topped up with new rows every
    HISTORY_REFRESH_SEC seconds, so only the first request after a restart is slow."""
    history = defaultdict(list)
    if not db_ids:
        return history
    now_s = time.time()
    with _history_lock:
        for db_id in db_ids:
            age = now_s - _history_fetched_at.get(db_id, 0.0)
            if db_id not in _history_cache or age >= HISTORY_REFRESH_SEC:
                try:
                    rows = _fetch_ride_rows(db_id, _history_last_raw.get(db_id))
                except Exception:
                    if db_id not in _history_cache:
                        raise
                    rows = []
                bucket = _history_cache.setdefault(db_id, [])
                for row in rows:
                    _history_last_raw[db_id] = row["timestamp"]
                    if row.get("issue_with_ride") or row.get("waittime") is None:
                        continue
                    bucket.append((_parse_ts(row["timestamp"]), row["waittime"]))
                _history_fetched_at[db_id] = now_s
            history[db_id] = list(_history_cache[db_id])
    return history

def warm_history_cache():
    """Preload wait history for every ride so the first real request is fast."""
    key_to_id, _ = _load_ride_id_map()
    _entrance = key_to_id.get("Entrance", ENTRANCE_DB_ID)
    _load_wait_history([i for i in key_to_id.values() if i != _entrance])


def _load_walk_times():
    return _cached("walk", _load_walk_times_uncached)


def _load_walk_times_uncached():
    """Return {(start_db_id, end_db_id): minutes}."""
    resp = (
        _get_client()
        .table("walk_times")
        .select("start_ride_ID, end_ride_ID, walk_time")
        .execute()
    )
    walk = {}
    for row in resp.data:
        wt = row["walk_time"]
        if wt is None:
            continue
        walk[(row["start_ride_ID"], row["end_ride_ID"])] = wt
    return walk


def _load_ride_durations():
    return _cached("durations", _load_ride_durations_uncached)


def _load_ride_durations_uncached():
    """Return {db_id: duration_minutes} from the `ride_duration` table."""
    resp = _get_client().table("ride_duration").select("id, duration").execute()
    return {row["id"]: row["duration"] for row in resp.data}


def _walk_time(walk_map, a_db_id, b_db_id):
    if a_db_id == b_db_id:
        return 0
    if (a_db_id, b_db_id) in walk_map:
        return walk_map[(a_db_id, b_db_id)]
    if (b_db_id, a_db_id) in walk_map:
        return walk_map[(b_db_id, a_db_id)]
    return DEFAULT_WALK_MIN


# ── prediction ───────────────────────────────────────────────────────
_NBINS = 1440 // HISTORY_BIN_MIN


def _get_bins(history_for_ride, target_time):
    """Bucket a ride's samples into time-of-day bins, with the weekday and recency
    weights (which are the same for every target time on a given date) already applied.
    Cached per request in _ctx.bins."""
    cache = getattr(_ctx, "bins", None)
    if cache is None:
        cache = _ctx.bins = {}
    key = (id(history_for_ride), len(history_for_ride), _op_date(target_time))
    hit = cache.get(key)
    if hit is not None:
        return hit[0], hit[1]

    target_op_date = _op_date(target_time)
    ref_time = datetime.combine(target_op_date, datetime.min.time()).replace(hour=12)
    target_weekday = target_op_date.weekday()
    target_is_weekend = target_weekday in WEEKEND_DAYS

    bw = [0.0] * _NBINS
    bws = [0.0] * _NBINS
    for ts, wait in history_for_ride:
        ts_wd = _op_date(ts).weekday()
        if ts_wd == target_weekday:
            day_weight = SAME_DAY_WEIGHT
        elif (ts_wd in WEEKEND_DAYS) == target_is_weekend:
            day_weight = WEEKEND_GROUP_WEIGHT
        else:
            day_weight = DIFF_DAY_WEIGHT
        age_days = max(0.0, (ref_time - ts).total_seconds() / 86400.0)
        w = day_weight * 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
        b = ((ts.hour * 60 + ts.minute) // HISTORY_BIN_MIN) % _NBINS
        bw[b] += w
        bws[b] += w * wait

    # keep a reference to the list so id() can't be reused within this request
    cache[key] = (bw, bws, history_for_ride)
    return bw, bws


def _historical_wait_curve(history_for_ride, target_time):
    """
    Kernel-weighted historical average wait at this time-of-day.
    Returns None if there's no history at all to work from.
    """
    if not history_for_ride:
        return None

    bw, bws = _get_bins(history_for_ride, target_time)
    target_minutes = target_time.hour * 60 + target_time.minute
    center_bin = target_minutes // HISTORY_BIN_MIN
    reach = int(4 * TIME_KERNEL_BANDWIDTH_MIN // HISTORY_BIN_MIN) + 1

    num = den = 0.0
    for off in range(-reach, reach + 1):
        b = (center_bin + off) % _NBINS
        if bw[b] <= 0:
            continue
        bin_center = b * HISTORY_BIN_MIN + HISTORY_BIN_MIN / 2.0
        raw = abs(bin_center - target_minutes)
        delta = min(raw, 1440 - raw)
        k = math.exp(-(delta ** 2) / (2 * TIME_KERNEL_BANDWIDTH_MIN ** 2))
        num += k * bws[b]
        den += k * bw[b]

    if den < MIN_HISTORY_WEIGHT:
        return None

    return num / den


def _predict_wait(history_for_ride, target_time, current_wait=None, now=None, historical_now=None, park_ratio=None):
    """
    Predicts the wait at `target_time`, anchored to a live reading when
    available and decaying toward the historical curve further out.
    """
    historical_target = _historical_wait_curve(history_for_ride, target_time)

    if current_wait is None or now is None:
        return historical_target if historical_target is not None else DEFAULT_WAIT_MIN

    if historical_target is None:
        return max(0.0, float(current_wait))

    if historical_now is None:
        historical_now = _historical_wait_curve(history_for_ride, now)
    if historical_now is None:
        return max(0.0, float(current_wait))

    hours_ahead = max(0.0, (target_time - now).total_seconds() / 3600.0)

    # Park-wide crowd factor: the ride's own live ratio fades toward the park-wide
    # ratio, and the park-wide ratio fades slowly toward 1.0 (normal).
    if USE_PARK_FACTOR and park_ratio is not None and historical_now > MIN_MEANINGFUL_BASELINE_MIN:
        own = max(CROWD_RATIO_MIN, min(CROWD_RATIO_MAX, current_wait / historical_now))
        r = park_ratio + (own - park_ratio) * math.exp(-hours_ahead / CROWD_TAU_OWN_HOURS)
        r = 1.0 + (r - 1.0) * math.exp(-hours_ahead / CROWD_TAU_PARK_HOURS)
        return max(0.0, historical_target * r)
    _tau = ANCHOR_DECAY_HOURS_RATIO if historical_now > MIN_MEANINGFUL_BASELINE_MIN else ANCHOR_DECAY_HOURS
    anchor_weight = math.exp(-hours_ahead / _tau)

    if ANCHOR_MODE == "ratio" and historical_now > MIN_MEANINGFUL_BASELINE_MIN:
        ratio = current_wait / historical_now
        ratio = max(ANCHOR_RATIO_MIN, min(ANCHOR_RATIO_MAX, ratio))
        anchor_adjusted = historical_target * ratio
    else:
        anchor_adjusted = max(0.0, historical_target + (current_wait - historical_now))

    predicted = anchor_weight * anchor_adjusted + (1 - anchor_weight) * historical_target

    return max(0.0, predicted)


# ── breaks ──────────────────────────────────────────────────────────
def _resolve_break_windows(breaks, base_date):
    """`breaks` is a list of (start_total_minutes, end_total_minutes) pairs.
    Returns a list of (start_dt, end_dt) datetimes anchored to `base_date`."""
    windows = []
    midnight = datetime.combine(base_date, datetime.min.time())
    for start_min, end_min in breaks or []:
        windows.append((midnight + timedelta(minutes=start_min), midnight + timedelta(minutes=end_min)))
    return windows


def _apply_breaks(clock, break_windows):
    """Push `clock` forward past any break window it currently falls inside.
    If the clock was moved by any break, a one-time POST_BREAK_BUFFER_MIN
    buffer is added on top before this function returns."""
    moved_by_break = False
    changed = True
    while changed:
        changed = False
        for b_start, b_end in break_windows:
            if b_start <= clock < b_end:
                clock = b_end
                changed = True
                moved_by_break = True
    if moved_by_break:
        clock += timedelta(minutes=POST_BREAK_BUFFER_MIN)
    return clock


# ── route planning engine ────────────────────────────────────────────
# Replaces the old greedy pipeline (forced -> optional -> fill -> pins).
# Everything is now decided in ONE search, so pins / locks / caps / breaks /
# the log are all constraints of the same optimisation instead of patches
# applied after the fact.
import copy
from collections import Counter

ALLOW_STRATEGIC_DELAY = True     # may wait a few minutes before queuing if the predicted wait drops by more
DELAY_STEP_MIN = 5
DELAY_MAX_MIN = 45
DELAY_MIN_GAIN_MIN = 5.0         # only delay when it saves at least this many minutes
BREAKS_BLOCK_WHOLE_RIDE = True   # True: walk + queue + ride must all fit between breaks
BEAM_WIDTH = 300                 # how many partial plans survive each step of the search
BEAM_PER_LEVEL = 30              # extra survivors guaranteed for every "required rides done" level
POLISH_MAX_PASSES = 3            # local-improvement sweeps after the search
FIRST_VISIT_SCALE = 10.0         # a ride you haven't done yet today is worth this many times more than a repeat
REPEAT_DECAY = 0.5               # each repeat of the same ride is worth this much of the previous one
BACK_TO_BACK_FACTOR = 0.4        # value multiplier when a REQUIRED extra visit has to follow the same ride
LOCKED_TIER_VALUE = 1_000_000_000.0  # a locked ride's visit outranks everything else
LOCKED_PRIORITY_SCALE = 1_000_000.0  # ...and if some locked rides must go, the lowest priority goes first
EXTRA_TIER_VALUE = 1_000.0           # counted-up extra visits (all dropped before any locked visit)
EXTRA_PRIORITY_SCALE = 10.0
PIN_WINDOW_STEPS_MIN = (MAX_DRAG_DRIFT_MIN, 60, 120, 240, 480, 1440)
UNLIMITED_VISITS = 99
MAX_ROUTE_STOPS = 80


class _Planner:
    """Time bookkeeping. All clocks are float minutes since midnight (park time)."""

    def __init__(self, histories, walk_map, durations, start_time, closing_min, break_windows,
                 start_db_id, current_waits, historical_now_by_id, earliest_min, park_ratio):
        self.histories = histories
        self.walk_map = walk_map
        self.durations = durations
        self.start_time = start_time
        self.day0 = datetime.combine(_op_date(start_time), datetime.min.time())
        self.s0 = (start_time - self.day0).total_seconds() / 60.0
        self.closing = closing_min
        self.breaks = sorted(break_windows)
        self.start_db_id = start_db_id
        self.current_waits = current_waits
        self.historical_now_by_id = historical_now_by_id
        self.earliest = earliest_min
        self.park_ratio = park_ratio
        self._raw_wait = {}
        self._eff_wait = {}
        self._walk = {}

    def walk(self, a, b):
        key = (a, b)
        v = self._walk.get(key)
        if v is None:
            v = _walk_time(self.walk_map, a, b)
            self._walk[key] = v
        return v

    def _raw(self, db_id, minute):
        key = (db_id, minute)
        w = self._raw_wait.get(key)
        if w is None:
            w = _predict_wait(
                self.histories.get(db_id, []),
                self.day0 + timedelta(minutes=minute),
                current_wait=self.current_waits.get(db_id),
                now=self.start_time,
                historical_now=self.historical_now_by_id.get(db_id),
                park_ratio=self.park_ratio,
            )
            self._raw_wait[key] = w
        return w

    def effective_wait(self, db_id, join):
        """Returns (delay_minutes, wait_minutes): the best way to join the queue
        at or shortly after `join`. delay > 0 only if waiting a bit first saves time."""
        m = int(round(join))
        key = (db_id, m)
        hit = self._eff_wait.get(key)
        if hit is None:
            base = self._raw(db_id, m)
            best = (0, base)
            if ALLOW_STRATEGIC_DELAY and base >= DELAY_MIN_GAIN_MIN:
                best_total = base
                d = DELAY_STEP_MIN
                while d <= DELAY_MAX_MIN and m + d <= self.closing:
                    w = self._raw(db_id, m + d)
                    if d + w < best_total:
                        best_total = d + w
                        best = (d, w)
                    d += DELAY_STEP_MIN
                if base - best_total < DELAY_MIN_GAIN_MIN:
                    best = (0, base)
            hit = best
            self._eff_wait[key] = hit
        return hit

    def _after_breaks(self, clock):
        while True:
            end = None
            for b0, b1 in self.breaks:
                if b0 <= clock < b1:
                    end = b1
                    break
            if end is None:
                return clock
            clock = end + POST_BREAK_BUFFER_MIN

    def activity(self, clock, prev_id, db_id):
        """Everything about visiting `db_id` after finishing the previous stop at `clock`.
        Returns (start, join, wait, ride_duration, end, walk)."""
        dur = self.durations.get(db_id, DEFAULT_RIDE_DURATION_MIN)
        walk = self.walk(prev_id, db_id) if prev_id is not None else 0
        earliest = self.earliest.get(db_id)
        start = self._after_breaks(clock) if self.breaks else clock
        for _ in range(len(self.breaks) + 3):
            join = start + walk
            if earliest is not None and join < earliest:
                join = earliest
            delay, wait = self.effective_wait(db_id, join)
            join += delay
            end = join + wait + dur
            if not self.breaks:
                break
            span_end = end if BREAKS_BLOCK_WHOLE_RIDE else join
            hit = None
            for b0, b1 in self.breaks:
                if b0 < span_end and b1 > start:
                    hit = b1
                    break
            if hit is None:
                break
            start = hit + POST_BREAK_BUFFER_MIN
        return start, join, wait, dur, end, walk


class _Problem:
    """What the guest asked for, translated into numbers the search can use."""

    def val(self, i, c):
        k = self.done[i] + c
        if k == 0:
            return self.w[i] * FIRST_VISIT_SCALE
        return self.w[i] * (REPEAT_DECAY ** k)

    def tier_add(self, i, c):
        if c < self.base[i]:
            return LOCKED_TIER_VALUE + self.w[i] * LOCKED_PRIORITY_SCALE
        if c < self.quota[i]:
            return EXTRA_TIER_VALUE + self.w[i] * EXTRA_PRIORITY_SCALE
        return 0.0

    def repeat_factor(self, i, c, last, n):
        """Riding the same ride twice in a row is only allowed when the guest asked
        for that many visits (or there is nothing else to ride); otherwise never."""
        if i != last or n <= 1:
            return 1.0
        return BACK_TO_BACK_FACTOR if c < self.quota[i] else 0.1


def _make_problem(checked, key_to_id, ride_locked, completed_counts, max_counts,
                  time_pinned, ride_priority_order):
    first_key = last_key = None
    window_pins = []
    for pin in time_pinned or []:
        key = pin.get("ride_key")
        t = pin.get("target_minutes")
        if not key or key not in checked or key not in key_to_id or t is None:
            continue
        try:
            t = float(t)
        except (TypeError, ValueError):
            continue
        if t == 0:
            if first_key is None:
                first_key = key
        elif t == 1440:
            if last_key is None:
                last_key = key
        else:
            window_pins.append((key, t))

    pin_counts = Counter([k for k in (first_key, last_key) if k] + [k for k, _ in window_pins])

    rows = []
    for key, count in checked.items():
        done = int(completed_counts.get(key, 0) or 0)
        remaining = int(count) - done
        pins_n = pin_counts.get(key, 0)

        cap_total = (max_counts or {}).get(key)
        cap = UNLIMITED_VISITS if cap_total is None else max(0, int(cap_total) - done)
        cap = max(cap, pins_n)                      # a pin always earns its visit
        if cap <= 0:
            continue

        locked = bool(ride_locked.get(key)) or pins_n > 0
        if locked:
            req = max(remaining, pins_n, 0)
        else:
            req = max(0, remaining - 1)             # unlocked: first visit optional, extras forced
        req = min(req, cap)
        base = 1 if (locked and req >= 1) else 0
        rows.append((key, done, cap, base, req - base))

    if not rows:
        return None

    valid = {r[0] for r in rows}
    order = [k for k in (ride_priority_order or []) if k in valid]
    order += [r[0] for r in rows if r[0] not in set(order)]
    n = len(rows)
    weight = {k: 1.0 + (n - idx) / n for idx, k in enumerate(order)}

    p = _Problem()
    p.n = n
    p.keys = [r[0] for r in rows]
    p.ids = [key_to_id[k] for k in p.keys]
    p.done = [r[1] for r in rows]
    p.cap = [r[2] for r in rows]
    p.base = [r[3] for r in rows]
    p.extra = [r[4] for r in rows]
    p.quota = [b + e for b, e in zip(p.base, p.extra)]
    p.w = [weight[k] for k in p.keys]
    idx = {k: i for i, k in enumerate(p.keys)}
    p.first_i = idx.get(first_key) if first_key else None
    p.last_i = idx.get(last_key) if last_key else None
    p.window_targets = [(idx[k], t) for k, t in window_pins if k in idx]
    p.lam = 0.04
    return p


def _estimate_lambda(prob, planner):
    """Rough 'value per minute' so the search can compare partial plans that
    have spent different amounts of time."""
    walks = [v for v in planner.walk_map.values() if v is not None]
    avg_walk = sum(walks) / len(walks) if walks else DEFAULT_WALK_MIN
    costs = []
    for db_id in prob.ids:
        _, w = planner.effective_wait(db_id, planner.s0)
        costs.append(avg_walk + w + planner.durations.get(db_id, DEFAULT_RIDE_DURATION_MIN))
    avg_cost = max(5.0, sum(costs) / len(costs))
    return FIRST_VISIT_SCALE * (sum(prob.w) / len(prob.w)) / avg_cost


class _State:
    __slots__ = ("clock", "last", "counts", "value", "tier", "req", "mask", "parent", "ride", "act")

    def __init__(self, clock, last, counts, value, tier, req, mask, parent, ride, act):
        self.clock = clock
        self.last = last
        self.counts = counts
        self.value = value
        self.tier = tier
        self.req = req
        self.mask = mask
        self.parent = parent
        self.ride = ride
        self.act = act


def _match_window(windows, mask, i, join):
    best, best_hi = -1, None
    for pid, (wi, lo, hi) in enumerate(windows):
        if wi == i and not (mask >> pid) & 1 and lo <= join <= hi:
            if best_hi is None or hi < best_hi:
                best, best_hi = pid, hi
    return best


def _sequence_from(state):
    out = []
    while state is not None and state.parent is not None:
        out.append(state.ride)
        state = state.parent
    out.reverse()
    return out


def _select(cands, lam, s0):
    cands.sort(key=lambda s: s.value - lam * (s.clock - s0), reverse=True)
    kept = cands[:BEAM_WIDTH]
    if len(cands) > BEAM_WIDTH:
        per_level = defaultdict(int)
        for s in kept:
            per_level[s.req] += 1
        for s in cands[BEAM_WIDTH:]:
            if per_level[s.req] < BEAM_PER_LEVEL:
                kept.append(s)
                per_level[s.req] += 1
    return kept


def _beam_search(prob, planner, windows):
    """Builds plans one stop at a time, keeping the most promising partial plans.
    Partial plans that reach the same set of visits (same ride last) are merged,
    keeping the faster one. Returns (key, state, last_pinned_ride_or_None) or None."""
    n = prob.n
    ids = prob.ids
    closing = planner.closing
    s0 = planner.s0
    lam = prob.lam
    full_mask = (1 << len(windows)) - 1
    bcap = list(prob.cap)
    if prob.last_i is not None:
        bcap[prob.last_i] -= 1          # one visit is reserved for the very end
    best = [None]

    def consider(st):
        if st.mask != full_mask:
            return
        if prob.first_i is not None and st.parent is None:
            return
        value, tier, end, final = st.value, st.tier, st.clock, None
        if prob.last_i is not None:
            L = prob.last_i
            prev = ids[st.last] if st.last >= 0 else planner.start_db_id
            act = planner.activity(st.clock, prev, ids[L])
            if act[1] > closing:
                return
            c = st.counts[L]
            value += prob.val(L, c) * prob.repeat_factor(L, c, st.last, n)
            tier += prob.tier_add(L, c)
            end = act[4]
            final = L
        key = (round(tier, 1), round(value, 4), -round(end, 3))
        if best[0] is None or key > best[0][0]:
            best[0] = (key, st, final)

    root = _State(s0, -1, (0,) * n, 0.0, 0.0, 0, 0, None, -1, None)
    layer = [root]
    consider(root)

    for _ in range(MAX_ROUTE_STOPS):
        nxt = {}
        for st in layer:
            prev = ids[st.last] if st.last >= 0 else planner.start_db_id
            counts = st.counts
            for i in range(n):
                c = counts[i]
                if c >= bcap[i]:
                    continue
                if st.parent is None and prob.first_i is not None and i != prob.first_i:
                    continue
                act = planner.activity(st.clock, prev, ids[i])
                join = act[1]
                if join > closing:
                    continue
                end = act[4]
                mask = st.mask
                if windows:
                    pid = _match_window(windows, mask, i, join)
                    if pid >= 0:
                        mask |= 1 << pid
                    if mask != full_mask:
                        ok = True
                        for pj, (wi, lo, hi) in enumerate(windows):
                            if (mask >> pj) & 1:
                                continue
                            if planner.activity(end, ids[i], ids[wi])[1] > hi:
                                ok = False
                                break
                        if not ok:
                            continue
                rf = prob.repeat_factor(i, c, st.last, n)
                if rf <= 0.0:
                    continue
                v = prob.val(i, c) * rf
                new_counts = counts[:i] + (c + 1,) + counts[i + 1:]
                key = (new_counts, i, mask)
                old = nxt.get(key)
                if old is not None and (old.clock < end - 1e-9 or
                                        (abs(old.clock - end) <= 1e-9 and old.value >= st.value + v)):
                    continue
                nxt[key] = _State(end, i, new_counts, st.value + v, st.tier + prob.tier_add(i, c),
                                  st.req + (1 if c < prob.quota[i] else 0), mask, st, i, act)
        if not nxt:
            break
        layer = _select(list(nxt.values()), lam, s0)
        for st in layer:
            consider(st)
    return best[0]


def _evaluate(prob, planner, windows, seq):
    """Score a complete visiting order from scratch (same scoring as the search).
    Returns None if the order breaks any rule."""
    n, ids = prob.n, prob.ids
    if not seq:
        if prob.first_i is not None or prob.last_i is not None or windows:
            return None
        return (0.0, 0.0, -round(planner.s0, 3))
    if prob.first_i is not None and seq[0] != prob.first_i:
        return None
    if prob.last_i is not None and seq[-1] != prob.last_i:
        return None
    full_mask = (1 << len(windows)) - 1
    counts = [0] * n
    clock, last, value, tier, mask = planner.s0, -1, 0.0, 0.0, 0
    for i in seq:
        c = counts[i]
        if c >= prob.cap[i]:
            return None
        prev = ids[last] if last >= 0 else planner.start_db_id
        act = planner.activity(clock, prev, ids[i])
        if act[1] > planner.closing:
            return None
        if windows:
            pid = _match_window(windows, mask, i, act[1])
            if pid >= 0:
                mask |= 1 << pid
        rf = prob.repeat_factor(i, c, last, n)
        if rf <= 0.0:
            return None
        value += prob.val(i, c) * rf
        tier += prob.tier_add(i, c)
        counts[i] = c + 1
        clock, last = act[4], i
    if mask != full_mask:
        return None
    return (round(tier, 1), round(value, 4), -round(clock, 3))


def _polish(prob, planner, windows, seq, key):
    """Local search on the finished plan: move, swap, substitute or insert
    single stops while that keeps improving the score."""
    n = prob.n
    for _ in range(POLISH_MAX_PASSES):
        L = len(seq)
        lo = 1 if prob.first_i is not None else 0
        hi = L - 1 if prob.last_i is not None else L
        cands = []
        for a in range(lo, hi):
            for b in range(lo, hi):
                if a != b:
                    s = seq[:]
                    s.insert(b, s.pop(a))
                    cands.append(s)
        for a in range(lo, hi):
            for b in range(a + 1, hi):
                if seq[a] != seq[b]:
                    s = seq[:]
                    s[a], s[b] = s[b], s[a]
                    cands.append(s)
        for a in range(lo, hi):
            for j in range(n):
                if j != seq[a]:
                    s = seq[:]
                    s[a] = j
                    cands.append(s)
        for pos in range(lo, hi + 1):
            for j in range(n):
                cands.append(seq[:pos] + [j] + seq[pos:])
        best_key, best_seq = key, None
        for s in cands:
            k = _evaluate(prob, planner, windows, s)
            if k is not None and k > best_key:
                best_key, best_seq = k, s
        if best_seq is None:
            break
        seq, key = best_seq, best_key
    return seq, key


def _plan(prob, planner):
    """Returns the final visiting order as a list of ride indices."""
    attempts = []
    if prob.window_targets:
        for step in PIN_WINDOW_STEPS_MIN:
            attempts.append([(i, t - step, t + step) for i, t in prob.window_targets])
    attempts.append([])
    for windows in attempts:
        res = _beam_search(prob, planner, windows)
        if res is None:
            continue
        key, st, final = res
        seq = _sequence_from(st) + ([final] if final is not None else [])
        seq, key = _polish(prob, planner, windows, seq, key)
        return seq

    # A pinned first/last ride can't be queued before closing at all. The pin is
    # still a hard rule, so honour it anyway and plan whatever else fits around it.
    relaxed = copy.copy(prob)
    relaxed.last_i = None
    relaxed.window_targets = []
    res = _beam_search(relaxed, planner, [])
    seq = _sequence_from(res[1]) if res else []
    if prob.first_i is not None and (not seq or seq[0] != prob.first_i):
        seq = [prob.first_i] + seq
    if prob.last_i is not None:
        seq = seq + [prob.last_i]
    return seq


def _build_output(prob, planner, seq):
    clock, last, out = planner.s0, -1, []
    for i in seq:
        prev = prob.ids[last] if last >= 0 else planner.start_db_id
        act = planner.activity(clock, prev, prob.ids[i])
        out.append((prob.keys[i], act[2], int(act[1])))
        clock, last = act[4], i
    return out


# ── public entry point ──────────────────────────────────────────────
def compute_and_print_route(ride_counts, ride_locked=None, closed_ride_keys=None,
                             breaks=None, start_time=None, start_key="entrance",
                             live_waits=None, time_pinned=None, max_counts=None,
                             close_hour=None, close_minute=None, override_closed_keys=None,
                             ride_priority_order=None, completed_counts=None):
    """
    Main entry point for route computation.

    Args:
        ride_counts: {ride_key: count} for every CHECKED ride
        ride_locked: {ride_key: bool} for force-included rides
        closed_ride_keys: iterable of ride_keys that are currently closed
        breaks: list of (start_min, end_min) pairs (minutes since midnight)
        start_time: datetime to start from (defaults to now)
        start_key: ride_key or "entrance" to start from
        live_waits: {ride_key: current_wait_minutes} today's live readings
        time_pinned: list of {ride_key, target_minutes} dicts. 0 = ride first,
            1440 = ride last, anything else = ride within MAX_DRAG_DRIFT_MIN
            minutes of that time of day (widened only if impossible).
        max_counts: {ride_key: max_visits} upper limit per ride (None = no limit)
        override_closed_keys: iterable of ride_keys that are closed but have
            been manually checked (Advanced Mode "yellow check")
        ride_priority_order: list of ride_keys, most important first
        completed_counts: {ride_key: visits already done today} (the log)

    Returns:
        List of (ride_key, predicted_wait, queue_join_minutes) tuples.
        [] if nothing fits, None if computation failed entirely.
    """
    _t_start = time.time()
    ride_locked = dict(ride_locked or {})
    completed_counts = dict(completed_counts or {})

    if time_pinned:
        for pin in time_pinned:
            key = pin.get('ride_key')
            if key and key not in ride_locked:
                ride_locked[key] = True

    closed_ride_keys = set(closed_ride_keys or [])
    all_closed_keys = set(closed_ride_keys)
    override_closed_keys = set(override_closed_keys or [])
    override_closed_keys &= closed_ride_keys
    closed_ride_keys -= override_closed_keys
    breaks = breaks or []

    if start_time is None:
        start_time = datetime.now(PARK_TIMEZONE).replace(tzinfo=None)
    elif start_time.tzinfo is not None:
        start_time = start_time.astimezone(PARK_TIMEZONE).replace(tzinfo=None)

    checked = {k: c for k, c in ride_counts.items() if c and c > 0}
    if not checked:
        return []

    # Closed rides are dropped completely
    checked = {k: c for k, c in checked.items() if k not in closed_ride_keys}
    if not checked:
        return []

    try:
        key_to_id, id_to_key = _load_ride_id_map()
    except Exception:
        import traceback
        print("DEBUG route computation failed while loading ride ID map:")
        print("DEBUG SUPABASE_URL =", repr(SUPABASE_URL))
        print("DEBUG SUPABASE_KEY set? ", bool(SUPABASE_KEY))
        traceback.print_exc()
        return None

    checked = {k: c for k, c in checked.items() if k in key_to_id}
    if not checked:
        return []

    all_db_ids = [key_to_id[k] for k in checked]
    histories = _load_wait_history(all_db_ids)
    for key in override_closed_keys:
        db_id = key_to_id.get(key)
        if db_id in histories:
            histories[db_id] = [(ts, w) for ts, w in histories[db_id] if w > 0]
    walk_map = _load_walk_times()
    try:
        durations = _load_ride_durations()
    except Exception:
        durations = {}

    current_waits = {}
    if live_waits:
        for key, wait in live_waits.items():
            if key in override_closed_keys:
                continue
            if key in checked and key in key_to_id and wait is not None:
                current_waits[key_to_id[key]] = wait

    # Rides anchored to a live reading learn their baseline from PREVIOUS days only,
    # otherwise today's samples would be counted twice.
    today_date = _op_date(start_time)
    for db_id in all_db_ids:
        if db_id in current_waits:
            histories[db_id] = [(ts, w) for ts, w in histories.get(db_id, []) if _op_date(ts) < today_date]
    _ctx.bins = {}

    historical_now_by_id = {
        db_id: _historical_wait_curve(histories.get(db_id, []), start_time)
        for db_id in all_db_ids
    }

    park_ratio = None
    if USE_PARK_FACTOR:
        try:
            pr_live = {
                key_to_id[k]: w for k, w in (live_waits or {}).items()
                if w is not None and k in key_to_id and k not in all_closed_keys
            }
            if pr_live:
                pr_hist = _load_wait_history(list(pr_live))
                num = den = 0.0
                used = 0
                for db_id, wait in pr_live.items():
                    hn = historical_now_by_id.get(db_id)
                    if hn is None:
                        prev = [(ts, w) for ts, w in pr_hist.get(db_id, []) if _op_date(ts) < today_date]
                        hn = _historical_wait_curve(prev, start_time)
                    if hn is not None and hn > MIN_MEANINGFUL_BASELINE_MIN:
                        num += wait
                        den += hn
                        used += 1
                if used >= CROWD_MIN_RIDES and den > 0:
                    park_ratio = max(CROWD_RATIO_MIN, min(CROWD_RATIO_MAX, num / den))
        except Exception:
            park_ratio = None

    entrance_id = key_to_id.get("Entrance", ENTRANCE_DB_ID)
    start_db_id = entrance_id if start_key == "entrance" else key_to_id.get(start_key, entrance_id)

    close_hour = close_hour if close_hour is not None else DEFAULT_PARK_CLOSE_HOUR
    close_minute = close_minute if close_minute is not None else DEFAULT_PARK_CLOSE_MINUTE
    closing_min = close_hour * 60 + close_minute
    if closing_min <= OPERATING_DAY_START_HOUR * 60:
        closing_min += 1440          # an after-midnight close (2 AM) = minute 1560 of the operating day

    s0 = start_time.hour * 60 + start_time.minute + start_time.second / 60.0
    s0 = (start_time - datetime.combine(_op_date(start_time), datetime.min.time())).total_seconds() / 60.0
    earliest_min = {
        key_to_id[k]: s0 + FORCE_OPEN_BUFFER_MIN
        for k in override_closed_keys if k in key_to_id
    }
    break_windows = [(float(a), float(b)) for a, b in breaks if b > a]

    prob = _make_problem(checked, key_to_id, ride_locked, completed_counts, max_counts,
                         time_pinned, ride_priority_order)
    if prob is None:
        return []

    planner = _Planner(histories, walk_map, durations, start_time, closing_min, break_windows,
                       start_db_id, current_waits, historical_now_by_id, earliest_min, park_ratio)
    prob.lam = _estimate_lambda(prob, planner)

    _t_plan = time.time()
    last_timing["load_s"] = round(_t_plan - _t_start, 2)
    seq = _plan(prob, planner)
    last_timing["plan_s"] = round(time.time() - _t_plan, 2)
    last_timing["total_s"] = round(time.time() - _t_start, 2)
    last_timing["stops"] = len(seq)
    return _build_output(prob, planner, seq)