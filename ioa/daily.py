# daily.py -- run with:  python daily.py
import os
import bisect
from statistics import mean
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


def nearest(times, waits, when):
    i = bisect.bisect_left(times, when)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            gap = abs((times[j] - when).total_seconds()) / 60
            if gap <= MAX_GAP_MIN and (best is None or gap < best[0]):
                best = (gap, waits[j])
    return None if best is None else best[1]


def main():
    key_to_id, _ = ro._load_ride_id_map()
    ids = [i for i in key_to_id.values() if i != ro.ENTRANCE_DB_ID]
    print("Loading history...")
    history = ro._load_wait_history(ids)

    today = datetime.now(ro.PARK_TIMEZONE).date()
    days = [today - timedelta(days=d) for d in range(1, TEST_DAYS + 1)]
    by_day = defaultdict(lambda: {"model": [], "persist": [], "bias": [], "hbias": [], "actual": []})

    for db_id in ids:
        full = sorted(history.get(db_id, []))
        if len(full) < 500:
            continue
        times = [t for t, _ in full]
        waits = [w for _, w in full]
        for day in days:
            prev = [(t, w) for t, w in full if t.date() < day]
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
                    d = by_day[day]
                    d["model"].append(abs(pred - actual))
                    d["persist"].append(abs(live - actual))
                    d["bias"].append(pred - actual)
                    d["hbias"].append(hist - actual)
                    d["actual"].append(actual)

    print(f"\n{'date':<12} {'day':<4} {'n':>5} {'model':>6} {'persist':>8} {'bias':>6} {'hist bias':>10} {'avg wait':>9}")
    for day in sorted(by_day):
        d = by_day[day]
        print(f"{day.isoformat():<12} {day.strftime('%a'):<4} {len(d['model']):>5} "
              f"{mean(d['model']):>6.1f} {mean(d['persist']):>8.1f} {mean(d['bias']):>+6.1f} "
              f"{mean(d['hbias']):>+10.1f} {mean(d['actual']):>9.1f}")


if __name__ == "__main__":
    main()