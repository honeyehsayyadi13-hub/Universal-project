# crowd_test.py -- run with:  python crowd_test.py
import os
import math
import bisect
import itertools
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
MIN_BASE = 3.0
RATIO_MIN, RATIO_MAX = 0.3, 4.0

MODES = ["sum", "median"]
TAU_OWNS = [1.5, 3.0]
TAU_PARKS = [4.0, 8.0, 16.0, 1e9]


def clamp(x):
    return max(RATIO_MIN, min(RATIO_MAX, x))


def nearest(times, waits, when):
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def park_ratio(rides_snap, mode):
    vals = [(s["live"], s["hn"]) for s in rides_snap.values()
            if s["hn"] is not None and s["hn"] > MIN_BASE]
    if not vals:
        return 1.0
    if mode == "sum":
        return clamp(sum(l for l, _ in vals) / sum(h for _, h in vals))
    return clamp(median([l / h for l, h in vals]))


def build():
    key_to_id, _ = ro._load_ride_id_map()
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
    snaps = []
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
                snap[db_id] = {"live": live, "hn": ro._historical_wait_curve(p, now), "prev": p}
            cases = []
            for db_id, s in snap.items():
                _, times, waits = rides[db_id]
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is None:
                        continue
                    ht = ro._historical_wait_curve(s["prev"], target)
                    if ht is None:
                        continue
                    cur = ro._predict_wait(s["prev"], target, current_wait=s["live"], now=now)
                    cases.append((db_id, h, actual, ht, cur))
            if cases:
                snaps.append({"day": day, "hour": hour, "rides": snap, "cases": cases})
        print(f"  built {day}", flush=True)
    return snaps


def day_groups(snaps):
    out = {}
    for sn in snaps:
        if sn["hour"] == 12:
            r = park_ratio(sn["rides"], "sum")
            out[sn["day"]] = "busy" if r > 1.3 else "quiet" if r < 0.85 else "normal"
    return out


def run(snaps, setting):
    """setting None = current model. Returns rows of (day, horizon, signed_error)."""
    rows = []
    for sn in snaps:
        pr = park_ratio(sn["rides"], setting[0]) if setting else None
        for db_id, h, actual, ht, cur in sn["cases"]:
            if setting is None:
                pred = cur
            else:
                s = sn["rides"][db_id]
                hn = s["hn"]
                if hn is not None and hn > MIN_BASE:
                    hours = h / 60.0
                    own = clamp(s["live"] / hn)
                    r = pr + (own - pr) * math.exp(-hours / setting[1])
                    r = 1 + (r - 1) * math.exp(-hours / setting[2])
                    pred = ht * r
                else:
                    pred = cur
            rows.append((sn["day"], h, pred - actual))
    return rows


def stat(rows):
    if not rows:
        return "   n/a"
    return f"{mean(abs(e) for _, _, e in rows):5.2f} {mean(e for _, _, e in rows):+6.2f}"


def line(label, rows, groups):
    parts = [f"{label:<32} {stat(rows)}"]
    for g in ("busy", "normal", "quiet"):
        parts.append(stat([r for r in rows if groups.get(r[0]) == g]))
    return "  |  ".join(parts)


def main():
    snaps = build()
    groups = day_groups(snaps)
    print("\nday types:", {g: sum(1 for v in groups.values() if v == g) for g in ("busy", "normal", "quiet")})

    base = run(snaps, None)
    results = []
    for setting in itertools.product(MODES, TAU_OWNS, TAU_PARKS):
        results.append((mean(abs(e) for _, _, e in run(snaps, setting)), setting))
    results.sort()

    print(f"\n{'':<32} {'ALL  MAE   bias'}  |  busy MAE  bias  |  normal MAE  bias  |  quiet MAE  bias")
    print(line("current (own reading only)", base, groups))
    for mae, setting in results[:8]:
        print(line(str(setting), run(snaps, setting), groups))

    best = results[0][1]
    brows, crows = run(snaps, best), base

    print(f"\nPer day, best = {best}")
    print(f"{'date':<12} {'type':<7} {'current MAE':>12} {'best MAE':>9} {'cur bias':>9} {'best bias':>10}")
    for day in sorted(groups):
        c = [e for d, _, e in crows if d == day]
        b = [e for d, _, e in brows if d == day]
        if c and b:
            print(f"{day.isoformat():<12} {groups[day]:<7} {mean(abs(x) for x in c):>12.1f} "
                  f"{mean(abs(x) for x in b):>9.1f} {mean(c):>+9.1f} {mean(b):>+10.1f}")

    print("\nPer horizon (MAE): current vs best")
    for h in HORIZONS_MIN:
        c = [abs(e) for _, hh, e in crows if hh == h]
        b = [abs(e) for _, hh, e in brows if hh == h]
        if c and b:
            print(f"  {h:>3}m  {mean(c):5.2f}  {mean(b):5.2f}")


if __name__ == "__main__":
    main()