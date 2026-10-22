# diag.py -- run with:  python diag.py
from statistics import mean
from blend_test import collect, NEWER, HORIZONS_MIN   # must come first: it loads the .env
import routeOptimizer as ro


def ok(p, a):
    return abs(p - a) < (10 if a >= 60 else 5)


def pct(xs):
    xs = list(xs)
    return f"{100 * mean(xs):5.1f}%" if xs else "   n/a"


def avg(xs):
    xs = list(xs)
    return f"{mean(xs):.1f}" if xs else "--"


def main():
    rows = collect()
    key_to_id, _ = ro._load_ride_id_map()

    print("\n1) Strict hit rate: curve only vs old (no park factor) vs NEW (park factor)")
    print(f"{'ahead':>6} {'curve only':>11} {'old':>7} {'NEW':>7}")
    for h in HORIZONS_MIN:
        r = [x for x in rows if x.h == h]
        c = [x for x in r if x.ht is not None]
        print(f"{h:>5}m {pct(ok(x.ht, x.actual) for x in c):>11} "
              f"{pct(ok(x.old, x.actual) for x in r):>7} {pct(ok(x.new, x.actual) for x in r):>7}")
    c = [x for x in rows if x.ht is not None]
    print(f"{'ALL':>6} {pct(ok(x.ht, x.actual) for x in c):>11} "
          f"{pct(ok(x.old, x.actual) for x in rows):>7} {pct(ok(x.new, x.actual) for x in rows):>7}")

    for key in ("hippogriff", "ripsawFalls"):
        r = [x for x in rows if x.db_id == key_to_id[key]]

        print(f"\n2) {key}: by hour of the target time")
        print(f"{'hour':>6} {'n':>4} {'actual older wk':>16} {'actual newer wk':>16} {'curve':>7} {'NEW':>7} {'NEW hit':>8}")
        for hr in range(10, 22):
            s = [x for x in r if x.tgt.hour == hr]
            if not s:
                continue
            print(f"{hr:>3}:00 {len(s):>4} {avg(x.actual for x in s if x.idx > NEWER):>16} "
                  f"{avg(x.actual for x in s if x.idx <= NEWER):>16} "
                  f"{avg(x.ht for x in s if x.ht is not None):>7} {avg(x.new for x in s):>7} "
                  f"{pct(ok(x.new, x.actual) for x in s):>8}")

        print(f"\n3) {key}: by day")
        print(f"{'date':<12} {'n':>4} {'avg actual':>11} {'avg curve':>10} {'avg NEW':>8} {'NEW hit':>8}")
        for d in sorted({x.tgt.date() for x in r}):
            s = [x for x in r if x.tgt.date() == d]
            print(f"{d.isoformat():<12} {len(s):>4} {avg(x.actual for x in s):>11} "
                  f"{avg(x.ht for x in s if x.ht is not None):>10} {avg(x.new for x in s):>8} "
                  f"{pct(ok(x.new, x.actual) for x in s):>8}")


if __name__ == "__main__":
    main()