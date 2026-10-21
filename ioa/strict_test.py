# strict_test.py -- run with:  python strict_test.py
from statistics import mean, median
from ride_skill import collect
from blend_test import HORIZONS_MIN

A, L, N = 3, 4, 5   # actual, live, new


def lim(a):
    return 10 if a >= 60 else 5


def ok(p, a):
    return abs(p - a) < lim(a)


def pct(xs):
    xs = list(xs)
    return f"{100 * mean(xs):5.1f}%" if xs else "   n/a"


def main():
    rows, names = collect()
    print("\nHit = error UNDER 5 min (under 10 if actual wait >= 60), no rounding")
    print(f"{'ahead':>6} {'stay':>7} {'NEW':>7} {'NEW median err':>15} {'NEW err>=5':>11}")
    for h in HORIZONS_MIN:
        r = [x for x in rows if x[1] == h]
        print(f"{h:>5}m {pct(ok(x[L], x[A]) for x in r):>7} {pct(ok(x[N], x[A]) for x in r):>7} "
              f"{median(abs(x[N] - x[A]) for x in r):>15.1f} {pct(abs(x[N] - x[A]) >= 5 for x in r):>11}")
    print(f"{'ALL':>6} {pct(ok(x[L], x[A]) for x in rows):>7} {pct(ok(x[N], x[A]) for x in rows):>7} "
          f"{median(abs(x[N] - x[A]) for x in rows):>15.1f} {pct(abs(x[N] - x[A]) >= 5 for x in rows):>11}")

    print("\nBy ride (NEW)")
    by = {}
    for x in rows:
        by.setdefault(x[2], []).append(x)
    for db_id, r in sorted(by.items(), key=lambda kv: mean(ok(x[N], x[A]) for x in kv[1])):
        print(f"{names.get(db_id, db_id):<16} n={len(r):>4}  hit {pct(ok(x[N], x[A]) for x in r)}  "
              f"median err {median(abs(x[N] - x[A]) for x in r):4.1f}  avg wait {mean(x[A] for x in r):5.1f}")


if __name__ == "__main__":
    main()