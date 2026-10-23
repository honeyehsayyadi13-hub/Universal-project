# server.py
import threading

from flask import Flask, jsonify, request, send_from_directory

import Data
from routeOptimizer import compute_and_print_route, warm_history_cache

app = Flask(__name__, static_folder="static", static_url_path="")

# Keep a lightweight background thread running so ride_waits / ride_open
# stay warm for routeOptimizer even between page loads.  The thread now
# sleeps 60 s (not 5 s) because /api/rides does its own on-demand fetch
# with a 30 s cache -- the thread is only a backstop, not the live feed.
threading.Thread(target=Data.update_backend, daemon=True).start()


def _warm():
    try:
        warm_history_cache()
        print("history warm-up finished", flush=True)
    except Exception:
        app.logger.exception("history warm-up failed")


threading.Thread(target=_warm, daemon=True).start()


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/rides")
def rides():
    payload = Data.get_live_wait_times()
    Data._sync_legacy_dicts(payload)
    # If we're past closing time, don't trust the source — mark everything closed.
    park_hours = Data.get_park_close_time()
    if park_hours:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        close_hour, close_minute = park_hours
        if (2, 0) <= (now.hour, now.minute) < (13, 0):
            payload = {k: {**v, "is_open": False, "waittime": 0} for k, v in payload.items()}

    return jsonify(payload)


_last_route = {}


@app.route("/api/route", methods=["POST"])
def route():
    payload = request.json or {}
    _last_route["payload"] = payload
    _last_route["result_length"] = "still computing (or crashed)"
    _last_route.pop("error", None)

    # Pull today's real Halloween Horror Night's closing time if it's available;
    # compute_and_print_route falls back to 2 PM on its own if this is None.
    park_hours = Data.get_park_close_time()
    close_hour, close_minute = park_hours if park_hours else (None, None)
    try:
        result = compute_and_print_route(
            payload.get("ride_counts", {}),
            ride_locked=payload.get("ride_locked"),
            closed_ride_keys=payload.get("closed_ride_keys"),
            breaks=payload.get("breaks"),
            start_key=payload.get("start_key", "entrance"),
            live_waits=payload.get("live_waits"),
            time_pinned=payload.get("time_pinned"),
            max_counts=payload.get("max_counts"),
            close_hour=close_hour,
            close_minute=close_minute,
            override_closed_keys=payload.get("override_closed_keys"),
            ride_priority_order=payload.get("ride_priority_order"),
            completed_counts=payload.get("completed_counts"),
            )
    except Exception as e:
        app.logger.exception("route computation failed")
        _last_route["error"] = str(e)
        return jsonify({"error": str(e)}), 500

    _last_route["result_length"] = None if result is None else len(result)
    _last_route["first_stops"] = (result or [])[:3]
    if result is None:
        return jsonify({"error": "Route could not be computed (backend data unreachable)."}), 502

    return jsonify(result)


@app.route("/api/park-hours")
def park_hours():
    close = Data.get_park_close_time()
    return jsonify({"close_minutes": close[0] * 60 + close[1] if close else None})


@app.route("/api/debug-last")
def debug_last():
    return jsonify(_last_route)


@app.route("/api/debug")
def debug():
    from datetime import datetime
    import routeOptimizer as ro
    out = {"new_optimizer_code_loaded": hasattr(ro, "_op_date")}
    try:
        now = datetime.now(ro.PARK_TIMEZONE).replace(tzinfo=None)
        out["park_time_now"] = now.isoformat()
        close = Data.get_park_close_time()
        out["park_close"] = close
        if hasattr(ro, "_op_date"):
            day0 = datetime.combine(ro._op_date(now), datetime.min.time())
            out["s0_minutes"] = round((now - day0).total_seconds() / 60)
        if close:
            c = close[0] * 60 + close[1]
            out["closing_minutes_expected"] = c + 1440 if c <= 360 else c
        key_to_id, _ = ro._load_ride_id_map()
        live = Data.get_live_wait_times()
        out["live_not_in_supabase"] = sorted(k for k in live if k not in key_to_id)
        out["supabase_not_in_live"] = sorted(k for k in key_to_id if k not in live and k != "Entrance")
        out["walk_rows"] = len(ro._load_walk_times())
        out["durations_rows"] = len(ro._load_ride_durations())
        ids = [i for k, i in key_to_id.items() if k != "Entrance"]
        hist = ro._load_wait_history(ids)
        out["history_samples_per_ride_id"] = {str(i): len(hist.get(i, [])) for i in ids}
        counts = {k: 1 for k in key_to_id if k != "Entrance"}
        res = ro.compute_and_print_route(
            counts,
            live_waits={k: v["waittime"] for k, v in live.items()},
            close_hour=close[0] if close else None,
            close_minute=close[1] if close else None,
        )
        out["route_result_length"] = None if res is None else len(res)
        out["route_first_stops"] = (res or [])[:3]
    except Exception as e:
        import traceback
        out["error"] = repr(e)
        out["traceback"] = traceback.format_exc()[-1500:]
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)