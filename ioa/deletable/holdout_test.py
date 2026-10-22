# holdout_test.py -- run with:  python holdout_test.py
from datetime import date
from statistics import mean, median

from ride_skill import collect            # must come first: it loads the .env
import routeOptimizer as ro
from blend_test import HORIZONS_MIN

FROM_DATE = date(2026, 8, 26)             # days never used for tuning
TO_DATE = date(2026, 9, 28)

A, L, N = 3, 4, 5                         # actual, live, prediction
ok = lambda p, a: abs(p - a) < (10 if a >= 60 else 5)


def pct(xs):
    xs = list(xs)
    return 100 * mean(xs) if xs else float("nan")


def run(use_park, tau):
    ro.USE_PARK_FACTOR = use_park
    ro.ANCHOR_DECAY_HOURS_RATIO = tau
    return collect(from_date=FROM_DATE, to_date=TO_DATE, max_days=70)


def main():
    print("=== OLD settings: park factor on, 3 h ===")
    old, names = run(True, 3.0)
    print("=== NEW settings: park factor off, 12 h ===")
    new, _ = run(False, 12.0)
    if not old or not new:
        print("No rows came back. Check FROM_DATE / TO_DATE.")
        return

    print(f"\nOut-of-sample days {FROM_DATE} to {TO_DATE}: {len(new)} predictions")
    print("Strict hit rate (error under 5 min, under 10 if actual >= 60)")
    print(f"{'ahead':>6} {'stay':>7} {'OLD':>7} {'NEW':>7} {'NEW median err':>15}")
    for h in HORIZONS_MIN:
        o = [x for x in old if x[1] == h]
        n = [x for x in new if x[1] == h]
        if n:
            print(f"{h:>5}m {pct(ok(x[L], x[A]) for x in n):>7.1f} {pct(ok(x[N], x[A]) for x in o):>7.1f} "
                  f"{pct(ok(x[N], x[A]) for x in n):>7.1f} {median(abs(x[N] - x[A]) for x in n):>15.1f}")
    print(f"{'ALL':>6} {pct(ok(x[L], x[A]) for x in new):>7.1f} {pct(ok(x[N], x[A]) for x in old):>7.1f} "
          f"{pct(ok(x[N], x[A]) for x in new):>7.1f} {median(abs(x[N] - x[A]) for x in new):>15.1f}")

    print("\nBy ride: OLD vs NEW")
    by_o, by_n = {}, {}
    for x in old:
        by_o.setdefault(x[2], []).append(x)
    for x in new:
        by_n.setdefault(x[2], []).append(x)
    wins = 0
    for db_id in sorted(by_n, key=lambda d: names.get(d, str(d))):
        o, n = pct(ok(x[N], x[A]) for x in by_o.get(db_id, [])), pct(ok(x[N], x[A]) for x in by_n[db_id])
        wins += n > o
        print(f"  {names.get(db_id, db_id):<16} OLD {o:5.1f}   NEW {n:5.1f}   {n - o:+5.1f}")
    print(f"\nNEW beats OLD on {wins} of {len(by_n)} rides")


if __name__ == "__main__":
    main()