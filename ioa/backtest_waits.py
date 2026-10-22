"""
backtest_waits.py -- measures how accurate routeOptimizer's predicted waits really are.

For every ride and every recent day, it pretends to be standing in the park at
several "origin" times (e.g. 9:00, 10:00 ... 19:00), uses ONLY data that existed
at that moment, predicts the wait N hours ahead, and compares it to what the
wait actually was N hours later.

"Only data that existed at that moment" means:
  * baseline history = readings from PREVIOUS days only (this is exactly what
    compute_and_print_route does for rides that have a live reading), and
  * the "live reading" = the logged reading closest to the origin time that day.

Three predictors are compared side by side:
  model        -- routeOptimizer._predict_wait (live-anchored, decaying to history)
  history only -- the plain time-of-day curve, no live anchoring
  persistence  -- "it will stay what it is right now"

Setup: put this file in the SAME folder as routeOptimizer.py and set the same
SUPABASE_URL / SUPABASE_KEY environment variables the server uses.

Usage:
    python backtest_waits.py                       # report on the last 30 days
    python backtest_waits.py --cache hist.pkl      # save/reuse the download (much faster reruns)
    python backtest_waits.py --tune --cache hist.pkl   # search for better constants
    python backtest_waits.py --skip-zeros          # ignore 0-minute readings
    python backtest_waits.py --rides hulk velociCoaster --horizons 1 3 6
"""

import argparse
import bisect
import itertools
import os
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, time as dtime

import routeOptimizer as ro


# ── editable tuning grid (used only with --tune) ──────────────────────
# The first key varies slowest, so it's the one that's expensive to change.
TUNE_GRID = {
    "RECENCY_HALF_LIFE_DAYS":   [30, 45, 90],
    "TIME_KERNEL_BANDWIDTH_MIN": [30, 45, 60],
    "ANCHOR_DECAY_HOURS_RATIO": [3.0, 6.0, 12.0, 24.0],
    "ANCHOR_MODE":              ["ratio"],      # add "add" to also test additive anchoring
}


# ── data loading ─────────────────────────────────────────────────────
def load_histories(args):
    """Return {ride_key: [(naive_eastern_ts, waittime), ...]} sorted by time."""
    if args.cache and os.path.exists(args.cache):
        print(f"Loading cached history from {args.cache} ...")
        with open(args.cache, "rb") as f:
            return pickle.load(f)

    print("Downloading history from Supabase (this can take a minute) ...")
    ro.HISTORY_WINDOW_DAYS = args.window_days
    key_to_id, _ = ro._load_ride_id_map()
    ids = {k: v for k, v in key_to_id.items() if v != ro.ENTRANCE_DB_ID}
    loaded = ro._load_wait_history(list(ids.values()))

    hist = {}
    for key, db_id in ids.items():
        h = sorted(loaded.get(db_id, []))
        if h:
            hist[key] = h

    if args.cache:
        with open(args.cache, "wb") as f:
            pickle.dump(hist, f)
        print(f"Saved history to {args.cache}")
    return hist


def print_hour_diagnostic(histories):
    """Sanity check for timezone problems: when does the data say the park is open?"""
    counts = [0] * 24
    for h in histories.values():
        for ts, _ in h:
            counts[ts.hour] += 1
    total = sum(counts) or 1
    print("\nShare of readings by hour of day (should match park hours in EASTERN time):")
    print("  " + "  ".join(f"{hr:02d}:{100 * c / total:4.1f}%" for hr, c in enumerate(counts) if c / total >= 0.005))
    print("  If the busy hours look shifted by 4-5 hours, the timestamps are UTC, not Eastern.\n")


# ── building test cases ──────────────────────────────────────────────
def make_nearest(mins, waits, tol):
    def nearest(m):
        i = bisect.bisect_left(mins, m)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(mins):
                d = abs(mins[j] - m)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, waits[j])
        return None if best is None else best[1]
    return nearest


def build_cases(histories, args):
    """One case per (ride, day): the prior-days history plus the (origin, target, live, actual) tuples."""
    origins = list(range(args.origin_start * 60, args.origin_end * 60 + 1, args.origin_step_min))
    cases = []
    for key, hist in histories.items():
        if args.rides and key not in args.rides:
            continue
        ts_list = [t for t, _ in hist]
        days = sorted({t.date() for t in ts_list})
        eligible = days[args.min_prior_days:]            # needs enough earlier days to learn from
        for day in eligible[-args.eval_days:]:
            midnight = datetime.combine(day, dtime.min)
            lo = bisect.bisect_left(ts_list, midnight)
            hi = bisect.bisect_left(ts_list, midnight + timedelta(days=1))
            prior = hist[:lo]
            today = hist[lo:hi]
            if not prior or not today:
                continue
            mins = [t.hour * 60 + t.minute for t, _ in today]
            waits = [w for _, w in today]
            nearest = make_nearest(mins, waits, args.match_tol_min)

            items = []
            for om in origins:
                cur = nearest(om)
                if cur is None:
                    continue
                for h in args.horizons:
                    tm = om + int(round(h * 60))
                    if tm >= 1440:
                        continue
                    act = nearest(tm)
                    if act is None:
                        continue
                    if args.skip_zeros and (act == 0 or cur == 0):
                        continue
                    items.append((midnight + timedelta(minutes=om),
                                  midnight + timedelta(minutes=tm), cur, act, h))
            if items:
                cases.append({"key": key, "day": day, "prior": prior, "items": items})
    return cases


