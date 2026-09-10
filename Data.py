# data.py
import requests
from datetime import datetime
import time

# ---------------------------------------------------------------------------
# On-demand fetch with a short cache.
# The old approach (background thread polling every 5s) is unreliable on
# Render free tier: the service spins down after inactivity, the daemon
# thread may die silently on wake-up, and outbound HTTP from a sleeping
# container often fails on the first attempt -- leaving ride_waits empty
# forever and /api/rides returning {}. Fetching on-demand and caching the
# result for 30 s is simpler, more reliable, and uses far less CPU.
# ---------------------------------------------------------------------------

_cache: dict = {}          # last successful payload
_cache_ts: float = 0.0     # unix timestamp of that fetch
_park_hours_cache: dict = {}   # {"open_min": int, "close_min": int}
_park_hours_ts: float = 0.0    # unix timestamp of last successful hours fetch
CACHE_TTL = 30             # seconds before we re-hit queue-times.com
PARK_HOURS_CACHE_TTL = 6 * 3600   # hours change rarely -- refetch every 6h
THEMEPARKS_ENTITY_ID = "267615cc-8943-4c2a-ae2c-5da728ca591f"  # Islands of Adventure

RIDE_NAME_MAP = {
    "The Incredible Hulk Coaster®":                    "hulk",
    "Storm Force Accelatron®":                         "stormForce",
    "Doctor Doom's Fearfall®":                         "doctorDoom",
    "The Amazing Adventures of Spider-Man®":           "spiderMan",
    "Popeye & Bluto's Bilge-Rat Barges®":             "bilgeRat",
    "Dudley Do-Right's Ripsaw Falls®":                 "ripsawFalls",
    "Skull Island: Reign of Kong":                     "skullIsland",
    "Jurassic World VelociCoaster":                    "velociCoaster",
    "Jurassic Park River Adventure":                   "riverAdventure",
    "Harry Potter and the Forbidden Journey™":         "harryPotter",
    "Hogwarts Express™ - Hogsmeade™ Station":          "hogwartsTrain",
    "Flight of the Hippogriff™":                       "hippogriff",
    "Hagrid's Magical Creatures Motorbike Adventure™": "hagrid",
    "The High in the Sky Seuss Trolley Train Ride!™":  "drSeussAirRide",
    "Caro-Seuss-el™":                                  "caroSeussel",
    "One Fish, Two Fish, Red Fish, Blue Fish™":        "oneFishtwoFish",
    "The Cat in The Hat™":                             "catInTheHat",
}


def get_live_wait_times() -> dict:
    """
    Return {ride_id: {"waittime": int, "is_open": bool}, ...}.

    Results are cached for CACHE_TTL seconds so repeated fast page loads
    don't hammer queue-times.com, while still feeling live to the user.
    On a fetch failure the last successful cache is returned so the UI
    keeps showing real data instead of going blank.
    """
    global _cache, _cache_ts

    now = time.time()
    if _cache and (now - _cache_ts) < CACHE_TTL:
        return _cache

    url = "https://queue-times.com/parks/64/queue_times.json"
    # Some sites reject the default python-requests User-Agent (403), which
    # would otherwise look identical to a timeout/network failure. Sending a
    # normal browser-ish UA avoids that class of silent failure.
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UniversalRoutePlanner/1.0; +https://universal-project.onrender.com)",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"[data] fetch failed: {e!r} (status={status})")
        return _cache          # stale cache beats an empty response
    except ValueError as e:
        print(f"[data] JSON parse failed: {e}")
        return _cache
    try:
        import re
        def _parse_time(raw):
            if raw is None:
                return None
            s = str(raw).strip()
            if 'T' in s:           # ISO-8601 — grab the HH:MM portion
                try:
                    tp = s.split('T')[1][:5]
                    return int(tp[:2]) * 60 + int(tp[3:5])
                except Exception:
                    return None
            m = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)?', s, re.IGNORECASE)
            if m:
                h, mn, p = int(m.group(1)), int(m.group(2)), (m.group(3) or '').upper()
                if p == 'PM' and h != 12: h += 12
                if p == 'AM' and h == 12: h = 0
                return h * 60 + mn
            return None
        open_v  = _parse_time(data.get('opening_time') or data.get('open_time'))
        close_v = _parse_time(data.get('closing_time') or data.get('close_time'))
        if open_v  is not None: _park_hours_cache['open_min']  = open_v
        if close_v is not None: _park_hours_cache['close_min'] = close_v
    except Exception as e:
        print(f"[data] park hours parse error: {e}")
    result: dict = {}
    for land in data.get("lands", []):
        for ride in land.get("rides", []):
            try:
                name    = ride["name"]
                ride_id = RIDE_NAME_MAP.get(name)
                if ride_id:
                    result[ride_id] = {
                        "waittime": ride["wait_time"],
                        "is_open":  ride["is_open"],
                    }
            except Exception as e:
                print(f"[data] skipping malformed ride entry {ride!r}: {e}")

    if result:                 # only promote to cache if we got real data
        _cache    = result
        _cache_ts = now
    else:
        print("[data] fetch succeeded but 0 rides matched RIDE_NAME_MAP "
              "-- check for a name/encoding mismatch against the live API")

    return _cache


