# round5_test.py -- run with:  python round5_test.py
import os
import math
from statistics import mean
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from ride_skill import collect, hit, pct
from blend_test import HORIZONS_MIN, NEWER

A, L, N = 3, 4, 5   # actual, live, new


def r5(x):
    return 5 * math.floor(x / 5 + 0.5)


def main():
    rows, names = collect()

    print("\n1) Are posted waits multiples of 5?")
    print(f"  actual waits: {pct(x[A] % 5 == 0 for x in rows)}   live waits: {pct(x[L] % 5 == 0 for x in rows)}")

    cands = {
        "stay": lambda x: x[L],
        "NEW": lambda x: x[N],
        "NEW rounded to 5": lambda x: r5(x[N]),
        "live+0.5*(NEW-live), rounded": lambda x: r5(x[L] + 0.5 * (x[N] - x[L])),
    }
    print("\n2) Hit rate (within 5, or 10 if actual >= 60)")
    print(f"{'candidate':<30} " + " ".join(f"{h:>5}m" for h in HORIZONS_MIN) + "    ALL")
    for name, f in cands.items():
        cells = []
        for h in HORIZONS_MIN:
            cells.append(pct(hit(f(x), x[A]) for x in rows if x[1] == h))
        print(f"{name:<30} " + " ".join(f"{c:>6}" for c in cells) +
              f" {pct(hit(f(x), x[A]) for x in rows):>7}")

    print("\n3) Level shift by ride (older week -> newer week)")
    print(f"{'ride':<16} {'older avg':>10} {'newer avg':>10} {'NEW bias, newer':>16}")
    by = {}
    for x in rows:
        by.setdefault(x[2], []).append(x)
    out = []
    for db_id, r in by.items():
        old = [x for x in r if x[0] > NEWER]
        new = [x for x in r if x[0] <= NEWER]
        if old and new:
            out.append((mean(x[A] for x in new) - mean(x[A] for x in old), db_id,
                        mean(x[A] for x in old), mean(x[A] for x in new),
                        mean(x[N] - x[A] for x in new)))
    for _, db_id, o, n, b in sorted(out, reverse=True):
        print(f"{names.get(db_id, db_id):<16} {o:>10.1f} {n:>10.1f} {b:>+16.1f}")


if __name__ == "__main__":
    main()