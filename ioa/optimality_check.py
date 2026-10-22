# optimality_check.py -- run with:  python optimality_check.py
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import routeOptimizer as ro

EIGHT = ["hulk", "spiderMan", "doctorDoom", "velociCoaster",
         "hagrid", "stormForce", "harryPotter", "skullIsland"]
FOUR = EIGHT[:4]
PARK_CLOSE = 20 * 60
REAL_WIDTH = ro.BEAM_WIDTH


def setup(keys, start_h, start_m, counts, locked, max_counts, pins):
    key_to_id, _ = ro._load_ride_id_map()
    ids = [key_to_id[k] for k in keys]
    histories = ro._load_wait_history(ids)
    walk_map = ro._load_walk_times()
    durations = ro._load_ride_durations()
    today = datetime.now(ro.PARK_TIMEZONE).date()
    start = datetime.combine(today, datetime.min.time()) + timedelta(hours=start_h, minutes=start_m)
    ro._ctx.bins = {}
    hist_now = {i: ro._historical_wait_curve(histories.get(i, []), start) for i in ids}
    locked = dict(locked)
    for p in pins:
        locked[p["ride_key"]] = True
    prob = ro._make_problem(dict(counts), key_to_id, locked, {}, max_counts, list(pins), None)
    return prob, histories, walk_map, durations, start, hist_now


def make_planner(env, breaks):
    prob, histories, walk_map, durations, start, hist_now = env
    planner = ro._Planner(histories, walk_map, durations, start, PARK_CLOSE,
                          [(float(a), float(b)) for a, b in breaks],
                          ro.ENTRANCE_DB_ID, {}, hist_now, {}, None)
    prob.lam = ro._estimate_lambda(prob, planner)
    return planner


def exhaustive(prob, planner):
    """Try every legal visiting order and return the best (key, sequence)."""
    best = [None, None]
    counts = [0] * prob.n

    def rec(seq, clock, last):
        k = ro._evaluate(prob, planner, [], seq)
        if k is not None and (best[0] is None or k > best[0]):
            best[0], best[1] = k, seq[:]
        prev = prob.ids[last] if last >= 0 else planner.start_db_id
        for i in range(prob.n):
            if counts[i] >= prob.cap[i]:
                continue
            if prob.repeat_factor(i, counts[i], last, prob.n) <= 0.0:
                continue
            act = planner.activity(clock, prev, prob.ids[i])
            if act[1] > planner.closing:
                continue
            counts[i] += 1
            seq.append(i)
            rec(seq, act[4], i)
            seq.pop()
            counts[i] -= 1

    rec([], planner.s0, -1)
    return best[0], best[1]


def run_case(name, keys, start_h, start_m, counts, locked=None, max_counts=None, breaks=(), pins=()):
    print(f"\n{name}", flush=True)
    env = setup(keys, start_h, start_m, counts, locked or {}, max_counts, pins)
    prob = env[0]
    if prob is None:
        print("  (nothing to plan)")
        return
    planner = make_planner(env, breaks)
    t0 = time.time()
    best_key, best_seq = exhaustive(prob, planner)
    print(f"  exhaustive search: {time.time() - t0:.1f}s")
    if best_key is None:
        print("  no legal plan exists")
        return
    print("  true best :", [prob.keys[i] for i in best_seq])
    for width in (REAL_WIDTH, 30):
        ro.BEAM_WIDTH = width
        t0 = time.time()
        seq = ro._plan(prob, planner)
        dt = time.time() - t0
        key = ro._evaluate(prob, planner, [], seq)
        label = f"beam {width:>3}"
        if key is None:
            verdict = "INVALID PLAN (breaks a rule)"
        elif all(abs(a - b) < 1e-3 for a, b in zip(key, best_key)):
            verdict = "OPTIMAL"
        else:
            verdict = (f"worse: tier {key[0] - best_key[0]:+.1f}, value {key[1] - best_key[1]:+.3f}, "
                       f"finishes {(-key[2]) - (-best_key[2]):+.1f} min later")
        print(f"  {label} ({dt:.1f}s): {verdict}")
    ro.BEAM_WIDTH = REAL_WIDTH


def timing():
    print("\n=== Full-size timing (all rides, real route function) ===", flush=True)
    key_to_id, _ = ro._load_ride_id_map()
    keys = [k for k in key_to_id if k not in ("entrance", "riverAdventure")]
    today = datetime.now(ro.PARK_TIMEZONE).date()
    start = datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=30)
    live = {k: 25 for k in keys}
    break_win = (12 * 60, 13 * 60)
    scenarios = [
        ("all rides once", dict(ride_counts={k: 1 for k in keys})),
        ("all rides twice (locked)", dict(ride_counts={k: 2 for k in keys},
                                           ride_locked={k: True for k in keys})),
        ("all once + 12-1 PM break + hulk pinned near 3 PM",
         dict(ride_counts={k: 1 for k in keys}, breaks=[break_win],
              time_pinned=[{"ride_key": "hulk", "target_minutes": 15 * 60}])),
    ]
    for name, kw in scenarios:
        t0 = time.time()
        out = ro.compute_and_print_route(start_time=start, live_waits=live, close_hour=21, close_minute=0,
                                         closed_ride_keys=["riverAdventure"], **kw)
        dt = time.time() - t0
        joins = [j for _, _, j in out]
        problems = []
        if joins != sorted(joins):
            problems.append("join times not in order")
        if joins and max(joins) > 21 * 60:
            problems.append("a stop joins after closing")
        if "breaks" in kw and any(break_win[0] <= j < break_win[1] for j in joins):
            problems.append("a stop joins during the break")
        print(f"\n{name}: {len(out)} stops in {dt:.1f}s  " + ("OK" if not problems else "PROBLEMS: " + "; ".join(problems)))
        if "time_pinned" in kw:
            print("  hulk joins at:", [f"{j // 60}:{j % 60:02d}" for k, _, j in out if k == "hulk"])
        print("  first stops:", [(k, round(w), f"{j // 60}:{j % 60:02d}") for k, w, j in out[:5]])


def main():
    print("=== Exact comparison on small problems (all orders tried) ===")
    run_case("A) 8 rides, one visit each, start 3:30 PM", EIGHT, 15, 30,
             {k: 1 for k in EIGHT}, max_counts={k: 1 for k in EIGHT})
    run_case("B) same, hagrid and hulk locked", EIGHT, 15, 30,
             {k: 1 for k in EIGHT}, locked={"hagrid": True, "hulk": True},
             max_counts={k: 1 for k in EIGHT})
    run_case("C) same as A, break 5:00-5:45 PM", EIGHT, 15, 30,
             {k: 1 for k in EIGHT}, max_counts={k: 1 for k in EIGHT}, breaks=[(17 * 60, 17 * 60 + 45)])
    run_case("D) 4 rides, 2 visits each (locked), start 2:00 PM", FOUR, 14, 0,
             {k: 2 for k in FOUR}, locked={k: True for k in FOUR}, max_counts={k: 2 for k in FOUR})
    SIX = EIGHT[:6]
    run_case("E) 6 rides, stormForce pinned first, hulk pinned last", SIX, 15, 30,
             {k: 1 for k in SIX}, max_counts={k: 1 for k in SIX},
             pins=[{"ride_key": "stormForce", "target_minutes": 0},
                   {"ride_key": "hulk", "target_minutes": 1440}])
    timing()


if __name__ == "__main__":
    main()