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

Call `compute_and_print_route(...)` from a button press on the
frontend. Results print to the terminal.

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
DIFF_DAY_WEIGHT = 0.35           # weight for samples on other weekdays
DEFAULT_WAIT_MIN = 30            # fallback if a ride has zero usable history
DEFAULT_WALK_MIN = 10            # fallback if a ride pair has no walk_times row
DEFAULT_RIDE_DURATION_MIN = 3    # fallback if a ride has no ride_duration row
BRUTE_FORCE_LIMIT = 8            # exact solve (permutations) up to this many stops
PARK_CLOSE_HOUR = 21             # 9:00 PM -- change if your park's hours differ
ENTRANCE_DB_ID = 0               # matches the "id" of the entrance row in `rides`
POST_BREAK_BUFFER_MIN = 2        # time to get moving again after a break ends,
                                  # added once before walking to the next ride


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
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


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
        walk[(row["start_ride_ID"], row["end_ride_ID"])] = row["walk_time"]
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
def _predict_wait(history_for_ride, target_time):
    """
    Weighted average of historical wait times at `target_time`, favoring
    samples from the same weekday and a similar time-of-day (Gaussian
    kernel on minutes-since-midnight, wrapped across midnight).
    """
    if not history_for_ride:
        return DEFAULT_WAIT_MIN

    target_minutes = target_time.hour * 60 + target_time.minute
    target_weekday = target_time.weekday()

    weighted_sum, weight_total = 0.0, 0.0
    for ts, wait in history_for_ride:
        sample_minutes = ts.hour * 60 + ts.minute
        raw_delta = abs(sample_minutes - target_minutes)
        delta = min(raw_delta, 1440 - raw_delta)
        time_kernel = math.exp(-(delta ** 2) / (2 * TIME_KERNEL_BANDWIDTH_MIN ** 2))
        day_weight = SAME_DAY_WEIGHT if ts.weekday() == target_weekday else DIFF_DAY_WEIGHT
        w = time_kernel * day_weight
        weighted_sum += w * wait
        weight_total += w

    if weight_total < 1e-6:
        return sum(w for _, w in history_for_ride) / len(history_for_ride)

    return weighted_sum / weight_total


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
def _simulate_route(order, histories, walk_map, durations, start_time, break_windows, start_db_id):
    """Walk `order` (list of db_ids) starting at start_time from
    `start_db_id` (the entrance, or whichever ride the user picked to
    start from). Time-dependent: each ride's predicted wait uses the
    clock as it stands when you'd arrive, and breaks/ride duration are
    both factored into how the clock moves.

    Break handling order matters: for each stop, we resolve any break
    (jump to break-end + buffer) BEFORE adding the walk to that stop.
    That way a break ending at 8:00 PM with a 2-min buffer and a 4-min
    walk correctly puts queue_join_clock at 8:06 PM, not 8:00 PM."""
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
        predicted_wait = _predict_wait(histories.get(db_id, []), clock)
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


def _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id):
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
    _, details = _simulate_route(order, histories, walk_map, durations, start_time, break_windows, start_db_id)
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


def _solve_order(db_ids, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id):
    """Find the best visiting order for the given (possibly-repeated) list
    of db_ids. Exact brute force for small lists, nearest-neighbor + 2-opt
    (both starting from the real start point) for larger ones."""
    if len(db_ids) == 0:
        return [], 0.0, []

    if len(db_ids) == 1:
        order = list(db_ids)
        _, total, details = _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id)
        return order, total, details

    if len(db_ids) <= BRUTE_FORCE_LIMIT:
        best_order, best_details = None, None
        best_score = (-1, math.inf)
        seen = set()
        for perm in itertools.permutations(db_ids):
            if perm in seen:  # dedupe identical perms when db_ids has repeats
                continue
            seen.add(perm)
            fits, total, details = _route_score(list(perm), histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id)
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

    fits, total, details = _route_score(order, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id)
    score = (fits, total)

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                cand_fits, cand_total, cand_details = _route_score(
                    candidate, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id
                )
                if _better((cand_fits, cand_total), score):
                    order, score, details = candidate, (cand_fits, cand_total), cand_details
                    improved = True
    return order, score[1], details


