# tune.py -- run with:  python tune.py
import os
import bisect
import itertools
from statistics import mean
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro

TEST_DAYS = 14
SPLIT = 7                      # newest 7 days = validation, older 7 = used to pick settings
NOW_HOURS = [10, 11, 12, 13, 14, 15, 16, 17]
HORIZONS_MIN = [15, 30, 60, 120, 180, 240]
MAX_GAP_MIN = 10

MODES = ["ratio", "add"]
DECAYS = [1.5, 3.0, 6.0, 12.0]
BANDWIDTHS = [30, 45, 75]
HALF_LIVES = [14, 30, 45, 90]
CURRENT = ("ratio", 3.0, 45, 45)


def nearest(times, waits, when):
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def build_groups():
    key_to_id, _ = ro._load_ride_id_map()
    ids = [i for i in key_to_id.values() if i != ro.ENTRANCE_DB_ID]
    print("Loading history (can take a minute)...")
    history = ro._load_wait_history(ids)
    today = datetime.now(ro.PARK_TIMEZONE).date()
    groups = []
    for db_id in ids:
        full = sorted(history.get(db_id, []))
        if len(full) < 500:
            continue
        times = [t for t, _ in full]
        waits = [w for _, w in full]
        for idx in range(1, TEST_DAYS + 1):
            day = today - timedelta(days=idx)
            prev = [(t, w) for t, w in full if t.date() < day]
            if len(prev) < 500:
                continue
            midnight = datetime.combine(day, datetime.min.time())
            cases = []
            for hour in NOW_HOURS:
                now = midnight + timedelta(hours=hour)
                live = nearest(times, waits, now)
                if live is None:
                    continue
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is not None:
                        cases.append((now, live, target, h, actual))
            if cases:
                groups.append({"idx": idx, "prev": prev, "cases": cases})
    return groups


def evaluate(groups, mode, decay, bw, half):
    ro.ANCHOR_MODE = mode
    ro.ANCHOR_DECAY_HOURS = decay
    ro.TIME_KERNEL_BANDWIDTH_MIN = bw
    ro.RECENCY_HALF_LIFE_DAYS = half
    errs = {h: [] for h in HORIZONS_MIN}
    signed = []
    for g in groups:
        ro._ctx.bins = {}
        for now, live, target, h, actual in g["cases"]:
            pred = ro._predict_wait(g["prev"], target, current_wait=live, now=now)
            errs[h].append(abs(pred - actual))
            signed.append(pred - actual)
    allerr = [e for v in errs.values() for e in v]
    return mean(allerr), mean(signed), {h: mean(v) for h, v in errs.items() if v}


def persist_mae(groups):
    return mean(abs(live - actual) for g in groups for _, live, _, _, actual in g["cases"])


def main():
    groups = build_groups()
    sel = [g for g in groups if g["idx"] > SPLIT]
    val = [g for g in groups if g["idx"] <= SPLIT]
    print(f"{len(sel)} selection groups, {len(val)} validation groups")

    combos = list(itertools.product(MODES, DECAYS, BANDWIDTHS, HALF_LIVES))
    results = []
    for n, c in enumerate(combos, 1):
        mae, _, _ = evaluate(sel, *c)
        results.append((mae, c))
        print(f"\r{n}/{len(combos)}", end="", flush=True)
    results.sort()

    print("\n\nTop 8 on the selection days (mode, decay_h, bandwidth_min, half_life_days):")
    for mae, c in results[:8]:
        print(f"  {mae:5.2f}  {c}")
    cur_sel = next(m for m, c in results if c == CURRENT)
    print(f"  current settings {CURRENT}: {cur_sel:.2f}")

    best = results[0][1]
    print("\nValidation on the newest 7 days (never used for picking):")
    print(f"  'stays the same' baseline: {persist_mae(val):.2f}")
    for label, c in (("current", CURRENT), ("best", best)):
        mae, bias, per_h = evaluate(val, *c)
        print(f"  {label:<8} {c}: MAE {mae:.2f}, bias {bias:+.2f}")
        print("           " + "  ".join(f"{h}m:{per_h[h]:.1f}" for h in HORIZONS_MIN if h in per_h))


if __name__ == "__main__":
    main()