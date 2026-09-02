from flask import Flask, jsonify, request, send_from_directory
from routeOptimizer import get_current_waits, compute_and_print_route

app = Flask(__name__, static_folder="static", static_url_path="")

@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/rides")
def rides():
    return jsonify(get_current_waits())

@app.route("/api/route", methods=["POST"])
def route():
    payload = request.json
    result = compute_and_print_route(
        payload["ride_counts"],
        ride_locked=payload.get("ride_locked"),
        closed_ride_keys=payload.get("closed_ride_keys"),
        breaks=payload.get("breaks"),
        start_key=payload.get("start_key", "entrance"),
        live_waits=payload.get("live_waits"),
    )
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)