# ── forced (locked + counted-up) scheduling ───────────────────────────
def _fit_forced(forced_items, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id):
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
            ids, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id
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
                      start_time, closing_time, break_windows, start_db_id):
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
                _, details = _simulate_route(candidate, histories, walk_map, durations, start_time, break_windows, start_db_id)
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


# ── public entry point ──────────────────────────────────────────────
def compute_and_print_route(ride_counts, ride_locked=None, closed_ride_keys=None,
                             breaks=None, start_time=None, start_key="entrance"):
    """
    ride_counts:      {ride_key: count} for every CHECKED ride. Anything
                       with count 0 (or missing) is treated as unchecked.
    ride_locked:      {ride_key: bool} -- locked rides are force-included
                       at their best slot even if they aren't the "best"
                       pick overall.
    closed_ride_keys: iterable of ride_keys that are currently closed --
                       dropped entirely, regardless of lock/count.
    breaks:           list of (start_total_minutes, end_total_minutes)
                       pairs (minutes since midnight), one per break the
                       user generated on the sidebar.
    start_time:       datetime to start the route from (defaults to now).
    start_key:        ride_key (or "entrance") the route starts from --
                       matches the sidebar's starting-location dropdown.
    """
    ride_locked = ride_locked or {}
    closed_ride_keys = set(closed_ride_keys or [])
    breaks = breaks or []

    if start_time is None:
        start_time = datetime.now()

    checked = {k: c for k, c in ride_counts.items() if c and c > 0}
    if not checked:
        print("\nNo rides selected -- check some boxes on the sidebar first.\n")
        return

    # rule 1: closed rides are dropped completely, no exceptions
    ignored_closed = sorted(k for k in checked if k in closed_ride_keys)
    checked = {k: c for k, c in checked.items() if k not in closed_ride_keys}
    if ignored_closed:
        print(f"Skipping currently-closed rides: {ignored_closed}")
    if not checked:
        print("\nEverything selected is currently closed.\n")
        return

    try:
        key_to_id, id_to_key = _load_ride_id_map()
    except Exception as e:
        print(f"\nCould not reach Supabase: {e}\n")
        return

    unknown = [k for k in checked if k not in key_to_id]
    if unknown:
        print(f"Warning: no DB entry found for rides {unknown} -- skipping them.")
    checked = {k: c for k, c in checked.items() if k in key_to_id}
    if not checked:
        print("\nNone of the selected rides were found in the database.\n")
        return

    all_db_ids = [key_to_id[k] for k in checked]
    histories = _load_wait_history(all_db_ids)
    walk_map = _load_walk_times()
    try:
        durations = _load_ride_durations()
    except Exception as e:
        print(f"Warning: couldn't load ride_duration table ({e}); using a "
              f"{DEFAULT_RIDE_DURATION_MIN}-min default for every ride.")
        durations = {}

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
        forced_pool, histories, walk_map, durations, start_time, closing_time, break_windows, start_db_id
    )

    final_order, included_optional, skipped_optional = _insert_optional(
        forced_order, optional_instances, histories, walk_map, durations,
        start_time, closing_time, break_windows, start_db_id
    )

    _, details = _simulate_route(final_order, histories, walk_map, durations, start_time, break_windows, start_db_id)

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


if __name__ == "__main__":
    # quick manual test -- edit below to try it out
    compute_and_print_route(
        ride_counts={"hulk": 2, "spiderMan": 1, "doctorDoom": 1, "stormForce": 1},
        ride_locked={"spiderMan": True},
        closed_ride_keys={"riverAdventure"},
        breaks=[(12 * 60, 13 * 60)],  # 12:00 PM - 1:00 PM
    )