# ---------------------------------------------------------------------------
# Legacy aliases kept so routeOptimizer (and any other module that imports
# Data.ride_waits / Data.ride_open directly) doesn't break.
# They're populated lazily on the first /api/rides call rather than by a
# background thread, which is fine because routeOptimizer reads them after
# the frontend has already loaded the page (and therefore after at least
# one /api/rides call has warmed the cache).
# ---------------------------------------------------------------------------

ride_waits: dict = {}
ride_open:  dict = {}


def _sync_legacy_dicts(payload: dict) -> None:
    """Keep the module-level dicts in sync after each live fetch."""
    for ride_id, info in payload.items():
        ride_waits[ride_id] = info["waittime"]
        ride_open[ride_id]  = info["is_open"]

def _fetch_park_hours():
    """Fetch today's operating hours from the ThemeParks.wiki API and
    populate _park_hours_cache. Cheap on-demand fetch, cached for
    PARK_HOURS_CACHE_TTL seconds since hours don't change intraday."""
    global _park_hours_ts
    now = time.time()
    if _park_hours_cache and (now - _park_hours_ts) < PARK_HOURS_CACHE_TTL:
        return

    url = f"https://api.themeparks.wiki/v1/entity/{THEMEPARKS_ENTITY_ID}/schedule"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UniversalRoutePlanner/1.0; +https://universal-project.onrender.com)",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[data] park hours fetch failed: {e!r}")
        return
    except ValueError as e:
        print(f"[data] park hours JSON parse failed: {e}")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    for entry in data.get("schedule", []):
        if entry.get("date") == today_str and entry.get("type") == "OPERATING":
            try:
                open_dt = datetime.fromisoformat(entry["openingTime"])
                close_dt = datetime.fromisoformat(entry["closingTime"])
            except (KeyError, ValueError) as e:
                print(f"[data] couldn't parse today's schedule entry: {e}")
                return
            _park_hours_cache["open_min"] = open_dt.hour * 60 + open_dt.minute
            _park_hours_cache["close_min"] = close_dt.hour * 60 + close_dt.minute
            _park_hours_ts = now
            return

    print("[data] no OPERATING schedule entry found for today -- using fallback hours")


def get_park_hours() -> dict:
    """Return {"open_min": int, "close_min": int} in minutes since midnight.
    Falls back to 9 AM / 8 PM if the live API has not provided hours yet."""
    _fetch_park_hours()
    return {
        "open_min":  _park_hours_cache.get("open_min",   9 * 60),
        "close_min": _park_hours_cache.get("close_min", 20 * 60),
    }

def update_backend():
    """
    Retained for any caller that still does
    `threading.Thread(target=Data.update_backend, ...).start()`.
    Now polls at 60 s (not 5 s) since /api/rides does its own on-demand
    fetch; this thread's only job is to keep ride_waits/ride_open warm
    for routeOptimizer between page loads.
    """
    while True:
        try:
            payload = get_live_wait_times()
            _sync_legacy_dicts(payload)
        except Exception as e:
            print(f"[data] update_backend unexpected error: {e}")
        time.sleep(60)


# ---------------------------------------------------------------------------
# Convenience: log current day/time (matches original module-level prints)
# ---------------------------------------------------------------------------
_now = datetime.now()
print(_now.strftime("%A"))
print(_now.strftime("%H:%M:%S"))