# ride_skill.py -- run with:  python ride_skill.py
import os
from statistics import mean
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro
from blend_test import nearest, tol, TEST_DAYS, NEWER, NOW_HOURS, HORIZONS_MIN


def hit(p, a):
    return abs(p - a) <= tol(a)


def pct(xs):
    xs = list(xs)
    return f"{100 * mean(xs):5.1f}%" if xs else "   n/a"


def collect():
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
    rows = []   # (idx, horizon, db_id, actual, live, new)
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
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is None:
                        continue
                    new = ro._predict_wait(prevs[db_id], target, current_wait=live, now=now,
                                           historical_now=hn, park_ratio=pr)
                    rows.append((idx, h, db_id, actual, live, new))
        print(f"  done {day}", flush=True)
    return rows, id_to_key


def main():
    rows, names = collect()
    A, L, N = 3, 4, 5   # column positions: actual, live, new

    print("\n1) When the wait really changes, does the model help?")
    print(f"{'ahead':>6} {'stay misses':>12} {'NEW rescues':>12} {'stay hits':>10} {'NEW still hits':>15}")
    for h in HORIZONS_MIN:
        r = [x for x in rows if x[1] == h]
        miss = [x for x in r if not hit(x[L], x[A])]
        held = [x for x in r if hit(x[L], x[A])]
        print(f"{h:>5}m {len(miss):>12} {pct(hit(x[N], x[A]) for x in miss):>12} "
              f"{len(held):>10} {pct(hit(x[N], x[A]) for x in held):>15}")

    print("\n2) Does the model's predicted direction match what happens?")
    for label, sel in (("model says UP (>= +5)", [x for x in rows if x[N] - x[L] >= 5]),
                       ("model says DOWN (<= -5)", [x for x in rows if x[N] - x[L] <= -5])):
        if sel:
            print(f"  {label:<24} n={len(sel):>5}  avg predicted change {mean(x[N] - x[L] for x in sel):+6.1f}"
                  f"   avg ACTUAL change {mean(x[A] - x[L] for x in sel):+6.1f}")

    print("\n3) By ride (all days, all horizons)")
    print(f"{'ride':<16} {'n':>5} {'stay hit':>9} {'NEW hit':>8} {'stay MAE':>9} {'NEW MAE':>8} {'avg wait':>9}")
    by = {}
    for x in rows:
        by.setdefault(x[2], []).append(x)
    ordered = sorted(by.items(), key=lambda kv: mean(hit(x[N], x[A]) for x in kv[1]) -
                                                 mean(hit(x[L], x[A]) for x in kv[1]), reverse=True)
    for db_id, r in ordered:
        print(f"{names.get(db_id, db_id):<16} {len(r):>5} {pct(hit(x[L], x[A]) for x in r):>9} "
              f"{pct(hit(x[N], x[A]) for x in r):>8} {mean(abs(x[L] - x[A]) for x in r):>9.1f} "
              f"{mean(abs(x[N] - x[A]) for x in r):>8.1f} {mean(x[A] for x in r):>9.1f}")

    print("\n4) Per-ride choice made on the OLDER week, scored on the NEWER week")
    choice = {}
    for db_id, r in by.items():
        old = [x for x in r if x[0] > NEWER]
        if old:
            choice[db_id] = "NEW" if mean(hit(x[N], x[A]) for x in old) > mean(hit(x[L], x[A]) for x in old) else "stay"
    newer = [x for x in rows if x[0] <= NEWER and x[2] in choice]
    hybrid = [hit(x[N] if choice[x[2]] == "NEW" else x[L], x[A]) for x in newer]
    print("  rides that use NEW:", ", ".join(names.get(d, str(d)) for d, c in choice.items() if c == "NEW") or "none")
    print(f"  newest 7 days: stay {pct(hit(x[L], x[A]) for x in newer)}   NEW {pct(hit(x[N], x[A]) for x in newer)}"
          f"   per-ride hybrid {pct(hybrid)}")


if __name__ == "__main__":
    main()