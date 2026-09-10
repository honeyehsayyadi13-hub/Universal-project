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
     prediction reaches. This keeps near-term forecasts consistent with
     how busy the park is actually running *today*, instead of just
     reporting a generic historical average for that time slot.
  6. Time-pinned rides (from drag-to-slot or click-to-lock) are forced
     to specific times of day or positions (first/last), as long as
     doing so doesn't cause other forced rides to drop before closing.
  7. The plan doesn't stop the moment every checked/locked/counted ride
     has been visited once -- it keeps cycling back through every
     selected ride, for as long as there's still daylight left, so the
     schedule runs all the way to park close instead of stopping early.

Call `compute_and_print_route(...)` from a button press on the
frontend. Results print to the terminal AND are returned as a list of
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
from Data import get_park_hours   # add at the top of the file if not already there

from supabase import create_client, Client


SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://azbjjemtcpaeqfqauzod.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_4oD2QwAuB39Sd9KInIRnsw_jEMOY7pK")

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
WEEKEND_DAYS = {5, 6}            # Saturday, Sunday (Monday == 0)
RECENCY_HALF_LIFE_DAYS = 45      # historical samples lose half their weight every 45 days
ANCHOR_DECAY_HOURS = 3.0         # how many hours out we keep trusting today's live reading
MIN_MEANINGFUL_BASELINE_MIN = 3.0 # min historical baseline for ratio-based anchoring
ANCHOR_RATIO_MIN = 0.15          # min ratio clamp for live anchor
ANCHOR_RATIO_MAX = 4.0           # max ratio clamp for live anchor
DEFAULT_WAIT_MIN = 30            # fallback if a ride has zero usable history
DEFAULT_WALK_MIN = 10            # fallback if a ride pair has no walk_times row
DEFAULT_RIDE_DURATION_MIN = 3    # fallback if a ride has no ride_duration row
BRUTE_FORCE_LIMIT = 8            # exact solve (permutations) up to this many stops
PARK_OPEN_HOUR  = 9              # 9:00 AM fallback (overridden by live API hours)
PARK_CLOSE_HOUR = 20             # 8:00 PM fallback (overridden by live API hours)
ENTRANCE_DB_ID = 0               # matches the "id" of the entrance row in `rides`
POST_BREAK_BUFFER_MIN = 2        # time to get moving again after a break ends
PARK_TIMEZONE = ZoneInfo("America/New_York")  # Universal Orlando is Eastern time
MAX_DRAG_DRIFT_MIN = 30          # a dragged-and-dropped ride must land within this many
                                  # minutes of the queue-join time of whatever ride it
                                  # displaced, whenever a slot like that exists at all

# ── ride "importance" tiers ─────────────────────────────────────────
RIDE_PRIORITY_WEIGHT = {
    "velociCoaster": 3.0,
    "hulk":           3.0,
    "hagrid":         3.0,
    "spiderMan":      2.0,
    "harryPotter":    2.0,
    "riverAdventure": 2.0,
    "skullIsland":    1.5,
    "stormForce":     1.5,
    "doctorDoom":     1.5,
    "hippogriff":     1.5,
}


# ── data loading ─────────────────────────────────────────────────────
def _load_ride_id_map():
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


def _load_wait_history(db_ids):
    """Return {db_id: [(timestamp, waittime), ...]} using valid, non-issue rows."""
    history = defaultdict(list)
    if not db_ids:
        return history
    resp = (
        _get_client()
        .table("ride_waits")
        .select("ride_id, timestamp, waittime, issue_with_ride")
        .in_("ride_id", db_ids)
        .execute()
    )
    for row in resp.data:
        if row.get("issue_with_ride"):
            continue
        if row.get("waittime") is None:
            continue
        history[row["ride_id"]].append((_parse_ts(row["timestamp"]), row["waittime"]))
    return history


