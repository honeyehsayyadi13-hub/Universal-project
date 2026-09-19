# data.py
import os
import requests
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

_cache: dict = {}          # last successful payload
_cache_ts: float = 0.0     # unix timestamp of that fetch
CACHE_TTL = 30             # seconds before we re-hit queue-times.com

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

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UniversalRoutePlanner/1.0; +https://universal-project.onrender.com)",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException:
        return _cache
    except ValueError:
        return _cache

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
            except Exception:
                pass

    if result:                 # only promote to cache if we got real data
        _cache    = result
        _cache_ts = now

    return _cache

ride_waits: dict = {}
ride_open:  dict = {}


def _sync_legacy_dicts(payload: dict) -> None:
    """Keep the module-level dicts in sync after each live fetch."""
    for ride_id, info in payload.items():
        ride_waits[ride_id] = info["waittime"]
        ride_open[ride_id]  = info["is_open"]


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
        except Exception:
            pass
        time.sleep(60)


# ---------------------------------------------------------------------------
# Park operating hours (Islands of Adventure), via ThemeParks.wiki.
# queue-times.com (used above for live waits) doesn't expose park hours at
# all, so this hits a separate free public API. Cached per-calendar-date so
# a route request doesn't refetch the whole schedule every time.
# ---------------------------------------------------------------------------

THEMEPARKS_API_BASE = "https://api.themeparks.wiki/v1"
PARK_HOURS_CACHE_TTL = 3600     # re-check once an hour; hours rarely change intra-day

_ioa_entity_id_cache = None
_park_hours_cache: dict = {}
_park_hours_cache_ts: float = 0.0


def _themeparks_headers():
    return {
        "User-Agent": "Mozilla/5.0 (compatible; UniversalRoutePlanner/1.0; +https://universal-project.onrender.com)",
        "Accept": "application/json",
    }


def _resolve_ioa_entity_id():
    """Look up Universal's Islands of Adventure's entityID from the
    ThemeParks.wiki destinations list. Cached in-process -- this practically
    never changes, so one lookup per server lifetime is plenty."""
    global _ioa_entity_id_cache
    if _ioa_entity_id_cache:
        return _ioa_entity_id_cache

    try:
        resp = requests.get(f"{THEMEPARKS_API_BASE}/destinations", headers=_themeparks_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError):
        return None

    for destination in data.get("destinations", []):
        for park in destination.get("parks", []):
            if "islands of adventure" in park.get("name", "").lower():
                _ioa_entity_id_cache = park["id"]
                return _ioa_entity_id_cache

    return None


def get_park_close_time(for_date=None):
    """
    Return (hour, minute) that Islands of Adventure closes on `for_date`
    (defaults to today), fetched live from ThemeParks.wiki.

    Returns None if it couldn't be determined -- unreachable API, park not
    found, or no OPERATING schedule entry for that date -- in which case
    the caller should fall back to a hardcoded default close time instead.
    """
    global _park_hours_cache, _park_hours_cache_ts

    target_date = (for_date or datetime.now()).date()
    now = time.time()

    if (
        _park_hours_cache.get("date") == target_date.isoformat()
        and (now - _park_hours_cache_ts) < PARK_HOURS_CACHE_TTL
    ):
        return _park_hours_cache["close_hour"], _park_hours_cache["close_minute"]

    entity_id = _resolve_ioa_entity_id()
    if not entity_id:
        return None

    try:
        resp = requests.get(
            f"{THEMEPARKS_API_BASE}/entity/{entity_id}/schedule",
            headers=_themeparks_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError):
        return None

    for entry in data.get("schedule", []):
        if entry.get("date") != target_date.isoformat():
            continue
        if entry.get("type") != "OPERATING":
            continue
        closing_raw = entry.get("closingTime")
        if not closing_raw:
            continue
        try:
            closing_dt = datetime.fromisoformat(closing_raw)
        except ValueError:
            continue
        _park_hours_cache = {
            "date": target_date.isoformat(),
            "close_hour": closing_dt.hour,
            "close_minute": closing_dt.minute,
        }
        _park_hours_cache_ts = now
        return closing_dt.hour, closing_dt.minute

    return None