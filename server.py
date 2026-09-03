# server.py
import threading

from flask import Flask, jsonify, request, send_from_directory

import Data
from routeOptimizer import compute_and_print_route

app = Flask(__name__, static_folder="static", static_url_path="")

# Keep a lightweight background thread running so ride_waits / ride_open
# stay warm for routeOptimizer even between page loads.  The thread now
# sleeps 60 s (not 5 s) because /api/rides does its own on-demand fetch
# with a 30 s cache -- the thread is only a backstop, not the live feed.
threading.Thread(target=Data.update_backend, daemon=True).start()


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/rides")
def rides():
    """
    Live wait times fetched on-demand from queue-times.com (cached 30 s).

    Fetching on-demand is more reliable than a background thread on
    Render free tier: the service spins down after inactivity, and a
    daemon thread that was alive before spin-down does NOT automatically
    restart on wake-up.  The first request after wake-up triggers a
    fresh fetch here, so the UI always gets real data instead of {}.
    """
    payload = Data.get_live_wait_times()
    # Also sync the legacy dicts so routeOptimizer sees fresh data
    # if it reads ride_waits/ride_open before the background thread
    # has had a chance to run.
    Data._sync_legacy_dicts(payload)
    return jsonify(payload)


@app.route("/api/route", methods=["POST"])
def route():
    payload = request.json or {}
    try:
        result = compute_and_print_route(
            payload.get("ride_counts", {}),
            ride_locked=payload.get("ride_locked"),
            closed_ride_keys=payload.get("closed_ride_keys"),
            breaks=payload.get("breaks"),
            start_key=payload.get("start_key", "entrance"),
            live_waits=payload.get("live_waits"),
        )
    except Exception as e:
        app.logger.exception("route computation failed")
        return jsonify({"error": str(e)}), 500

    if result is None:
        return jsonify({"error": "Route could not be computed (backend data unreachable)."}), 502

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)