# forward_test.py -- run with:  python forward_test.py
# Run it no sooner than ~Oct 24, ideally after Oct 28. Settings must stay frozen until then.
from datetime import date, datetime, timedelta
from statistics import mean, median

from ride_skill import collect            # must come first: it loads the .env
import routeOptimizer as ro
from blend_test import HORIZONS_MIN

FROM_DATE = date(2026, 10, 22)            # first day NOT used for any tuning

A, L, N = 3, 4, 5                         # actual, live, new
ok = lambda p, a: abs(p - a) < (10 if a >= 60 else 5)


def pct(xs):
    xs = list(xs)
    return f"{100 * mean(xs):5.1f}%" if xs else "   n/a"


def main():
    rows, names = collect(from_date=FROM_DATE)
    if not rows:
        print(f"No complete days on or after {FROM_DATE} yet. Try again later.")
        return
    today = datetime.now(ro.PARK_TIMEZONE).date()
    days = sorted({today - timedelta(days=x[0]) for x in rows})
    print(f"\nForward test: {len(days)} day(s), {days[0]} to {days[-1]}, {len(rows)} predictions")
    if len(days) < 5:
        print("  (fewer than 5 days: treat this as a rough check, not a verdict)")

    print("\nStrict hit rate (error under 5 min, under 10 if actual >= 60)")
    print(f"{'ahead':>6} {'n':>6} {'stay':>7} {'model':>7} {'median err':>11}")
    for h in HORIZONS_MIN:
        r = [x for x in rows if x[1] == h]
        if r:
            print(f"{h:>5}m {len(r):>6} {pct(ok(x[L], x[A]) for x in r):>7} "
                  f"{pct(ok(x[N], x[A]) for x in r):>7} {median(abs(x[N] - x[A]) for x in r):>11.1f}")
    print(f"{'ALL':>6} {len(rows):>6} {pct(ok(x[L], x[A]) for x in rows):>7} "
          f"{pct(ok(x[N], x[A]) for x in rows):>7} {median(abs(x[N] - x[A]) for x in rows):>11.1f}")
    print("  (tuned-days reference: model 59.3% overall, median error 3.8)")

    print("\nBy day (model)")
    for d in days:
        r = [x for x in rows if today - timedelta(days=x[0]) == d]
        print(f"  {d} {d.strftime('%a')}  n={len(r):>4}  hit {pct(ok(x[N], x[A]) for x in r)}  "
              f"bias {mean(x[N] - x[A] for x in r):+5.1f}  avg wait {mean(x[A] for x in r):5.1f}")

    print("\nBy ride (model)")
    by = {}
    for x in rows:
        by.setdefault(x[2], []).append(x)
    for db_id, r in sorted(by.items(), key=lambda kv: mean(ok(x[N], x[A]) for x in kv[1])):
        print(f"  {names.get(db_id, db_id):<16} n={len(r):>4}  hit {pct(ok(x[N], x[A]) for x in r)}  "
              f"median err {median(abs(x[N] - x[A]) for x in r):4.1f}")


if __name__ == "__main__":
    main()