# ── predictors ───────────────────────────────────────────────────────
def _model(prior, odt, tdt, cur):
    return ro._predict_wait(prior, tdt, current_wait=cur, now=odt)


def _hist_only(prior, odt, tdt, cur):
    v = ro._historical_wait_curve(prior, tdt)
    return v if v is not None else ro.DEFAULT_WAIT_MIN


def _persistence(prior, odt, tdt, cur):
    return float(cur)


PREDICTORS = {"model": _model, "history only": _hist_only, "persistence": _persistence}

_last_half_life = None


def apply_params(params):
    """Set routeOptimizer constants. The bin cache depends on the half-life, so reset it when that changes."""
    global _last_half_life
    for k, v in params.items():
        setattr(ro, k, v)
    hl = getattr(ro, "RECENCY_HALF_LIFE_DAYS")
    if hl != _last_half_life:
        ro._ctx.bins = {}
        _last_half_life = hl


def collect(cases, predictor):
    rows = []                                   # (ride, horizon, predicted, actual)
    for c in cases:
        prior = c["prior"]
        for odt, tdt, cur, act, h in c["items"]:
            rows.append((c["key"], h, predictor(prior, odt, tdt, cur), act))
    return rows


# ── scoring ──────────────────────────────────────────────────────────
def summarize(rows, args):
    if not rows:
        return None
    errs = [p - a for _, _, p, a in rows]
    hits = sum(1 for (_, _, p, a) in rows if abs(p - a) <= max(args.tol_min, args.tol_pct * a))
    return {
        "n": len(rows),
        "mae": statistics.fmean(abs(e) for e in errs),
        "med": statistics.median(abs(e) for e in errs),
        "bias": statistics.fmean(errs),
        "hit": 100.0 * hits / len(rows),
    }


def fmt_cell(s):
    return f"{s['mae']:5.1f} {s['hit']:5.1f}%" if s else "     -      -"


def report(cases, args):
    apply_params({})
    results = {name: collect(cases, fn) for name, fn in PREDICTORS.items()}
    names = list(PREDICTORS)

    print(f"Hit = within max({args.tol_min:g} min, {args.tol_pct * 100:g}% of the actual wait).")
    print("Each cell is: average error in minutes (MAE), then hit rate.\n")

    header = f"{'horizon':>8} {'n':>7}   " + "   ".join(f"{n:^13}" for n in names) + "   model bias"
    print(header)
    print("-" * len(header))
    for h in sorted({h for _, h, _, _ in results["model"]}):
        cells, model_s = [], None
        for name in names:
            s = summarize([r for r in results[name] if r[1] == h], args)
            cells.append(fmt_cell(s))
            if name == "model":
                model_s = s
        print(f"{h:>7g}h {model_s['n']:>7}   " + "   ".join(cells) + f"   {model_s['bias']:+6.1f}")
    allc = [summarize(results[n], args) for n in names]
    print("-" * len(header))
    print(f"{'ALL':>8} {allc[0]['n']:>7}   " + "   ".join(fmt_cell(s) for s in allc) + f"   {allc[0]['bias']:+6.1f}")
    print("(bias > 0 means the model predicts waits LONGER than reality, < 0 means shorter)\n")

    print("Model accuracy by ride (worst first):")
    by_ride = defaultdict(list)
    for r in results["model"]:
        by_ride[r[0]].append(r)
    table = sorted(((k, summarize(v, args)) for k, v in by_ride.items()), key=lambda kv: kv[1]["hit"])
    print(f"  {'ride':<18}{'n':>6}{'MAE':>8}{'hit%':>8}{'bias':>8}")
    for k, s in table:
        print(f"  {k:<18}{s['n']:>6}{s['mae']:>8.1f}{s['hit']:>7.1f}%{s['bias']:>+8.1f}")

    # Where is the model beaten by a dumber baseline? Those are the settings to fix.
    worse = []
    for h in sorted({h for _, h, _, _ in results["model"]}):
        m = summarize([r for r in results["model"] if r[1] == h], args)
        for other in ("history only", "persistence"):
            o = summarize([r for r in results[other] if r[1] == h], args)
            if o and o["mae"] < m["mae"] - 0.05:
                worse.append(f"  {h:g}h ahead: '{other}' (MAE {o['mae']:.1f}) beats the model (MAE {m['mae']:.1f})")
    if worse:
        print("\nWarning -- a simpler baseline beats the model here:")
        print("\n".join(worse))
    print()


