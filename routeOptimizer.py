"""
route_optimizer.py

Computes the best order to visit a selected set of rides using:
  - Historical wait-time data (Supabase 'wait_times' table) to predict
    future wait times, based on time-of-day / day-of-week patterns.
  - Static walk-time data (Supabase 'walk_times' table) to account for
    travel time between rides.

Call `compute_and_print_route(selected_ride_ids)` -- e.g. from a button
press on the frontend -- with the list of short ride keys that are
currently checked (the same strings used everywhere else in the codebase,
like "hulk", "spiderMan", "hagrid", ...). Results print to the terminal.

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
BRUTE_FORCE_LIMIT = 8            # exact solve (permutations) up to this many rides
PARK_CLOSE_HOUR = 21             # 9:00 PM -- change if your park's hours differ


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


# ── route simulation ─────────────────────────────────────────────────
def _simulate_route(order, histories, walk_map, start_time):
    """Walk `order` (list of db_ids) starting at start_time. Time-dependent:
    each ride's predicted wait uses the clock as it stands when you'd arrive."""
    clock = start_time
    total = 0.0
    details = []
    prev = None
    for db_id in order:
        wt = _walk_time(walk_map, prev, db_id) if prev is not None else 0
        if prev is not None:
            clock += timedelta(minutes=wt)
            total += wt

        queue_join_clock = clock  # moment you'd actually get in line
        predicted_wait = _predict_wait(histories.get(db_id, []), clock)
        clock += timedelta(minutes=predicted_wait)
        total += predicted_wait

        details.append({
            "db_id": db_id,
            "walk_from_prev": wt,
            "predicted_wait": predicted_wait,
            "queue_join_clock": queue_join_clock,
            "arrival_clock": clock,
        })
        prev = db_id

    return total, details


def _route_score(order, histories, walk_map, start_time, closing_time):
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
    _, details = _simulate_route(order, histories, walk_map, start_time)
    fits_count = 0
    committed_total = 0.0
    for d in details:
        if d["queue_join_clock"] <= closing_time:
            fits_count += 1
            committed_total += d["walk_from_prev"] + d["predicted_wait"]
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


def _best_order(db_ids, histories, walk_map, start_time, closing_time):
    if len(db_ids) <= 1:
        order = list(db_ids)
        _, total, details = _route_score(order, histories, walk_map, start_time, closing_time)
        return order, total, details

    if len(db_ids) <= BRUTE_FORCE_LIMIT:
        best_order, best_details = None, None
        best_score = (-1, math.inf)
        for perm in itertools.permutations(db_ids):
            fits, total, details = _route_score(list(perm), histories, walk_map, start_time, closing_time)
            if _better((fits, total), best_score):
                best_order, best_score, best_details = list(perm), (fits, total), details
        return best_order, best_score[1], best_details

    # Heuristic for larger selections: nearest-neighbor construction,
    # then 2-opt improvement using the closing-time-aware score.
    remaining = set(db_ids)
    start = min(remaining)  # deterministic arbitrary start
    order = [start]
    remaining.remove(start)
    while remaining:
        last = order[-1]
        nxt = min(remaining, key=lambda r: _walk_time(walk_map, last, r))
        order.append(nxt)
        remaining.remove(nxt)

    fits, total, details = _route_score(order, histories, walk_map, start_time, closing_time)
    score = (fits, total)

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                cand_fits, cand_total, cand_details = _route_score(
                    candidate, histories, walk_map, start_time, closing_time
                )
                if _better((cand_fits, cand_total), score):
                    order, score, details = candidate, (cand_fits, cand_total), cand_details
                    improved = True
    return order, score[1], details


# ── public entry point ──────────────────────────────────────────────
def compute_and_print_route(selected_ride_ids, start_time=None):
    """
    selected_ride_ids: list of short ride keys currently checked on the
                        frontend, e.g. ["hulk", "spiderMan", "hagrid"]
    start_time:        datetime to start the route from (defaults to now)
    """
    if start_time is None:
        start_time = datetime.now()

    if not selected_ride_ids:
        print("\nNo rides selected -- check some boxes on the sidebar first.\n")
        return

    try:
        key_to_id, id_to_key = _load_ride_id_map()
    except Exception as e:
        print(f"\nCould not reach Supabase: {e}\n")
        return

    db_ids, unknown = [], []
    for key in selected_ride_ids:
        if key in key_to_id:
            db_ids.append(key_to_id[key])
        else:
            unknown.append(key)

    if unknown:
        print(f"Warning: no DB entry found for rides {unknown} -- skipping them.")

    if not db_ids:
        print("\nNone of the selected rides were found in the database.\n")
        return

    histories = _load_wait_history(db_ids)
    walk_map = _load_walk_times()

    closing_time = start_time.replace(hour=PARK_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if closing_time <= start_time:
        # already past closing for "today" -- assume they mean tonight's closing
        # has passed and nothing more fits; still show the plan for reference.
        print(f"\nHeads up: it's already past {closing_time.strftime('%I:%M %p')} closing time.\n")

    order, _, details = _best_order(db_ids, histories, walk_map, start_time, closing_time)

    # Because the clock only moves forward, once a stop fails to fit before
    # closing, every stop after it fails too -- so the "committed" plan is
    # just the leading run of stops that fit.
    committed = []
    for d in details:
        if d["queue_join_clock"] <= closing_time:
            committed.append(d)
        else:
            break
    skipped = details[len(committed):]

    committed_total = sum(d["walk_from_prev"] + d["predicted_wait"] for d in committed)

    print("\n" + "=" * 55)
    print(f"OPTIMAL ROUTE  (starting {start_time.strftime('%A %I:%M %p')}, "
          f"park closes {closing_time.strftime('%I:%M %p')})")
    print("=" * 55)

    if not committed:
        print("None of the selected rides fit before closing from this start time.")
    for i, d in enumerate(committed, start=1):
        name = id_to_key.get(d["db_id"], str(d["db_id"]))
        walk_note = f"  (+{d['walk_from_prev']} min walk)" if d["walk_from_prev"] else ""
        print(
            f"{i}. {name:<16} predicted wait: {d['predicted_wait']:.0f} min"
            f"{walk_note}   -> in line by ~{d['queue_join_clock'].strftime('%I:%M %p')}"
        )

    print("-" * 55)
    print(f"Total estimated time (walking + waiting): {committed_total:.0f} min")
    print(f"Rides that fit before closing: {len(committed)} / {len(details)}")

    if skipped:
        skipped_names = [id_to_key.get(d["db_id"], str(d["db_id"])) for d in skipped]
        print(f"\nWon't fit before closing today ({len(skipped)}): {', '.join(skipped_names)}")
        print("Uncheck a few rides, or start earlier, to fit more of them in.")

    print("=" * 55 + "\n")


if __name__ == "__main__":
    # quick manual test -- edit the list below to try it out
    compute_and_print_route(["hulk", "spiderMan", "doctorDoom", "stormForce"])