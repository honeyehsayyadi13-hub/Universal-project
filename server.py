import threading

from flask import Flask, jsonify, request, send_from_directory

import Data
from routeOptimizer import compute_and_print_route

app = Flask(__name__, static_folder="static", static_url_path="")

# Start the live queue-times.com poller as soon as this module is imported
# (not inside `if __name__ == "__main__":`) so it also runs when the app is
# served by a WSGI server like gunicorn (e.g. `gunicorn server:app`), which
# imports this module but never executes that block. Without this thread
# running, Data.ride_waits / Data.ride_open never get populated on the
# deployed server, and /api/rides has nothing live to report.
threading.Thread(target=Data.update_backend, daemon=True).start()


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/rides")
def rides():
    """
    Live wait times, straight from Data.py's in-memory dicts (populated by
    the background poller above from queue-times.com every 5s).

    NOTE: this is deliberately NOT routeOptimizer.get_current_waits(),
    which reads the Supabase `ride_waits` table -- that table is the
    historical log the route optimizer trains predictions on, not a live
    feed, and nothing repopulates it in real time on its own. Serving it
    from /api/rides would show stale/"hardcoded"-looking numbers instead
    of what the park is actually reporting right now.
    """
    return jsonify({
        ride_id: {
            "waittime": wait,
            "is_open": Data.ride_open.get(ride_id),
        }
        for ride_id, wait in Data.ride_waits.items()
    })


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
        # Surface real backend errors as a real HTTP error instead of
        # letting the frontend hang on "Generating..." forever.
        app.logger.exception("route computation failed")
        return jsonify({"error": str(e)}), 500

    if result is None:
        # compute_and_print_route() returns None only when it couldn't run
        # at all (e.g. Supabase unreachable) -- treat that as a real error,
        # distinct from [] ("ran fine, nothing fit").
        return jsonify({"error": "Route could not be computed (backend data unreachable)."}), 502

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)