# ── tuning ───────────────────────────────────────────────────────────
def tune(cases, args):
    days = sorted({c["day"] for c in cases})
    if len(days) < 6:
        print("Not enough evaluation days to tune with a hold-out. Use --eval-days with a larger number.")
        return
    split = max(1, int(len(days) * (1 - args.holdout)))
    train_days, hold_days = set(days[:split]), set(days[split:])
    train = [c for c in cases if c["day"] in train_days]
    hold = [c for c in cases if c["day"] in hold_days]
    print(f"Tuning on {len(train_days)} days, validating on the {len(hold_days)} most recent days.\n")

    keys = list(TUNE_GRID)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*TUNE_GRID.values())]
    current = {k: getattr(ro, k) for k in keys}

    def score(params, subset):
        apply_params(params)
        return summarize(collect(subset, _model), args)

    scored = []
    for i, p in enumerate(combos, 1):
        s = score(p, train)
        scored.append((s["hit"], -s["mae"], p, s))
        print(f"  [{i:>3}/{len(combos)}] hit {s['hit']:5.1f}%  MAE {s['mae']:5.2f}   {p}", flush=True)
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    print("\nTop 5 on training days:")
    for _, _, p, s in scored[:5]:
        print(f"  hit {s['hit']:5.1f}%  MAE {s['mae']:5.2f}   {p}")

    best = scored[0][2]
    cur_h, best_h = score(current, hold), score(best, hold)
    print("\nOn the held-out recent days (the honest test):")
    print(f"  current settings: hit {cur_h['hit']:5.1f}%  MAE {cur_h['mae']:5.2f}   {current}")
    print(f"  best settings:    hit {best_h['hit']:5.1f}%  MAE {best_h['mae']:5.2f}   {best}")

    if best_h["hit"] > cur_h["hit"] + 0.5 and best_h["mae"] <= cur_h["mae"]:
        print("\nThe best settings also win on unseen days. Worth applying:")
        for k, v in best.items():
            print(f"  {k} = {v!r}")
    else:
        print("\nThe 'best' settings do NOT clearly beat your current ones on unseen days,")
        print("so leave routeOptimizer.py as it is. (Winning only on training days = overfitting.)")
    apply_params(current)


# ── main ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-days", type=int, default=30, help="how many recent days to test on (per ride)")
    ap.add_argument("--min-prior-days", type=int, default=14, help="skip days with fewer earlier days of history")
    ap.add_argument("--horizons", type=float, nargs="+", default=[1, 2, 4, 6], help="hours ahead to predict")
    ap.add_argument("--origin-start", type=int, default=9, help="first origin hour (park-local)")
    ap.add_argument("--origin-end", type=int, default=19, help="last origin hour (park-local)")
    ap.add_argument("--origin-step-min", type=int, default=60, help="minutes between origins")
    ap.add_argument("--match-tol-min", type=float, default=10, help="max minutes between a requested time and the reading used for it")
    ap.add_argument("--tol-min", type=float, default=5, help="hit tolerance: absolute minutes")
    ap.add_argument("--tol-pct", type=float, default=0.15, help="hit tolerance: fraction of the actual wait")
    ap.add_argument("--skip-zeros", action="store_true", help="ignore cases where the live or actual wait is 0")
    ap.add_argument("--rides", nargs="*", help="only these ride keys, e.g. hulk velociCoaster")
    ap.add_argument("--window-days", type=int, default=ro.HISTORY_WINDOW_DAYS, help="how many days of history to download")
    ap.add_argument("--cache", help="pickle file to save/reuse the downloaded history")
    ap.add_argument("--tune", action="store_true", help="grid-search the tunable constants")
    ap.add_argument("--holdout", type=float, default=0.33, help="fraction of eval days kept unseen during --tune")
    args = ap.parse_args()

    histories = load_histories(args)
    if not histories:
        sys.exit("No ride history found.")
    print(f"Loaded {sum(len(h) for h in histories.values()):,} readings for {len(histories)} rides.")
    print_hour_diagnostic(histories)

    cases = build_cases(histories, args)
    n_items = sum(len(c["items"]) for c in cases)
    if not cases:
        sys.exit("No usable test cases. Try a smaller --min-prior-days or larger --match-tol-min.")
    print(f"Built {n_items:,} predictions to check across {len(cases)} ride-days.\n")

    if args.tune:
        tune(cases, args)
    else:
        report(cases, args)


if __name__ == "__main__":
    main()