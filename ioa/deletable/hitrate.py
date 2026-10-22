# hitrate.py -- run with:  python hitrate.py
import os
import bisect
from statistics import mean, median
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro

TEST_DAYS = 14
NOW_HOURS = [10, 11, 12, 13, 14, 15, 16, 17]
HORIZONS_MIN = [15, 30, 60, 120, 180, 240]
MAX_GAP_MIN = 10

LONG_WAIT_MIN = 60     # actual wait at/above this gets the wider tolerance
TOL_SHORT = 5
TOL_LONG = 10


def tol(actual):
    return TOL_LONG if actual >= LONG_WAIT_MIN else TOL_SHORT


def nearest(times, waits, when):
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def pct(hits):
    return f"{100 * sum(hits) / len(hits):5.1f}%" if hits else "   n/a"


def main():
    key_to_id, id_to_key = ro._load_ride_id_map()
    ids = [i for i in key_to_id.values() if i != ro.ENTRANCE_DB_ID]
    print("Loading history...")
    history = ro._load_wait_history(ids)

    rides = {}
    for db_id in ids:
        full = sorted(history.get(db_id, []))
        if len(full) >= 500:
            rides[db_id] = (full, [t for t, _ in full], [w for _, w in full])

    today = datetime.now(ro.PARK_TIMEZONE).date()
    days = [today - timedelta(days=d) for d in range(1, TEST_DAYS + 1)]
    rows = []   # (horizon, db_id, actual, stay, old, new)

    for day in days:
        ro._ctx.bins = {}
        midnight = datetime.combine(day, datetime.min.time())
        prevs = {}
        for db_id, (full, _, _) in rides.items():
            p = [(t, w) for t, w in full if t.date() < day]
            if len(p) >= 500:
                prevs[db_id] = p
        for hour in NOW_HOURS:
            now = midnight + timedelta(hours=hour)
            snap = {}
            for db_id, p in prevs.items():
                _, times, waits = rides[db_id]
                live = nearest(times, waits, now)
                if live is None:
                    continue
                snap[db_id] = (live, ro._historical_wait_curve(p, now))

            # same park-wide ratio the production code computes
            num = den = 0.0
            used = 0
            for live, hn in snap.values():
                if hn is not None and hn > ro.MIN_MEANINGFUL_BASELINE_MIN:
                    num += live
                    den += hn
                    used += 1
            park_ratio = None
            if used >= ro.CROWD_MIN_RIDES and den > 0:
                park_ratio = max(ro.CROWD_RATIO_MIN, min(ro.CROWD_RATIO_MAX, num / den))

            for db_id, (live, hn) in snap.items():
                _, times, waits = rides[db_id]
                p = prevs[db_id]
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is None:
                        continue
                    old = ro._predict_wait(p, target, current_wait=live, now=now, historical_now=hn)
                    new = ro._predict_wait(p, target, current_wait=live, now=now, historical_now=hn,
                                           park_ratio=park_ratio)
                    rows.append((h, db_id, actual, live, old, new))
        print(f"  done {day}", flush=True)

    print(f"\nHit = within {TOL_SHORT} min (or {TOL_LONG} min if the actual wait is {LONG_WAIT_MIN}+)")
    print(f"{'ahead':>6} {'n':>6} {'stay':>7} {'old':>7} {'NEW':>7} {'NEW median err':>15}")
    for h in HORIZONS_MIN:
        r = [x for x in rows if x[0] == h]
        if not r:
            continue
        print(f"{h:>5}m {len(r):>6} "
              f"{pct([abs(x[3] - x[2]) <= tol(x[2]) for x in r]):>7} "
              f"{pct([abs(x[4] - x[2]) <= tol(x[2]) for x in r]):>7} "
              f"{pct([abs(x[5] - x[2]) <= tol(x[2]) for x in r]):>7} "
              f"{median(abs(x[5] - x[2]) for x in r):>15.1f}")
    allr = rows
    print(f"{'ALL':>6} {len(allr):>6} "
          f"{pct([abs(x[3] - x[2]) <= tol(x[2]) for x in allr]):>7} "
          f"{pct([abs(x[4] - x[2]) <= tol(x[2]) for x in allr]):>7} "
          f"{pct([abs(x[5] - x[2]) <= tol(x[2]) for x in allr]):>7} "
          f"{median(abs(x[5] - x[2]) for x in allr):>15.1f}")

    print("\nBy ride (NEW, all horizons):")
    print(f"{'ride':<18} {'n':>6} {'hit':>7} {'avg actual':>11}")
    by_ride = defaultdict(list)
    for x in rows:
        by_ride[x[1]].append(x)
    for db_id, r in sorted(by_ride.items(), key=lambda kv: sum(abs(x[5] - x[2]) <= tol(x[2]) for x in kv[1]) / len(kv[1])):
        print(f"{id_to_key.get(db_id, db_id):<18} {len(r):>6} "
              f"{pct([abs(x[5] - x[2]) <= tol(x[2]) for x in r]):>7} {mean(x[2] for x in r):>11.1f}")

    print("\nBy actual wait size (NEW):")
    for label, lo, hi in (("under 15", 0, 15), ("15-59", 15, 60), ("60+", 60, 10**6)):
        r = [x for x in rows if lo <= x[2] < hi]
        print(f"  {label:<9} n={len(r):>5}  hit {pct([abs(x[5] - x[2]) <= tol(x[2]) for x in r])}")


if __name__ == "__main__":
    main()