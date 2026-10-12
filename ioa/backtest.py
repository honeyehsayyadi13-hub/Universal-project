# backtest.py -- run with:  python backtest.py
import os
import bisect
from statistics import mean
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro

TEST_DAYS = 14
NOW_HOURS = [10, 11, 12, 13, 14, 15, 16, 17]
HORIZONS_MIN = [15, 30, 60, 120, 180, 240]
MAX_GAP_MIN = 10


def nearest(times, waits, when):
    """Reading closest to `when`, or None if none within MAX_GAP_MIN minutes."""
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def main():
    key_to_id, id_to_key = ro._load_ride_id_map()
    ids = [i for i in key_to_id.values() if i != ro.ENTRANCE_DB_ID]
    print("Loading history (can take a minute the first time)...")
    history = ro._load_wait_history(ids)

    today = datetime.now(ro.PARK_TIMEZONE).date()
    test_days = [today - timedelta(days=d) for d in range(1, TEST_DAYS + 1)]

    by_h = defaultdict(lambda: {"model": [], "hist": [], "persist": [], "bias": []})
    by_ride = defaultdict(list)

    for db_id in ids:
        full = sorted(history.get(db_id, []))
        if len(full) < 500:
            print(f"skipping ride {db_id} ({id_to_key.get(db_id)}): only {len(full)} usable readings")
            continue
        times = [t for t, _ in full]
        waits = [w for _, w in full]

        for day in test_days:
            prev = [(t, w) for t, w in full if t.date() < day]   # earlier days only
            if len(prev) < 500:
                continue
            ro._ctx.bins = {}
            midnight = datetime.combine(day, datetime.min.time())
            for hour in NOW_HOURS:
                now = midnight + timedelta(hours=hour)
                live = nearest(times, waits, now)
                if live is None:
                    continue
                for h in HORIZONS_MIN:
                    target = now + timedelta(minutes=h)
                    actual = nearest(times, waits, target)
                    if actual is None:
                        continue
                    hist = ro._historical_wait_curve(prev, target)
                    if hist is None:
                        continue
                    pred = ro._predict_wait(prev, target, current_wait=live, now=now)
                    d = by_h[h]
                    d["model"].append(abs(pred - actual))
                    d["hist"].append(abs(hist - actual))
                    d["persist"].append(abs(live - actual))
                    d["bias"].append(pred - actual)
                    by_ride[db_id].append((abs(pred - actual), actual))

    print(f"\nBacktest: last {TEST_DAYS} days, predictions made 10 AM-5 PM (errors in minutes)")
    print(f"{'ahead':>6} {'n':>6} {'model':>8} {'hist-only':>10} {'persist':>9} {'bias':>7}")
    for h in HORIZONS_MIN:
        d = by_h[h]
        if not d["model"]:
            continue
        print(f"{h:>5}m {len(d['model']):>6} {mean(d['model']):>8.1f} {mean(d['hist']):>10.1f} "
              f"{mean(d['persist']):>9.1f} {mean(d['bias']):>+7.1f}")

    print(f"\n{'ride':<18} {'n':>6} {'MAE':>6} {'avg actual wait':>16}")
    for db_id, rows in sorted(by_ride.items(), key=lambda kv: -mean(e for e, _ in kv[1])):
        print(f"{id_to_key.get(db_id, db_id):<18} {len(rows):>6} "
              f"{mean(e for e, _ in rows):>6.1f} {mean(a for _, a in rows):>16.1f}")


if __name__ == "__main__":
    main()