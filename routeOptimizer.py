"""
route_optimizer.py ( the main algorithm)

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
     reporting a generic historical average for that time slot. The
     ratio between live and historical is clamped (see
     ANCHOR_RATIO_MIN/MAX below) so a noisy or near-zero historical
     baseline can't blow a single live reading up into an absurd
     multi-hour-out forecast.
  6. The plan doesn't stop the moment every checked/locked/counted ride
     has been visited once -- it keeps cycling back through every
     selected ride, for as long as there's still daylight left, so the
     schedule runs all the way to park close instead of stopping early.
     This cycling is weighted-round-robin, not "always grab whatever's
     currently cheapest": each ride's effective weight (its sidebar
     count multiplied by its baseline popularity tier -- see
     RIDE_PRIORITY_WEIGHT below) controls roughly how often it gets an
     extra visit relative to the rest, and ties in that weighting are
     broken by *how long it's been since that ride last got a turn*
     (not by a fixed "cheapest wait wins" rule), so no pair of rides
     can permanently starve out the others just because they happen to
     have the lowest predicted wait. See `_fill_until_close` below.

Call `compute_and_print_route(...)` from a button press on the
frontend. Results print to the terminal AND are returned as a plain
list of ride_key strings (the committed order, i.e. the rides that
actually fit before closing) so the frontend can render them (e.g. in
the top route bar). Returns `None` if the route couldn't be computed
at all (bad/missing selection, Supabase unreachable, etc.) -- callers
should treat `None` as "no change", as opposed to `[]` which means
"computed successfully, but nothing fit."

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

from supabase import create_client, Client


SUPABASE_URL = "https://azbjjemtcpaeqfqauzod.supabase.co"
SUPABASE_KEY = "sb_publishable_4oD2QwAuB39Sd9KInIRnsw_jEMOY7pK"


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
                                  # but aren't the same weekday -- Sat/Sun crowd
                                  # patterns resemble each other more than a Tuesday
DIFF_DAY_WEIGHT = 0.35           # weight for a weekday-vs-weekend mismatch
WEEKEND_DAYS = {5, 6}            # Saturday, Sunday (Monday == 0)
RECENCY_HALF_LIFE_DAYS = 45      # historical samples lose half their weight every
                                  # 45 days -- crowd levels & ride popularity drift,
                                  # so a reading from a year ago shouldn't count the
                                  # same as one from last week
ANCHOR_DECAY_HOURS = 3.0         # how many hours out we keep trusting "today's live
                                  # reading + historical shift" before fading back to
                                  # the plain historical time-of-day curve
MIN_MEANINGFUL_BASELINE_MIN = 3.0
                                  # if the historical wait at "now" is below this, it's
                                  # essentially a walk-on historically and dividing by
                                  # it is not trustworthy -- a live reading of even a
                                  # few minutes would produce a huge ratio and blow up
                                  # every downstream prediction it gets multiplied into.
                                  # Below this threshold we fall back to the small,
                                  # bounded additive shift instead of a ratio.
ANCHOR_RATIO_MIN = 0.15          # even with a meaningful baseline, clamp how far a
ANCHOR_RATIO_MAX = 4.0           # single live reading is allowed to scale the rest of
                                  # the day's historical curve, so one noisy/glitchy
                                  # live sample can't produce an absurd forecast for a
                                  # ride hours from now.
DEFAULT_WAIT_MIN = 30            # fallback if a ride has zero usable history
DEFAULT_WALK_MIN = 10            # fallback if a ride pair has no walk_times row
DEFAULT_RIDE_DURATION_MIN = 3    # fallback if a ride has no ride_duration row
BRUTE_FORCE_LIMIT = 8            # exact solve (permutations) up to this many stops
PARK_CLOSE_HOUR = 21             # 9:00 PM -- change if your park's hours differ
ENTRANCE_DB_ID = 0               # matches the "id" of the entrance row in `rides`
POST_BREAK_BUFFER_MIN = 2        # time to get moving again after a break ends,
                                  # added once before walking to the next ride
PARK_TIMEZONE = ZoneInfo("America/New_York")  # Universal Orlando is Eastern time

# ── ride "importance" tiers ─────────────────────────────────────────
# Baseline popularity weight for each ride, used by `_fill_until_close`
# (the "keep cycling until close" phase) so marquee attractions naturally
# get more of the repeat visits than a low-key ride, even when neither
# was explicitly spun up on the sidebar. This is multiplied together
# with the guest's own sidebar count (see `compute_and_print_route`), so
# a manually counted-up/locked ride still gets extra weight on top of
# its tier -- this table only sets the *default* split when everything
# is left at a plain single check.
#
# Any ride key not listed here (or an unrecognized key) falls back to
# the baseline weight of 1.0 via the .get(..., 1.0) calls below.
RIDE_PRIORITY_WEIGHT = {
    # Tier 1 -- headliners
    "velociCoaster": 3.0,
    "hulk":           3.0,
    "hagrid":         3.0,
    # Tier 2
    "spiderMan":      2.0,
    "harryPotter":    2.0,
    "riverAdventure": 2.0,
    # Tier 3
    "skullIsland":    1.5,
    "stormForce":     1.5,
    "doctorDoom":     1.5,
    "hippogriff":     1.5,
    # everything else (bilgeRat, ripsawFalls, hogwartsTrain, drSeussAirRide,
    # caroSeussel, oneFishtwoFish, catInTheHat, ...) uses the 1.0 baseline.
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
    """Parse a Supabase timestamp into a NAIVE datetime in the park's local
    timezone. `ride_waits.timestamp` is `timestamptz`, so Supabase hands back
    a UTC-aware value -- if we don't convert it, every hour-of-day / weekday
    comparison elsewhere in this file ends up comparing UTC hours against
    local-time hours (start_time, closing_time, etc. are all naive local
    times), silently shifting every prediction by several hours."""
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
    """Return {(start_db_id, end_db_id): minutes}.

    NOTE: `actually_checked` is deliberately ignored here -- it's a
    bookkeeping flag for manual verification only and has no bearing on
    whether the algorithm should trust/use a row. What DOES matter is
    whether `walk_time` itself is null: a row can exist for a ride pair
    before its walk time has been measured, and Supabase will happily
    hand back `walk_time: None` for it. If we stored that None as-is,
    `_walk_time()`'s `if (a, b) in walk_map` check would find the key
    present and return None instead of falling through to
    DEFAULT_WALK_MIN, which is what caused the
    `TypeError: unsupported operand type(s) for +: 'NoneType' and 'float'`
    crash. So: skip rows with a null walk_time and let those pairs use
    the default instead.
    """
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
            continue  # no measured walk time yet -- fall back to DEFAULT_WALK_MIN
        walk[(row["start_ride_ID"], row["end_ride_ID"])] = wt
    return walk


def _load_ride_durations():
    """Return {db_id: duration_minutes} from the `ride_duration` table.
    Assumes ride_duration.id lines up 1:1 with rides.id."""
    resp = _get_client().table("ride_duration").select("id, duration").execute()
    return {row["id"]: row["duration"] for row in resp.data}


def _walk_time(walk_map, a_db_id, b_db_id):
    if a_db_id == b_db_id:
        return 0
    if (a_db_id, b_db_id) in walk_map:
        return walk_map[(a_db_id, b_db_id)]
    if (b_db_id, a_db_id) in walk_map:
        return walk_map[(b_db_id, a_db_id)]
    return DEFAULT_WALK_MIN  # no data between this pair -- assume a modest default


# ── prediction ───────────────────────────────────────────────────────
def _historical_wait_curve(history_for_ride, target_time):
    """
    Kernel-weighted historical average wait at this time-of-day, weighted by:
      - how close the sample's time-of-day is to target_time (Gaussian kernel,
        wrapped across midnight)
      - whether the sample falls on the same weekday, the same weekend/weekday
        group, or neither
      - how recent the sample is (older data counts less, since crowd levels
        and ride popularity drift over time)

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
        # Nothing matched the time-of-day kernel well enough to trust it --
        # fall back to a straight recency-weighted average across ALL of this
        # ride's history (instead of an unweighted average), so a reading
        # from a year ago still doesn't count the same as one from last week.
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
    between `now` and `target_time`. Wait times are bounded at zero and scale
    with crowd level (a ride that's running 2x its historical average right
    now is more likely to still be running ~2x than to be running a flat
    fixed number of minutes higher later on) -- so the anchor blends by
    RATIO rather than by a flat additive offset. That keeps near-term
    forecasts consistent with what's actually happening at the park right
    now, without the additive version either overshooting on unusually busy
    readings or getting clamped to zero on unusually quiet ones.

    The ratio itself is only trusted when the historical baseline at `now`
    is above MIN_MEANINGFUL_BASELINE_MIN, and even then it's clamped to
    [ANCHOR_RATIO_MIN, ANCHOR_RATIO_MAX]. Without that clamp, a ride that's
    historically a near-walk-on at this hour (say a 0.5-min historical
    baseline) combined with even a modest live reading (say 10 min, maybe
    just noise or a temporary stoppage) would produce a 20x ratio that then
    gets multiplied into every other time slot's historical curve for this
    ride -- turning one noisy live sample into a wildly overinflated
    forecast hours out. The clamp keeps the live anchor influential without
    letting it run away.

    As `target_time` moves further from `now`, we fade out from the anchor
    and blend toward the plain historical time-of-day curve, since "today is
    running at N times the historical average" is a much safer bet for the
    next hour than it is for six hours from now.

    `historical_now`, if provided, should be `_historical_wait_curve(history,
    now)` precomputed once by the caller -- it's the same value on every call
    within a single route computation, so callers should compute it once per
    ride rather than paying for it on every permutation/insertion attempt.
    """
    historical_target = _historical_wait_curve(history_for_ride, target_time)

    if current_wait is None or now is None:
        return historical_target if historical_target is not None else DEFAULT_WAIT_MIN

    if historical_target is None:
        # no history to compare against -- the live reading is our best guess
        return max(0.0, float(current_wait))

    if historical_now is None:
        historical_now = _historical_wait_curve(history_for_ride, now)
    if historical_now is None:
        return max(0.0, float(current_wait))

    hours_ahead = max(0.0, (target_time - now).total_seconds() / 3600.0)
    anchor_weight = math.exp(-hours_ahead / ANCHOR_DECAY_HOURS)

    if historical_now > MIN_MEANINGFUL_BASELINE_MIN:
        # scale the target's historical baseline by how much busier/quieter
        # today is running right now, relative to its own historical norm --
        # clamped so a single live reading can't distort the whole curve
        ratio = current_wait / historical_now
        ratio = max(ANCHOR_RATIO_MIN, min(ANCHOR_RATIO_MAX, ratio))
        anchor_adjusted = historical_target * ratio
    else:
        # no meaningful historical baseline to form a ratio against (e.g.
        # this ride is historically a walk-on at this hour) -- an additive
        # shift is the best we can do here, and it's safe since it's small
        anchor_adjusted = current_wait + historical_target

    predicted = anchor_weight * anchor_adjusted + (1 - anchor_weight) * historical_target

    return max(0.0, predicted)


# ── breaks ──────────────────────────────────────────────────────────
def _resolve_break_windows(breaks, base_date):
    """`breaks` is a list of (start_total_minutes, end_total_minutes) pairs
    (minutes since midnight, e.g. from data._to_ampm()). Returns a list of
    (start_dt, end_dt) datetimes anchored to `base_date`."""
    windows = []
    midnight = datetime.combine(base_date, datetime.min.time())
    for start_min, end_min in breaks or []:
        windows.append((midnight + timedelta(minutes=start_min), midnight + timedelta(minutes=end_min)))
    return windows


def _apply_breaks(clock, break_windows):
    """Push `clock` forward past any break window it currently falls inside.
    You can't walk into a queue during a break -- the plan just waits until
    the break ends. Loops so back-to-back/overlapping breaks all get cleared
    in one call. If the clock was moved by any break, a one-time
    POST_BREAK_BUFFER_MIN buffer is added on top (time to actually get
    moving again) before this function returns -- callers should apply this
    BEFORE adding walk time, so the buffer + walk both land after the break
    ends instead of the walk being "used up" while still on break."""
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
    """Walk `order` (list of db_ids) starting at start_time from
    `start_db_id` (the entrance, or whichever ride the user picked to
    start from). Time-dependent: each ride's predicted wait uses the
    clock as it stands when you'd arrive, and breaks/ride duration are
    both factored into how the clock moves.

    `current_waits` (db_id -> today's live wait) and `historical_now_by_id`
    (db_id -> precomputed historical curve at start_time) let each ride's
    prediction anchor to today's actual conditions -- see `_predict_wait`.
    Both are optional; omitting them falls back to the plain historical
    time-of-day curve.

    Break handling order matters: for each stop, we resolve any break
    (jump to break-end + buffer) BEFORE adding the walk to that stop.
    That way a break ending at 8:00 PM with a 2-min buffer and a 4-min
    walk correctly puts queue_join_clock at 8:06 PM, not 8:00 PM."""
    current_waits = current_waits or {}
    historical_now_by_id = historical_now_by_id or {}

    clock = start_time
    total = 0.0
    details = []
    prev = start_db_id
    for db_id in order:
        clock = _apply_breaks(clock, break_windows)  # resolve break + buffer first

        wt = _walk_time(walk_map, prev, db_id) if prev is not None else 0
        if wt:
            clock += timedelta(minutes=wt)
            total += wt

        queue_join_clock = clock  # moment you'd actually get in line
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
    Primary objective: maximize how many rides you actually get in line for
    before the park closes. Secondary objective (tiebreaker among routes
    that get the same number of rides in): minimize the time spent on just
    those committed rides (NOT the full order) -- since stops after the
    first one that misses closing are irrelevant, and including them in the
    tiebreak total would wash out any incentive to prefer a cheaper-wait
    ride within the committed set.
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
        return fits_a > fits_b          # more rides completed before closing wins
    return total_a < total_b - 1e-6      # tiebreak: less total time wins


def _solve_order(db_ids, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                  current_waits=None, historical_now_by_id=None):
    """Find the best visiting order for the given (possibly-repeated) list
    of db_ids. Exact brute force for small lists, nearest-neighbor + 2-opt
    (both starting from the real start point) for larger ones."""
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
            if perm in seen:  # dedupe identical perms when db_ids has repeats
                continue
            seen.add(perm)
            fits, total, details = _route_score(list(perm), histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id,
                                                  current_waits=current_waits, historical_now_by_id=historical_now_by_id)
            if _better((fits, total), best_score):
                best_order, best_score, best_details = list(perm), (fits, total), details
        return best_order, best_score[1], best_details

    # Heuristic for larger selections: nearest-neighbor construction from
    # the real starting point, then 2-opt improvement using the
    # closing-time-aware score.
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
    Try to schedule every item in `forced_items` (each a dict with db_id/
    ride_key/kind, kind being "locked" or "extra"). If they don't all fit
    before closing, drop the lowest-priority ones -- EXTRA (counted-up)
    visits first, then LOCKED base visits -- and retry, until whatever's
    left does fit (or nothing's left).

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


# ── optional-visit insertion (cheapest insertion) ─────────────────────
def _insert_optional(base_order, optional_items, histories, walk_map, durations,
                      start_time, closing_time, break_windows, start_db_id,
                      current_waits=None, historical_now_by_id=None):
    """
    Greedily inserts optional (unlocked, single-count) rides into the
    already-fixed forced schedule, one at a time, always taking whichever
    remaining ride + position adds the least time -- and only if the
    insertion doesn't push any forced item (or itself) past closing.
    """
    order = list(base_order)
    included, remaining = [], list(optional_items)
    must_fit = len(order)  # every stop currently in `order` has to keep fitting

    changed = True
    while remaining and changed:
        changed = False
        best = None  # (added_time, candidate_order, item)
        for item in remaining:
            for pos in range(len(order) + 1):
                candidate = order[:pos] + [item["db_id"]] + order[pos:]
                _, details = _simulate_route(candidate, histories, walk_map, durations, start_time, break_windows, start_db_id,
                                              current_waits=current_waits, historical_now_by_id=historical_now_by_id)
                fits = sum(1 for d in details if d["queue_join_clock"] <= closing_time)
                if fits < must_fit + 1:
                    continue  # would bump something (or itself) past closing
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


# ── fill remaining daylight (re-ride until close, keeping variety) ────
def _fill_until_close(order, candidate_ids, weights, histories, walk_map, durations,
                       start_time, closing_time, break_windows, start_db_id,
                       current_waits=None, historical_now_by_id=None):
    """
    Keeps the plan going after every locked/counted/optional ride has
    already been scheduled once. Rather than stopping the instant the
    guest's checked list is exhausted, this treats every originally
    selected ride as re-ridable and keeps appending more visits for as
    long as there's still time to queue before `closing_time`. This is
    what makes the route span the whole park day instead of finishing
    hours early whenever the guest only checked a handful of rides.

    IMPORTANT: this does NOT just keep grabbing whichever ride is
    cheapest right now -- that degenerates into repeating one short
    ride over and over. Instead it's a weighted round-robin: `weights`
    is {db_id: effective_weight}, combining the sidebar's requested
    count (1 for a normal check, 2+ for a ride the guest marked up)
    with that ride's baseline popularity tier (see
    RIDE_PRIORITY_WEIGHT) -- so a headliner like hulk/velociCoaster/
    hagrid naturally gets more of the "extra" visits than a low-key
    ride even at a plain single check, and a ride the guest also spun
    up on top of that gets weighted higher still.

    At each step we pick whichever candidate is currently most "behind"
    its fair share -- i.e. the smallest (visits_so_far / weight) -- so
    every checked ride keeps cycling through. Ties on that ratio are
    broken by *recency*: whichever tied candidate has gone the longest
    without a turn goes first. This is the fix for a real bug where the
    old version broke ties by "whichever has the lowest predicted wait
    wins" -- since that value never changes over the course of a single
    route computation, the same one or two cheap/nearby rides would win
    every tie forever and permanently starve out the rest of the
    selection, especially visible with a small handful of checked
    rides. Predicted wait is now only a final tiebreaker, after weight
    ratio and recency, purely to keep otherwise-equal choices efficient.

    Only appends to the END of `order` -- the forced/optional portion in
    front of it has already been optimized and shouldn't be reshuffled,
    it just keeps building forward in time from wherever that left off.

    Returns the extended order (a new list; `order` itself isn't mutated).
    """
    order = list(order)
    if not candidate_ids:
        return order

    # start each ride's tally from however many times it's already in the
    # plan (forced/optional visits count toward its fair share too)
    visit_counts = {db_id: 0 for db_id in candidate_ids}
    for db_id in order:
        if db_id in visit_counts:
            visit_counts[db_id] += 1

    # tracks the "step number" each ride was last placed at, so ties on the
    # weight ratio go to whichever ride has been waiting longest for another
    # turn instead of always favoring the same low-wait ride. Rides not yet
    # visited default to -1 so they outrank anything that's already had a
    # turn.
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
            candidate = order + [db_id]
            _, cand_details = _simulate_route(
                candidate, histories, walk_map, durations, start_time, break_windows, start_db_id,
                current_waits=current_waits, historical_now_by_id=historical_now_by_id
            )
            last = cand_details[-1]
            if last["queue_join_clock"] > closing_time:
                continue  # can't get in line for this one before closing -- try the next-most-owed candidate
            order.append(db_id)
            visit_counts[db_id] += 1
            last_visit_step[db_id] = step
            step += 1
            placed = True
            break

        if not placed:
            break  # nothing left that can still be queued for today

    return order

def get_historical_average(ride_key, at_time=None):
    """
    Returns the kernel-weighted historical average wait (minutes) for
    `ride_key` at `at_time` (defaults to now, in the park's local
    timezone), or None if it can't be determined (unknown ride key,
    Supabase unreachable, or no history at all for this ride).

    This is a lightweight, read-only helper meant for the FRONTEND to
    compare a live wait reading against "the average wait this ride
    usually has at this time of day" -- e.g. to color-code the wait-time
    popup. It reuses the same time-of-day/day-of-week/recency weighted
    curve the route optimizer itself uses (_historical_wait_curve), but
    does none of the route-planning work, so it's safe/cheap to call on
    a simple ride-icon click.

    Because it hits Supabase, callers on a UI thread (e.g. pygame) should
    call this from a background thread rather than the main loop, to
    avoid blocking on network latency.
    """
    if at_time is None:
        at_time = datetime.now(PARK_TIMEZONE).replace(tzinfo=None)
    elif at_time.tzinfo is not None:
        at_time = at_time.astimezone(PARK_TIMEZONE).replace(tzinfo=None)

    try:
        key_to_id, _ = _load_ride_id_map()
    except Exception as e:
        print(f"get_historical_average: could not reach Supabase: {e}")
        return None

    db_id = key_to_id.get(ride_key)
    if db_id is None:
        return None

    try:
        history = _load_wait_history([db_id]).get(db_id, [])
    except Exception as e:
        print(f"get_historical_average: could not load wait history: {e}")
        return None

    return _historical_wait_curve(history, at_time)

# ── public entry point ──────────────────────────────────────────────
def compute_and_print_route(ride_counts, ride_locked=None, closed_ride_keys=None,
                             breaks=None, start_time=None, start_key="entrance",
                             live_waits=None):
    """
    ride_counts:      {ride_key: count} for every CHECKED ride. Anything
                       with count 0 (or missing) is treated as unchecked.
    ride_locked:      {ride_key: bool} -- locked rides are force-included
                       at their best slot even if they aren't the "best"
                       pick overall.
    closed_ride_keys: iterable of ride_keys that are currently closed --
                       dropped entirely, regardless of lock/count. This
                       should come from the live API's own `is_open` flag
                       (see Data.ride_open), NOT from a 0-min wait -- a
                       0-min wait is a legitimate walk-on, not a closure.
    breaks:           list of (start_total_minutes, end_total_minutes)
                       pairs (minutes since midnight), one per break the
                       user generated on the sidebar.
    start_time:       datetime to start the route from (defaults to now,
                       in the park's local timezone -- see PARK_TIMEZONE).
    start_key:        ride_key (or "entrance") the route starts from --
                       matches the sidebar's starting-location dropdown.
    live_waits:       {ride_key: current_wait_minutes} -- today's live
                       readings (e.g. `Data.ride_waits`), ideally a
                       snapshot taken at click time. When provided, each
                       ride's predicted wait anchors to its live reading
                       and decays toward the historical time-of-day curve
                       the further out the prediction reaches (with the
                       ratio clamped -- see _predict_wait). Omit to fall
                       back to pure historical time-of-day predictions.
                       Rides already excluded via closed_ride_keys never
                       have their live_waits entry used, since a closed
                       ride's reported wait doesn't reflect a real queue.

    Returns:
        A list of ride_key strings, in visiting order, for the rides that
        actually fit before closing (i.e. the "committed" plan -- what
        used to only get printed as numbered lines 1., 2., 3., ...).
        Returns [] if nothing fits or nothing valid was selected/found.
        Returns None only when the computation couldn't run at all (e.g.
        Supabase was unreachable) -- callers should treat None as "no
        change" rather than "empty route".
    """
    ride_locked = ride_locked or {}
    closed_ride_keys = set(closed_ride_keys or [])
    breaks = breaks or []

    if start_time is None:
        # Anchor "now" to the park's local timezone, not whatever timezone
        # the machine running this script happens to be set to -- every
        # historical timestamp is normalized to PARK_TIMEZONE in _parse_ts,
        # so start_time needs to match or every time-of-day comparison
        # (and therefore every prediction) silently shifts by however many
        # hours the two clocks are apart.
        start_time = datetime.now(PARK_TIMEZONE).replace(tzinfo=None)
    elif start_time.tzinfo is not None:
        start_time = start_time.astimezone(PARK_TIMEZONE).replace(tzinfo=None)

    checked = {k: c for k, c in ride_counts.items() if c and c > 0}
    if not checked:
        print("\nNo rides selected -- check some boxes on the sidebar first.\n")
        return []

    # rule 1: closed rides are dropped completely, no exceptions
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
        print(f"Warning: couldn't load ride_duration table ({e}); using a "
              f"{DEFAULT_RIDE_DURATION_MIN}-min default for every ride.")
        durations = {}

    # live-anchored prediction setup: map today's live readings onto db_ids,
    # and precompute each ride's historical curve at start_time ONCE so we
    # don't redo that O(history) work on every permutation/insertion attempt.
    # Only rides that survived the closed-ride filter above can have a
    # live_waits entry used -- a closed ride's last reported wait isn't a
    # real queue reading and shouldn't anchor anything.
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

    closing_time = start_time.replace(hour=PARK_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if closing_time <= start_time:
        print(f"\nHeads up: it's already past {closing_time.strftime('%I:%M %p')} closing time.\n")

    # rule 2: split into forced (locked base + counted-up extras) vs optional
    locked_instances, extra_instances, optional_instances = [], [], []
    for key, count in checked.items():
        db_id = key_to_id[key]
        is_locked = bool(ride_locked.get(key))
        if is_locked:
            locked_instances.append({"db_id": db_id, "ride_key": key, "kind": "locked"})
        else:
            optional_instances.append({"db_id": db_id, "ride_key": key, "kind": "optional"})
        for _ in range(count - 1):
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

    # rule 6: don't stop just because every checked/locked/counted ride has
    # been scheduled once -- keep cycling back through every selected ride
    # so the plan runs all the way to park close instead of quitting early
    # whenever there's still daylight left. Each ride's effective weight
    # combines its sidebar count (a ride the guest marked up, e.g. hulk: 2,
    # keeps getting picked roughly twice as often) with its baseline
    # popularity tier (RIDE_PRIORITY_WEIGHT), so headliners get more of the
    # "extra" visits by default too -- without ever starving out the rest
    # of the checked list (see the recency tiebreak in _fill_until_close).
    fill_weights = {
        key_to_id[k]: count * RIDE_PRIORITY_WEIGHT.get(k, 1.0)
        for k, count in checked.items()
    }
    final_order = _fill_until_close(
        final_order, all_db_ids, fill_weights, histories, walk_map, durations,
        start_time, closing_time, break_windows, start_db_id,
        current_waits=current_waits, historical_now_by_id=historical_now_by_id
    )

    _, details = _simulate_route(final_order, histories, walk_map, durations, start_time, break_windows, start_db_id,
                                  current_waits=current_waits, historical_now_by_id=historical_now_by_id)

    # Because the clock only moves forward, once a stop fails to fit before
    # closing, every stop after it fails too -- so the "committed" plan is
    # just the leading run of stops that fit.
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

    # Return the committed order as plain ride_key strings so the frontend
    # can render it (e.g. in the top route bar), without needing to know
    # anything about db_ids.
    return [
        (id_to_key.get(d["db_id"], str(d["db_id"])), d["predicted_wait"])
        for d in committed
    ]

if __name__ == "__main__":
    # quick manual test -- edit below to try it out
    result = compute_and_print_route(
        ride_counts={"hulk": 2, "spiderMan": 1, "doctorDoom": 1, "stormForce": 1},
        ride_locked={"spiderMan": True},
        closed_ride_keys={"riverAdventure"},
        breaks=[(12 * 60, 13 * 60)],  # 12:00 PM - 1:00 PM
        live_waits={"hulk": 45, "spiderMan": 20, "doctorDoom": 15, "stormForce": 5},
    )
    print("Returned route:", result)