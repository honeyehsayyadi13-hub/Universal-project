# blend_test.py -- run with:  python blend_test.py
import os
import math
import bisect
from statistics import mean
from collections import namedtuple
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro

TEST_DAYS = 14
NEWER = 7                      # day_idx 1..7 = newest week (validation); 8..14 = older week (selection)
NOW_HOURS = [10, 11, 12, 13, 14, 15, 16, 17]
HORIZONS_MIN = [15, 30, 60, 120, 180, 240]
MAX_GAP_MIN = 10
LONG_WAIT_MIN, TOL_SHORT, TOL_LONG = 60, 5, 10

R = namedtuple("R", "idx h actual live old new ht hmed")


def tol(a):
    return TOL_LONG if a >= LONG_WAIT_MIN else TOL_SHORT


def nearest(times, waits, when):
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def hist_median(prev, target):
    """Kernel-weighted median of the history near this time of day (uses the optimizer's own bins)."""
    bw, bws = ro._get_bins(prev, target)
    tm = target.hour * 60 + target.minute
    center = tm // ro.HISTORY_BIN_MIN
    reach = int(4 * ro.TIME_KERNEL_BANDWIDTH_MIN // ro.HISTORY_BIN_MIN) + 1
    items = []
    for off in range(-reach, reach + 1):
        b = (center + off) % ro._NBINS
        if bw[b] <= 0:
            continue
        bc = b * ro.HISTORY_BIN_MIN + ro.HISTORY_BIN_MIN / 2.0
        raw = abs(bc - tm)
        d = min(raw, 1440 - raw)
        k = math.exp(-(d ** 2) / (2 * ro.TIME_KERNEL_BANDWIDTH_MIN ** 2))
        items.append((bws[b] / bw[b], k * bw[b]))
    if not items:
        return None
    items.sort()
    half = sum(w for _, w in items) / 2
    acc = 0.0
    for v, w in items:
        acc += w
        if acc >= half:
            return v
    return items[-1][0]


def collect():
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
    rows = []
    for idx in range(1, TEST_DAYS + 1):
        day = today - timedelta(days=idx)
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
                if live is not None:
                    snap[db_id] = (live, ro._historical_wait_curve(p, now))
            num = den = 0.0
            used = 0
            for live, hn in snap.values():
                if hn is not None and hn > ro.MIN_MEANINGFUL_BASELINE_MIN:
                    num += live
                    den += hn
                    used += 1
            pr = None
            if used >= ro.CROWD_MIN_RIDES and den > 0:
                pr = max(ro.CROWD_RATIO_MIN, min(ro.CROWD_RATIO_MAX, num / den))
            for db_id, (live, hn) in snap.items():
                _, times, waits = rides[db_id]
                p = prevs[db_id]
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is None:
                        continue
                    old = ro._predict_wait(p, target, current_wait=live, now=now, historical_now=hn)
                    new = ro._predict_wait(p, target, current_wait=live, now=now, historical_now=hn, park_ratio=pr)
                    ht = ro._historical_wait_curve(p, target)
                    hm = hist_median(p, target) if ht is not None else None
                    rows.append(R(idx, h, actual, live, old, new, ht, hm))
        print(f"  done {day}", flush=True)
    return rows


def med(r):
    if r.ht is not None and r.hmed is not None and r.ht > 0.3:
        return r.new * r.hmed / r.ht
    return r.new


def blend(a, base):
    return lambda r: a * r.live + (1 - a) * base(r)


def fade(tau, base):
    return lambda r: math.exp(-(r.h / 60.0) / tau) * r.live + (1 - math.exp(-(r.h / 60.0) / tau)) * base(r)


NEW = lambda r: r.new
CANDS = {
    "stay (copy live wait)": lambda r: r.live,
    "old (no park factor)": lambda r: r.old,
    "NEW (in production)": NEW,
    "median baseline": med,
    "blend 25% live + NEW": blend(0.25, NEW),
    "blend 50% live + NEW": blend(0.5, NEW),
    "blend 75% live + NEW": blend(0.75, NEW),
    "fade tau=2h live->NEW": fade(2, NEW),
    "fade tau=4h live->NEW": fade(4, NEW),
    "fade tau=8h live->NEW": fade(8, NEW),
    "blend 50% live + median": blend(0.5, med),
    "blend 75% live + median": blend(0.75, med),
    "fade tau=4h live->median": fade(4, med),
    "fade tau=8h live->median": fade(8, med),
}


def hit(rows, f):
    return 100 * mean(abs(f(r) - r.actual) <= tol(r.actual) for r in rows) if rows else float("nan")


def main():
    rows = collect()
    newer = [r for r in rows if r.idx <= NEWER]
    older = [r for r in rows if r.idx > NEWER]
    print(f"\nHit rate (within {TOL_SHORT} min, or {TOL_LONG} if actual wait >= {LONG_WAIT_MIN})")
    print(f"{'candidate':<28} {'ALL':>6} {'older7':>7} {'newer7':>7} {'15m':>6} {'60m':>6} {'240m':>6}")
    scored = []
    for name, f in CANDS.items():
        a, o, n = hit(rows, f), hit(older, f), hit(newer, f)
        h15 = hit([r for r in rows if r.h == 15], f)
        h60 = hit([r for r in rows if r.h == 60], f)
        h240 = hit([r for r in rows if r.h == 240], f)
        scored.append((o, n, name))
        print(f"{name:<28} {a:>6.1f} {o:>7.1f} {n:>7.1f} {h15:>6.1f} {h60:>6.1f} {h240:>6.1f}")
    best = max(scored)
    stay_new = next(n for o, n, nm in scored if nm.startswith("stay"))
    print(f"\nBest on the older 7 days: '{best[2]}' ({best[0]:.1f}%)")
    print(f"Same candidate on the newest 7 days (unseen): {best[1]:.1f}%   vs  'stay': {stay_new:.1f}%")


if __name__ == "__main__":
    main()