def _load_walk_times():
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
def _historical_wait_curve(history_for_ride, target_time):
    """
    Kernel-weighted historical average wait at this time-of-day, weighted by:
      - how close the sample's time-of-day is to target_time (Gaussian kernel)
      - whether the sample falls on the same weekday, similar day-type, or different
      - how recent the sample is (older data counts less)

    Returns None if there's no history at all to work from.
    """
    if not history_for_ride:
        return None

    target_minutes = target_time.hour * 60 + target_time.minute
    target_weekday = target_time.weekday()
    target_is_weekend = target_weekday in WEEKEND_DAYS

    weighted_sum, weight_total = 0.0, 0.0
    for ts, wait in history_for_ride:
        sample_minutes = ts.hour * 60 + ts.minute
        raw_delta = abs(sample_minutes - target_minutes)
        delta = min(raw_delta, 1440 - raw_delta)
        time_kernel = math.exp(-(delta ** 2) / (2 * TIME_KERNEL_BANDWIDTH_MIN ** 2))

        if ts.weekday() == target_weekday:
            day_weight = SAME_DAY_WEIGHT
        elif (ts.weekday() in WEEKEND_DAYS) == target_is_weekend:
            day_weight = WEEKEND_GROUP_WEIGHT
        else:
            day_weight = DIFF_DAY_WEIGHT

        age_days = max(0.0, (target_time - ts).total_seconds() / 86400.0)
        recency_weight = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)

        w = time_kernel * day_weight * recency_weight
        weighted_sum += w * wait
        weight_total += w

    if weight_total < 1e-6:
        # Nothing matched time-of-day well -- fall back to recency-weighted average
        fb_sum, fb_weight = 0.0, 0.0
        for ts, wait in history_for_ride:
            age_days = max(0.0, (target_time - ts).total_seconds() / 86400.0)
            w = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
            fb_sum += w * wait
            fb_weight += w
        if fb_weight > 1e-9:
            return fb_sum / fb_weight
        return sum(wait for _, wait in history_for_ride) / len(history_for_ride)

    return weighted_sum / weight_total


