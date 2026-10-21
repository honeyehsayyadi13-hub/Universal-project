# persist_test.py -- run with:  python persist_test.py
import math
from statistics import mean
from collections import namedtuple
from datetime import datetime, timedelta

from blend_test import nearest, TEST_DAYS, NEWER, NOW_HOURS, HORIZONS_MIN   # must come first: it loads the .env
import routeOptimizer as ro

TAU_OWNS = [3.0, 6.0, 12.0, 24.0, 1e9]       # hours a ride's own live ratio lasts
PROD = (True, ro.CROWD_TAU_OWN_HOURS)        # (park factor on, tau_own) = what is live now
Row = namedtuple("Row", "idx h db_id actual live hn ht pr fb")


def ok(p, a):
    return abs(p - a) < (10 if a >= 60 else 5)


def fmt(t):
    return "inf" if t >= 1e8 else f"{t:g}"


def predict(r, s):
    if r.fb is not None:                      # low-baseline / no-history rows use the production fallback
        return r.fb
    use_park, tau = s
    hrs = r.h / 60.0
    own = max(ro.CROWD_RATIO_MIN, min(ro.CROWD_RATIO_MAX, r.live / r.hn))
    base = r.pr if use_park else 1.0
    x = base + (own - base) * math.exp(-hrs / tau)
    if use_park:
        x = 1.0 + (x - 1.0) * math.exp(-hrs / ro.CROWD_TAU_PARK_HOURS)
    return max(0.0, r.ht * x)


def hr(rs, s):
    return 100 * mean(ok(predict(r, s), r.actual) for r in rs) if rs else float("nan")


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
            pr = 1.0
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
                    ht = ro._historical_wait_curve(p, target)
                    fb = None
                    if ht is None or hn is None or hn <= ro.MIN_MEANINGFUL_BASELINE_MIN:
                        fb = ro._predict_wait(p, target, current_wait=live, now=now, historical_now=hn)
                    rows.append(Row(idx, h, db_id, actual, live, hn, ht, pr, fb))
        print(f"  done {day}", flush=True)
    return rows, id_to_key


def main():
    rows, names = collect()
    ids = {v: k for k, v in names.items()}
    older = [r for r in rows if r.idx > NEWER]
    newer = [r for r in rows if r.idx <= NEWER]
    hippo = [r for r in rows if r.db_id == ids.get("hippogriff")]
    ripsaw = [r for r in rows if r.db_id == ids.get("ripsawFalls")]

    print("\nStrict hit rate (error under 5 min, under 10 if actual >= 60)")
    print(f"{'park factor':<12} {'tau_own h':>10} {'ALL':>6} {'older7':>7} {'newer7':>7} {'hippo':>6} {'ripsaw':>7}")
    stay = lambda rs: 100 * mean(ok(r.live, r.actual) for r in rs)
    print(f"{'(copy live)':<12} {'':>10} {stay(rows):>6.1f} {stay(older):>7.1f} {stay(newer):>7.1f} "
          f"{stay(hippo):>6.1f} {stay(ripsaw):>7.1f}")
    for use_park in (False, True):
        for tau in TAU_OWNS:
            s = (use_park, tau)
            mark = "  <- live now" if s == PROD else ""
            print(f"{('on' if use_park else 'off'):<12} {fmt(tau):>10} {hr(rows, s):>6.1f} {hr(older, s):>7.1f} "
                  f"{hr(newer, s):>7.1f} {hr(hippo, s):>6.1f} {hr(ripsaw, s):>7.1f}{mark}")

    by = {}
    for r in rows:
        by.setdefault(r.db_id, []).append(r)

    def pick(rs):
        best_tau, best = PROD[1], hr(rs, PROD)
        for tau in TAU_OWNS:
            v = hr(rs, (True, tau))
            if v > best + 1e-9:
                best_tau, best = tau, v
        return best_tau

    for label, train, test in (
        ("choose on OLDER week, score on NEWER week", lambda r: r.idx > NEWER, lambda r: r.idx <= NEWER),
        ("choose on NEWER week, score on OLDER week", lambda r: r.idx <= NEWER, lambda r: r.idx > NEWER),
    ):
        chosen, hyb, prod = {}, [], []
        for db_id, rs in by.items():
            tr = [r for r in rs if train(r)]
            te = [r for r in rs if test(r)]
            if not tr or not te:
                continue
            tau = pick(tr)
            chosen[db_id] = tau
            hyb += [ok(predict(r, (True, tau)), r.actual) for r in te]
            prod += [ok(predict(r, PROD), r.actual) for r in te]
        print(f"\nPer-ride tau_own: {label}")
        print("  chosen:", ", ".join(f"{names[d]} {fmt(t)}h" for d, t in sorted(chosen.items(), key=lambda kv: names[kv[0]])))
        print(f"  live-now settings: {100 * mean(prod):.1f}%    per-ride choice: {100 * mean(hyb):.1f}%")


if __name__ == "__main__":
    main()