def _predict_wait(history_for_ride, target_time, current_wait=None, now=None, historical_now=None):
    """
    Predicts the wait at `target_time`.

    When we have a live current reading (`current_wait`, taken at `now`), we
    anchor to it: predicted wait = today's actual current wait, scaled by how
    much the historical time-of-day curve typically *changes proportionally*
    between `now` and `target_time`. The ratio is clamped so one noisy live
    reading can't distort the whole curve.

    As `target_time` moves further from `now`, we fade out from the anchor
    and blend toward the plain historical time-of-day curve.
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
    anchor_weight = math.exp(-hours_ahead / ANCHOR_DECAY_HOURS)

    if historical_now > MIN_MEANINGFUL_BASELINE_MIN:
        ratio = current_wait / historical_now
        ratio = max(ANCHOR_RATIO_MIN, min(ANCHOR_RATIO_MAX, ratio))
        anchor_adjusted = historical_target * ratio
    else:
        anchor_adjusted = current_wait + historical_target

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


# ── route simulation ─────────────────────────────────────────────────
def _simulate_route(order, histories, walk_map, durations, start_time, break_windows, start_db_id,
                     current_waits=None, historical_now_by_id=None):
    """Walk `order` (list of db_ids) starting at start_time from `start_db_id`.
    Returns (total_time, details) where details is a list of dicts with timing info."""
    current_waits = current_waits or {}
    historical_now_by_id = historical_now_by_id or {}

    clock = start_time
    total = 0.0
    details = []
    prev = start_db_id
    for db_id in order:
        clock = _apply_breaks(clock, break_windows)

        wt = _walk_time(walk_map, prev, db_id) if prev is not None else 0
        if wt:
            clock += timedelta(minutes=wt)
            total += wt

        queue_join_clock = clock
        predicted_wait = _predict_wait(
            histories.get(db_id, []),
            clock,
            current_wait=current_waits.get(db_id),
            now=start_time,
            historical_now=historical_now_by_id.get(db_id),
        )
        clock += timedelta(minutes=predicted_wait)
        total += predicted_wait

        ride_time = durations.get(db_id, DEFAULT_RIDE_DURATION_MIN)
        clock += timedelta(minutes=ride_time)
        total += ride_time

        details.append({
            "db_id": db_id,
            "walk_from_prev": wt,
            "predicted_wait": predicted_wait,
            "ride_duration": ride_time,
            "queue_join_clock": queue_join_clock,
            "arrival_clock": clock,
        })
        prev = db_id

    return total, details


def _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                  current_waits=None, historical_now_by_id=None):
    """
    Score a candidate route for comparison.
    Primary objective: maximize how many rides you actually get in line for before closing.
    Secondary objective: minimize time spent on just those committed rides.
    Returns (fits_count, committed_total_minutes, details).
    """
    _, details = _simulate_route(order, histories, walk_map, durations, start_time, break_windows, start_db_id,
                                  current_waits=current_waits, historical_now_by_id=historical_now_by_id)
    fits_count = 0
    committed_total = 0.0
    for d in details:
        if d["queue_join_clock"] <= closing_time:
            fits_count += 1
            committed_total += d["walk_from_prev"] + d["predicted_wait"] + d["ride_duration"]
        else:
            break
    return fits_count, committed_total, details


def _better(score_a, score_b):
    """True if score_a (fits_count, total_minutes) beats score_b."""
    fits_a, total_a = score_a
    fits_b, total_b = score_b
    if fits_a != fits_b:
        return fits_a > fits_b
    return total_a < total_b - 1e-6


def _solve_order(db_ids, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                  current_waits=None, historical_now_by_id=None):
    """Find the best visiting order for the given (possibly-repeated) list of db_ids.
    Exact brute force for small lists, nearest-neighbor + 2-opt for larger ones."""
    if len(db_ids) == 0:
        return [], 0.0, []

    if len(db_ids) == 1:
        order = list(db_ids)
        _, total, details = _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                                          current_waits=current_waits, historical_now_by_id=historical_now_by_id)
        return order, total, details

    if len(db_ids) <= BRUTE_FORCE_LIMIT:
        best_order, best_details = None, None
        best_score = (-1, math.inf)
        seen = set()
        for perm in itertools.permutations(db_ids):
            if perm in seen:
                continue
            seen.add(perm)
            fits, total, details = _route_score(list(perm), histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                                                  current_waits=current_waits, historical_now_by_id=historical_now_by_id)
            if _better((fits, total), best_score):
                best_order, best_score, best_details = list(perm), (fits, total), details
        return best_order, best_score[1], best_details

    # Nearest-neighbor construction, then 2-opt improvement
    remaining = list(db_ids)
    order = []
    last = start_db_id
    while remaining:
        nxt = min(remaining, key=lambda r: _walk_time(walk_map, last, r))
        order.append(nxt)
        remaining.remove(nxt)
        last = nxt

    fits, total, details = _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                                          current_waits=current_waits, historical_now_by_id=historical_now_by_id)
    score = (fits, total)

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                cand_fits, cand_total, cand_details = _route_score(
                    candidate, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                    current_waits=current_waits, historical_now_by_id=historical_now_by_id
                )
                if _better((cand_fits, cand_total), score):
                    order, score, details = candidate, (cand_fits, cand_total), cand_details
                    improved = True
    return order, score[1], details


# ── forced (locked + counted-up) scheduling ───────────────────────────
def _fit_forced(forced_items, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                 current_waits=None, historical_now_by_id=None):
    """
    Try to schedule every item in `forced_items` (each a dict with db_id/ride_key/kind).
    If they don't all fit before closing, drop the lowest-priority ones --
    EXTRA (counted-up) visits first, then LOCKED base visits.
    Returns (kept_items, dropped_items, order, details).
    """
    forced_items = list(forced_items)
    dropped = []

    while forced_items:
        ids = [it["db_id"] for it in forced_items]
        order, _, details = _solve_order(
            ids, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
            current_waits=current_waits, historical_now_by_id=historical_now_by_id
        )
        fits = sum(1 for d in details if d["queue_join_clock"] <= closing_time)
        if fits >= len(forced_items):
            return forced_items, dropped, order, details

        drop_kind = "extra" if any(it["kind"] == "extra" for it in forced_items) else "locked"
        for i, it in enumerate(forced_items):
            if it["kind"] == drop_kind:
                dropped.append(forced_items.pop(i))
                break

    return [], dropped, [], []


# ── optional-visit insertion ─────────────────────────────────────────
def _insert_optional(base_order, optional_items, histories, walk_map, durations,
                      start_time, closing_time, break_windows, start_db_id,
                      current_waits=None, historical_now_by_id=None):
    """
    Greedily inserts optional (unlocked, single-count) rides into the
    already-fixed forced schedule, one at a time, always taking whichever
    remaining ride + position adds the least time.
    """
    order = list(base_order)
    included, remaining = [], list(optional_items)
    must_fit = len(order)

    changed = True
    while remaining and changed:
        changed = False
        best = None
        for item in remaining:
            for pos in range(len(order) + 1):
                candidate = order[:pos] + [item["db_id"]] + order[pos:]
                _, details = _simulate_route(candidate, histories, walk_map, durations, start_time, break_windows, start_db_id,
                                              current_waits=current_waits, historical_now_by_id=historical_now_by_id)
                fits = sum(1 for d in details if d["queue_join_clock"] <= closing_time)
                if fits < must_fit + 1:
                    continue
                added = details[pos]["walk_from_prev"] + details[pos]["predicted_wait"] + details[pos]["ride_duration"]
                if best is None or added < best[0]:
                    best = (added, candidate, item)
        if best is not None:
            _, candidate, item = best
            order = candidate
            included.append(item)
            remaining.remove(item)
            must_fit += 1
            changed = True

    return order, included, remaining


# ── fill remaining daylight ──────────────────────────────────────────
def _fill_until_close(order, candidate_ids, weights, histories, walk_map, durations,
                       start_time, closing_time, break_windows, start_db_id,
                       current_waits=None, historical_now_by_id=None, max_counts_by_id=None):
    """
    Keeps appending rides for as long as there's time to queue before closing.
    Uses weighted round-robin so every ride cycles fairly, with ties broken
    by recency (time since last visit) rather than predicted wait.
    """
    order = list(order)
    if not candidate_ids:
        return order

    visit_counts = {db_id: 0 for db_id in candidate_ids}
    for db_id in order:
        if db_id in visit_counts:
            visit_counts[db_id] += 1

    last_visit_step = {db_id: -1 for db_id in candidate_ids}
    for step_idx, db_id in enumerate(order):
        if db_id in last_visit_step:
            last_visit_step[db_id] = step_idx

    step = len(order)

    while True:
        ranked = sorted(
            candidate_ids,
            key=lambda db_id: (
                visit_counts[db_id] / weights.get(db_id, 1),
                last_visit_step[db_id],
                historical_now_by_id.get(db_id) if historical_now_by_id.get(db_id) is not None else DEFAULT_WAIT_MIN,
                db_id,
            ),
        )

        placed = False
        for db_id in ranked:
            max_for_db = (max_counts_by_id or {}).get(db_id, float('inf'))
            if visit_counts[db_id] >= max_for_db:
                continue
            candidate = order + [db_id]
            _, cand_details = _simulate_route(
                candidate, histories, walk_map, durations, start_time, break_windows, start_db_id,
                current_waits=current_waits, historical_now_by_id=historical_now_by_id
            )
            last = cand_details[-1]
            if last["queue_join_clock"] > closing_time:
                continue
            order.append(db_id)
            visit_counts[db_id] += 1
            last_visit_step[db_id] = step
            step += 1
            placed = True
            break

        if not placed:
            break

    return order

def _or_opt_refine(order, forced_db_ids, histories, walk_map, durations,
                    start_time, closing_time, break_windows, start_db_id,
                    current_waits=None, historical_now_by_id=None, max_passes=3):
    """Single-stop relocation local search. Only moves stops NOT in
    forced_db_ids (locked/extra), so it never disturbs guaranteed visits."""
    order = list(order)
    forced_set = set(forced_db_ids)

    for _ in range(max_passes):
        improved = False
        for i in range(len(order)):
            if order[i] in forced_set:
                continue
            item = order[i]
            without = order[:i] + order[i+1:]

            base_fits, base_total, _ = _route_score(
                order, histories, walk_map, durations, start_time, closing_time,
                break_windows, start_db_id, current_waits=current_waits,
                historical_now_by_id=historical_now_by_id
            )

            best = (base_fits, base_total, i)
            for pos in range(len(without) + 1):
                candidate = without[:pos] + [item] + without[pos:]
                fits, total, _ = _route_score(
                    candidate, histories, walk_map, durations, start_time, closing_time,
                    break_windows, start_db_id, current_waits=current_waits,
                    historical_now_by_id=historical_now_by_id
                )
                if _better((fits, total), (best[0], best[1])):
                    best = (fits, total, pos)

            if best[2] != i:
                order = without[:best[2]] + [item] + without[best[2]:]
                improved = True
        if not improved:
            break
    return order
# ── time-pin reordering ──────────────────────────────────────────────
def _reorder_for_time_pins(order, pin_targets, histories, walk_map, durations,
                            start_time, closing_time, break_windows, start_db_id,
                            current_waits=None, historical_now_by_id=None):
    """
    Reorders rides to honor time-pin targets (from drag-to-slot or click-to-lock).

    Sentinel values (0 = force first, 1440 = force last) are HARD
    constraints: a ride pinned first ALWAYS ends up first, and a ride
    pinned last ALWAYS ends up last (with nothing appended after it,
    since this reordering pass runs after every other scheduling step).
    This is enforced unconditionally -- it does not back off even if it
    costs the route some fits_count, because the whole point of pinning
    something first/last is that the person wants exactly that.

    For a normal (non-sentinel) pin -- i.e. a ride dragged onto some
    other ride's slot -- we look at every possible insertion position and
    require the result to land within MAX_DRAG_DRIFT_MIN minutes of the
    target time (the queue-join time of whatever ride occupied that slot)
    whenever any such position exists at all. Among those, we prefer ones
    that also keep the existing fits_count, but the drift window always
    wins over fits_count for a normal pin -- only if NO position keeps it
    within the drift window do we fall back to fits-preserving-but-farther,
    and only if that's empty too do we fall back to closest-overall.
    """
    order = list(order)
    if not order or not pin_targets:
        return order

    fits_baseline, _, _ = _route_score(
        order, histories, walk_map, durations, start_time, closing_time,
        break_windows, start_db_id, current_waits=current_waits,
        historical_now_by_id=historical_now_by_id,
    )

    for (db_id, inst_idx), target_minutes in sorted(pin_targets.items()):
        occurrences = [i for i, x in enumerate(order) if x == db_id]
        if inst_idx >= len(occurrences):
            continue
        src_pos = occurrences[inst_idx]
        order_without = order[:src_pos] + order[src_pos + 1:]

        # Sentinel "force first" (0) -- unconditional, always honored.
        if target_minutes == 0:
            order = [db_id] + order_without
            continue

        # Sentinel "force last" (1440) -- unconditional, always honored.
        # Because this reordering pass is the last step before the route
        # is simulated and returned, appending here guarantees nothing
        # else ever lands after this ride.
        if target_minutes == 1440:
            order = order_without + [db_id]
            continue

        # Normal pin: find the insertion position closest to target_minutes,
        # preferring positions within MAX_DRAG_DRIFT_MIN minutes of it.
        candidates = []  # (distance_minutes, fits_ok, position)
        for pos in range(len(order_without) + 1):
            candidate = order_without[:pos] + [db_id] + order_without[pos:]
            fits, _, details = _route_score(
                candidate, histories, walk_map, durations, start_time, closing_time,
                break_windows, start_db_id, current_waits=current_waits,
                historical_now_by_id=historical_now_by_id,
            )
            if pos >= len(details):
                continue
            qjc = details[pos]['queue_join_clock']
            dist = abs(qjc.hour * 60 + qjc.minute - target_minutes)
            candidates.append((dist, fits >= fits_baseline, pos))

        if not candidates:
            # Nothing to insert into -- leave this pin's ride where it was.
            order = order_without[:src_pos] + [db_id] + order_without[src_pos:]
            continue

        within_and_fits = [c for c in candidates if c[0] <= MAX_DRAG_DRIFT_MIN and c[1]]
        within_only     = [c for c in candidates if c[0] <= MAX_DRAG_DRIFT_MIN]
        fits_only       = [c for c in candidates if c[1]]

        if within_and_fits:
            pool = within_and_fits
        elif within_only:
            # Guarantee the drift window even if it costs a fit -- staying
            # close to the ride that was dropped onto matters more here
            # than preserving fits_count for a plain (non-sentinel) pin.
            pool = within_only
        else:
            # No position lands within 30 min -- get as close as possible.
            # fits_count is never a reason to move further from the target.
            pool = candidates

        best_pos = min(pool, key=lambda c: c[0])[2]
        order = order_without[:best_pos] + [db_id] + order_without[best_pos:]

    return order


# ── pin relative-order enforcement ───────────────────────────────────
def _enforce_pin_order(order, pin_items):
    """
    Guarantees pinned rides appear in the same relative order as they did
    in the route when the user pinned them (tracked via route_index).

    After _reorder_for_time_pins places each pin near its target time, two
    pins could end up swapped -- e.g. the user pinned Hagrid's (slot 2)
    then Hulk (slot 5), but time-proximity logic placed Hulk before Hagrid's.
    This pass fixes that by re-assigning pinned positions to match the
    original route_index ranking, without touching non-pinned rides.

    pin_items: list of (db_id, instance_index, original_route_index)
    """
    if len(pin_items) < 2:
        return order

    order = list(order)
    pin_set = {(db_id, inst): orig_idx for db_id, inst, orig_idx in pin_items}

    # Walk order and locate each pinned (db_id, instance_index)
    occurrence = {}
    pinned_at = []  # (position, db_id, instance_index, original_route_index)
    for pos, db_id in enumerate(order):
        inst = occurrence.get(db_id, 0)
        occurrence[db_id] = inst + 1
        key = (db_id, inst)
        if key in pin_set:
            pinned_at.append((pos, db_id, inst, pin_set[key]))

    if len(pinned_at) < 2:
        return order

    # Slots the pinned rides currently occupy, ascending
    positions = sorted(p[0] for p in pinned_at)

    # Rides sorted by original_route_index = desired relative order
    rides_in_order = sorted(pinned_at, key=lambda p: p[3])

    # Re-assign each ride to the next slot in position order
    for (_, db_id, _, _), pos in zip(rides_in_order, positions):
        order[pos] = db_id

    return order


# ── public entry point ──────────────────────────────────────────────
def compute_and_print_route(ride_counts, ride_locked=None, closed_ride_keys=None,
                             breaks=None, start_time=None, start_key="entrance",
                             live_waits=None, time_pinned=None, max_counts=None,
                             park_open_minutes=None, park_close_minutes=None):
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
        time_pinned: list of {ride_key, instance_index, target_minutes} dicts
        max_counts: {ride_key: max_visits} upper limit per ride

    Returns:
        List of (ride_key, predicted_wait, queue_join_minutes) tuples for
        rides that fit before closing. Returns [] if nothing fits.
        Returns None if computation failed entirely.
    """
    ride_locked = dict(ride_locked or {})

    # Time-pinned rides are force-included (treated as locked)
    if time_pinned:
        for pin in time_pinned:
            key = pin.get('ride_key')
            if key and key not in ride_locked:
                ride_locked[key] = True

    closed_ride_keys = set(closed_ride_keys or [])
    breaks = breaks or []

    if start_time is None:
        start_time = datetime.now(PARK_TIMEZONE).replace(tzinfo=None)
    elif start_time.tzinfo is not None:
        start_time = start_time.astimezone(PARK_TIMEZONE).replace(tzinfo=None)
        
    # Never start before the park opens
    open_h = (park_open_minutes // 60) if park_open_minutes is not None else PARK_OPEN_HOUR
    open_m = (park_open_minutes %  60) if park_open_minutes is not None else 0
    park_open_dt = start_time.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    if start_time < park_open_dt:
        start_time = park_open_dt

    checked = {k: c for k, c in ride_counts.items() if c and c > 0}
    if not checked:
        print("\nNo rides selected -- check some boxes on the sidebar first.\n")
        return []

    # RULE 1: Drop closed rides completely
    ignored_closed = sorted(k for k in checked if k in closed_ride_keys)
    checked = {k: c for k, c in checked.items() if k not in closed_ride_keys}
    if ignored_closed:
        print(f"Skipping currently-closed rides: {ignored_closed}")
    if not checked:
        print("\nEverything selected is currently closed.\n")
        return []

    try:
        key_to_id, id_to_key = _load_ride_id_map()
    except Exception as e:
        print(f"\nCould not reach Supabase: {e}\n")
        return None

    unknown = [k for k in checked if k not in key_to_id]
    if unknown:
        print(f"Warning: no DB entry found for rides {unknown} -- skipping them.")
    checked = {k: c for k, c in checked.items() if k in key_to_id}
    if not checked:
        print("\nNone of the selected rides were found in the database.\n")
        return []

    all_db_ids = [key_to_id[k] for k in checked]
    histories = _load_wait_history(all_db_ids)
    walk_map = _load_walk_times()
    try:
        durations = _load_ride_durations()
    except Exception as e:
        print(f"Warning: couldn't load ride_duration table ({e}); using "
              f"{DEFAULT_RIDE_DURATION_MIN}-min default for every ride.")
        durations = {}

    current_waits = {}
    if live_waits:
        for key, wait in live_waits.items():
            if key in checked and key in key_to_id and wait is not None:
                current_waits[key_to_id[key]] = wait

    historical_now_by_id = {
        db_id: _historical_wait_curve(histories.get(db_id, []), start_time)
        for db_id in all_db_ids
    }

    start_db_id = ENTRANCE_DB_ID if start_key == "entrance" else key_to_id.get(start_key, ENTRANCE_DB_ID)
    break_windows = _resolve_break_windows(breaks, start_time.date())

    close_h = (park_close_minutes // 60) if park_close_minutes is not None else PARK_CLOSE_HOUR
    close_m = (park_close_minutes %  60) if park_close_minutes is not None else 0
    closing_time = start_time.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    if closing_time <= start_time:
        print(f"\nHeads up: it's already past {closing_time.strftime('%I:%M %p')} closing time.\n")

    max_counts_by_id = {}
    if max_counts:
        for key, max_val in max_counts.items():
            if key in key_to_id and key in checked:
                max_counts_by_id[key_to_id[key]] = float('inf') if max_val is None else float(max_val)

    # RULE 2: Split into forced (locked base + counted-up extras) vs optional
    locked_instances, extra_instances, optional_instances = [], [], []
    for key, count in checked.items():
        db_id = key_to_id[key]
        max_for_ride = max_counts_by_id.get(db_id, float('inf'))
        if max_for_ride == 0:
            continue
        is_locked = bool(ride_locked.get(key))
        if is_locked:
            locked_instances.append({"db_id": db_id, "ride_key": key, "kind": "locked"})
        else:
            optional_instances.append({"db_id": db_id, "ride_key": key, "kind": "optional"})
        num_extras = count - 1
        if max_for_ride != float('inf'):
            num_extras = min(num_extras, max(0, int(max_for_ride) - 1))
        for _ in range(num_extras):
            extra_instances.append({"db_id": db_id, "ride_key": key, "kind": "extra"})

    forced_pool = locked_instances + extra_instances
    kept_forced, dropped_forced, forced_order, _ = _fit_forced(
        forced_pool, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
        current_waits=current_waits, historical_now_by_id=historical_now_by_id
    )

    final_order, included_optional, skipped_optional = _insert_optional(
        forced_order, optional_instances, histories, walk_map, durations,
        start_time, closing_time, break_windows, start_db_id,
        current_waits=current_waits, historical_now_by_id=historical_now_by_id
    )

    # RULE 6: Fill remaining daylight with weighted round-robin
    fill_weights = {
        key_to_id[k]: count * RIDE_PRIORITY_WEIGHT.get(k, 1.0)
        for k, count in checked.items()
    }
    final_order = _fill_until_close(
        final_order, all_db_ids, fill_weights, histories, walk_map, durations,
        start_time, closing_time, break_windows, start_db_id,
        current_waits=current_waits, historical_now_by_id=historical_now_by_id,
        max_counts_by_id=max_counts_by_id,
    )
    
    # Local search refinement — reduces sensitivity to small input
    # differences by pulling the greedy result toward a real local optimum.
    forced_ids = [it["db_id"] for it in kept_forced]
    final_order = _or_opt_refine(
        final_order, forced_ids, histories, walk_map, durations,
        start_time, closing_time, break_windows, start_db_id,
        current_waits=current_waits, historical_now_by_id=historical_now_by_id,
    )

    # RULE 6b: Honor time-pin placement requests (drag-to-slot, click-to-lock)
    # NOTE: this runs LAST, after forced scheduling, optional insertion, and
    # daylight-filling are all done -- that ordering is what guarantees a
    # ride pinned "last" truly ends up last with nothing appended after it.
    if time_pinned:
        pin_targets = {}
        pin_sequence = []  # (db_id, instance_index, route_index) for order enforcement
        for pin in time_pinned:
            key       = pin.get('ride_key')
            inst      = pin.get('instance_index', 0)
            tmin      = pin.get('target_minutes')
            route_idx = pin.get('route_index', -1)
            if key and key in key_to_id and tmin is not None and key in checked:
                db_id = key_to_id[key]
                pin_targets[(db_id, inst)] = tmin
                # Sentinel pins (first/last) are already unconditionally
                # placed by _reorder_for_time_pins -- exclude them from
                # relative-order enforcement to avoid interfering with that.
                if tmin not in (0, 1440) and route_idx >= 0:
                    pin_sequence.append((db_id, inst, route_idx))
        if pin_targets:
            final_order = _reorder_for_time_pins(
                final_order, pin_targets, histories, walk_map, durations,
                start_time, closing_time, break_windows, start_db_id,
                current_waits=current_waits, historical_now_by_id=historical_now_by_id,
            )
        if len(pin_sequence) >= 2:
            final_order = _enforce_pin_order(final_order, pin_sequence)

    _, details = _simulate_route(final_order, histories, walk_map, durations, start_time, break_windows, start_db_id,
                                  current_waits=current_waits, historical_now_by_id=historical_now_by_id)

    # Extract committed rides (those that fit before closing)
    committed = []
    for d in details:
        if d["queue_join_clock"] <= closing_time:
            committed.append(d)
        else:
            break
    skipped_details = details[len(committed):]
    committed_total = sum(d["walk_from_prev"] + d["predicted_wait"] + d["ride_duration"] for d in committed)

    start_label = "Entrance" if start_key == "entrance" else id_to_key.get(start_db_id, start_key)

    print("\n" + "=" * 55)
    print(f"OPTIMAL ROUTE  (starting {start_time.strftime('%A %I:%M %p')} from {start_label}, "
          f"park closes {closing_time.strftime('%I:%M %p')})")
    print("=" * 55)

    for b_start, b_end in break_windows:
        print(f"Break scheduled: {b_start.strftime('%I:%M %p')} - {b_end.strftime('%I:%M %p')}")

    if not committed:
        print("None of the selected rides fit before closing from this start time.")
    for i, d in enumerate(committed, start=1):
        name = id_to_key.get(d["db_id"], str(d["db_id"]))
        walk_note = f"  (+{d['walk_from_prev']} min walk)" if d["walk_from_prev"] else ""
        print(
            f"{i}. {name:<16} predicted wait: {d['predicted_wait']:.0f} min"
            f"  ride time: {d['ride_duration']:.0f} min"
            f"{walk_note}   -> in line by ~{d['queue_join_clock'].strftime('%I:%M %p')}"
        )

    print("-" * 55)
    print(f"Total estimated time (walking + waiting + riding): {committed_total:.0f} min")
    print(f"Rides that fit before closing: {len(committed)} / {len(details)}")

    if dropped_forced:
        drop_msgs = [f"{it['ride_key']} ({it['kind']})" for it in dropped_forced]
        print(f"\nCouldn't fit every locked/repeated ride -- had to drop: {', '.join(drop_msgs)}")

    if skipped_optional:
        names = sorted({it["ride_key"] for it in skipped_optional})
        print(f"Didn't fit in the schedule: {', '.join(names)}")

    if skipped_details:
        skipped_names = [id_to_key.get(d["db_id"], str(d["db_id"])) for d in skipped_details]
        print(f"\nWon't fit before closing today ({len(skipped_details)}): {', '.join(skipped_names)}")
        print("Uncheck a few rides, or start earlier, to fit more of them in.")

    print("=" * 55 + "\n")

    return [
        (id_to_key.get(d["db_id"], str(d["db_id"])),
         d["predicted_wait"],
         d["queue_join_clock"].hour * 60 + d["queue_join_clock"].minute)
        for d in committed
    ]


if __name__ == "__main__":
    hours = get_park_hours()
    result = compute_and_print_route(
        ride_counts={"hulk": 2, "spiderMan": 1, "doctorDoom": 1, "stormForce": 1},
        ride_locked={"spiderMan": True},
        closed_ride_keys={"riverAdventure"},
        breaks=[(12 * 60, 13 * 60)],
        live_waits={"hulk": 45, "spiderMan": 20, "doctorDoom": 15, "stormForce": 5},
        park_open_minutes=hours["open_min"],
        park_close_minutes=hours["close_min"],
    )
    print("Returned route:", result)