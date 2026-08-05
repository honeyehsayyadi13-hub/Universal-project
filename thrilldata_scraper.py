import requests
import re
import json
import psycopg2
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import random
 
 
DB = {
    "host": "localhost",
    "database": "thrill",
    "user": "postgres",
    "password": "password"
}
 
 
PARK_WAITS_URL = "https://www.thrill-data.com/wa/park-waits/islands-of-adventure"
 
 
def normalize_name(name):
    """Lowercase, strip punctuation, collapse whitespace - for fuzzy-matching
    thrill-data's ride names against your own DB's ride names, since the
    exact wording/subtitle sometimes differs slightly."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
 
 
# your database's ride names, keyed by ride_id - used to match against
# whatever thrill-data returns, since their exact wording can differ
# slightly (e.g. "Hogwarts Express" vs "Hogwarts Express - Hogsmeade Station")
DB_RIDE_NAMES = {
    1:  "The Incredible Hulk Coaster",
    2:  "Storm Force Accelatron",
    3:  "Doctor Doom's Fearfall",
    4:  "The Amazing Adventures of Spider-Man",
    5:  "Popeye & Bluto's Bilge-Rat Barges",
    6:  "Dudley Do-Right's Ripsaw Falls",
    7:  "Skull Island: Reign of Kong",
    8:  "Jurassic World VelociCoaster",
    9:  "Jurassic Park River Adventure",
    10: "Hogwarts Express",
    11: "Flight of the Hippogriff",
    12: "Hagrid's Magical Creatures Motorbike Adventure",
    13: "The High in the Sky Seuss Trolley Train Ride",
    14: "Caro-Seuss-el",
    15: "One Fish, Two Fish, Red Fish, Blue Fish",
    16: "The Cat in the Hat",
    17: "Harry Potter and the Forbidden Journey",
}
 
NORMALIZED_DB_NAMES = {
    ride_id: normalize_name(name) for ride_id, name in DB_RIDE_NAMES.items()
}
 
 
def match_ride_id(thrilldata_name):
    """
    Tries to match a ride name from thrill-data's table to one of your
    DB_RIDE_NAMES. Returns the ride_id, or None if nothing matches
    closely enough.
 
    Tries exact normalized match first, then falls back to a
    substring match in either direction (handles subtitle differences
    like "Hogwarts Express" vs "Hogwarts Express - Hogsmeade Station").
    """
    norm = normalize_name(thrilldata_name)
 
    for ride_id, db_norm in NORMALIZED_DB_NAMES.items():
        if norm == db_norm:
            return ride_id
 
    for ride_id, db_norm in NORMALIZED_DB_NAMES.items():
        if norm.startswith(db_norm) or db_norm.startswith(norm):
            return ride_id
 
    return None
 
 
# kept for the historical/per-ride endpoints (rideavg etc.) - fill in
# "title" slugs here only for rides you want day-by-day history for.
# Not needed anymore for current wait times; see fetch_current_park_waits().
RIDES = {
    1:  {"park": "islands-of-adventure", "title": "the-incredible-hulk-coaster",              "tdid": None},
    2:  {"park": "islands-of-adventure", "title": "storm-force-accelatron",                    "tdid": None},
    3:  {"park": "islands-of-adventure", "title": "doctor-dooms-fearfall",                      "tdid": None},
    4:  {"park": "islands-of-adventure", "title": "the-amazing-adventures-of-spider-man",       "tdid": None},
    5:  {"park": "islands-of-adventure", "title": "popeye-blutos-bilge-rat-barges",              "tdid": None},
    6:  {"park": "islands-of-adventure", "title": "dudley-do-rights-ripsaw-falls",               "tdid": None},
    7:  {"park": "islands-of-adventure", "title": "skull-island-reign-of-kong",                  "tdid": None},
    8:  {"park": "islands-of-adventure", "title": "jurassicworldvelocicoaster",                  "tdid": 2015},
    9: {"park": "islands-of-adventure", "title": "jurassicparkriveradventure", "tdid": None},
    10: {"park": "islands-of-adventure", "title": "hogwarts-express",                             "tdid": None},
    11: {"park": "islands-of-adventure", "title": "flight-of-the-hippogriff",                      "tdid": None},
    12: {"park": "islands-of-adventure", "title": "hagrids-magical-creatures-motorbike-adventure",  "tdid": None},
    13: {"park": "islands-of-adventure", "title": "high-in-the-sky-seuss-trolley-train-ride",       "tdid": None},
    14: {"park": "islands-of-adventure", "title": "caro-seuss-el",                                   "tdid": None},
    15: {"park": "islands-of-adventure", "title": "one-fish-two-fish-red-fish-blue-fish",             "tdid": None},
    16: {"park": "islands-of-adventure", "title": "the-cat-in-the-hat",                                "tdid": None},
    17: {"park": "islands-of-adventure", "title": "harry-potter-and-the-forbidden-journey",             "tdid": None},
}
 
 
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.thrill-data.com/"
})
 
 
# matches: Plotly.newPlot(  "some-id",  [ ...traces... ],  {layout...}
# group(1) is just the array of trace objects
NEWPLOT_RE = re.compile(
    r'Plotly\.newPlot\(\s*"[^"]+"\s*,\s*(\[.*?\])\s*,\s*\{',
    re.S
)
 
 
def fetch_rideavg(park, title, date_str, tag="daily"):
    """
    Hits the /waits/graph/quick/rideavg endpoint for a single ride/day
    and returns the raw JSON response (dict with a "plot1" html string).
    """
    url = "https://www.thrill-data.com/waits/graph/quick/rideavg"
    params = {
        "park": park,
        "title": title,
        "dateStart": date_str,
        "tag": tag
    }
 
    resp = session.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()
 
 
def extract_traces(plot_html):
    """
    Given the html string from response["plot1"], pulls out and parses
    the JSON array of Plotly traces passed into Plotly.newPlot(...).
 
    Returns a list of trace dicts, each with at least "name", "x", "y".
    """
    match = NEWPLOT_RE.search(plot_html)
 
    if not match:
        raise ValueError("Could not find Plotly.newPlot(...) call in response")
 
    traces_json = match.group(1)
    traces = json.loads(traces_json)
    return traces
 
 
def traces_to_rows(traces, ride_id, wanted_names=("Posted Wait",)):
    """
    Converts parsed Plotly traces into flat rows ready for the database.
 
    wanted_names filters which lines to keep - by default only the
    actual posted wait time (skip "Typical Wait", which is a historical
    average line, not a real observation).
    """
    rows = []
 
    for trace in traces:
        name = trace.get("name", "")
 
        if wanted_names and name not in wanted_names:
            continue
 
        xs = trace.get("x", [])
        ys = trace.get("y", [])
 
        for x, y in zip(xs, ys):
            if y is None:
                continue
 
            timestamp = datetime.fromisoformat(x)
 
            rows.append({
                "ride_id": ride_id,
                "timestamp": timestamp,
                "waittime": y,
                "issue_with_ride": False
            })
 
    return rows
 
 
def insert_rows(rows):
 
    if not rows:
        return
 
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
 
    for r in rows:
        cur.execute(
            """
            INSERT INTO ride_waits
            (
                ride_id,
                timestamp,
                waittime,
                issue_with_ride
            )
            VALUES (%s,%s,%s,%s)
            """,
            (
                r["ride_id"],
                r["timestamp"],
                r["waittime"],
                r["issue_with_ride"]
            )
        )
 
    conn.commit()
    cur.close()
    conn.close()
 
 
def get_current_wait(ride_id, date=None):
    """
    Fetches the most recent "Posted Wait" data point for a single ride
    and returns it as {"ride_id", "title", "timestamp", "waittime"}.
 
    thrill-data's rideavg endpoint returns the whole day's wait-time
    curve, not just "right now" - so "current" here means the last
    non-null point in today's Posted Wait trace, which is effectively
    the most recent reading they have.
    """
    info = RIDES[ride_id]
 
    if date is None:
        date = datetime.now()
 
    date_str = date.strftime("%Y-%m-%d")
 
    data = fetch_rideavg(info["park"], info["title"], date_str)
 
    plot_html = data.get("plot1", "")
    if not plot_html:
        raise ValueError(f"No plot1 data returned for {info['title']}")
 
    traces = extract_traces(plot_html)
 
    posted = None
    for trace in traces:
        if trace.get("name") == "Posted Wait":
            posted = trace
            break
 
    if posted is None:
        raise ValueError(f"No 'Posted Wait' trace found for {info['title']}")
 
    xs = posted.get("x", [])
    ys = posted.get("y", [])
 
    # walk backwards to find the last point that actually has a value
    for x, y in zip(reversed(xs), reversed(ys)):
        if y is not None:
            return {
                "ride_id": ride_id,
                "title": info["title"],
                "timestamp": datetime.fromisoformat(x),
                "waittime": y
            }
 
    raise ValueError(f"No non-null wait values found for {info['title']}")
 
 
def get_all_current_waits(ride_ids=None, delay_range=(1, 2.5)):
    """
    Fetches the current wait time for every ride in RIDES (or a subset
    via ride_ids). Prints progress as it goes and returns two lists:
    (successes, failures).
 
    successes: list of dicts from get_current_wait
    failures:  list of {"ride_id", "title", "error"} - use this to spot
               which slugs in RIDES are wrong and need fixing.
    """
    if ride_ids is None:
        ride_ids = list(RIDES.keys())
 
    successes = []
    failures = []
 
    for ride_id in ride_ids:
        info = RIDES[ride_id]
 
        try:
            result = get_current_wait(ride_id)
            successes.append(result)
            print(f"OK   {info['title']:<45} {result['waittime']:>3} min  ({result['timestamp']})")
 
        except Exception as e:
            failures.append({
                "ride_id": ride_id,
                "title": info["title"],
                "error": str(e)
            })
            print(f"FAIL {info['title']:<45} {e}")
 
        time.sleep(random.uniform(*delay_range))
 
    return successes, failures
 
 
def fetch_current_park_waits(park="islands-of-adventure"):
    """
    Hits the /wa/park-waits/<park>?fmt=table endpoint - the same one
    the site's "Wait Times" modal uses - and returns the raw HTML table
    for every reporting ride in the park, in a single request.
    """
    url = f"{PARK_WAITS_URL if park == 'islands-of-adventure' else 'https://www.thrill-data.com/wa/park-waits/' + park}"
    params = {"fmt": "table"}
 
    # the browser only got a real response when the request looked like
    # an XHR call rather than a plain page visit - this header mimics that
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, */*; q=0.01",
        "Referer": "https://www.thrill-data.com/waits/park/uor/islands-of-adventure/"
    }
 
    resp = session.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text
 
 
def parse_current_park_waits(html):
    """
    Parses the park-waits table HTML into a list of dicts:
    {"thrilldata_name", "slug", "wait", "avg", "ride_id"}
 
    ride_id is filled in via match_ride_id() where possible; it will be
    None for rides thrill-data reports that aren't in your DB_RIDE_NAMES
    (e.g. Pteranodon Flyers, Ollivanders Experience - not in your
    original 17), which is fine, just skip/handle those as you like.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table#rt-live tbody tr")
 
    results = []
 
    for tr in rows:
        wait_raw = tr.get("data-wait")
        avg_raw = tr.get("data-avg")
 
        fav_btn = tr.select_one("button.rf-fav")
        slug = fav_btn.get("data-slug") if fav_btn else None
        display_name = fav_btn.get("data-name") if fav_btn else tr.get("data-name")
 
        wait = int(wait_raw) if wait_raw not in (None, "") else None
        avg = int(avg_raw) if avg_raw not in (None, "") else None
 
        results.append({
            "thrilldata_name": display_name,
            "slug": slug,
            "wait": wait,
            "avg": avg,
            "ride_id": match_ride_id(display_name) if display_name else None
        })
 
    return results
 
 
def get_current_waits_for_park(park="islands-of-adventure"):
    """
    One-call convenience function: fetches and parses current wait
    times for every ride in the park. Prints a summary and returns
    the parsed list (see parse_current_park_waits for the shape).
    """
    html = fetch_current_park_waits(park)
    results = parse_current_park_waits(html)
 
    matched = [r for r in results if r["ride_id"] is not None]
    unmatched = [r for r in results if r["ride_id"] is None]
 
    for r in matched:
        print(f"OK   ride_id {r['ride_id']:<3} {r['thrilldata_name']:<45} {r['wait']:>3} min")
 
    if unmatched:
        print("\nNot in your DB_RIDE_NAMES (skipped, ride_id=None):")
        for r in unmatched:
            print(f"     {r['thrilldata_name']:<45} {r['wait']:>3} min  (slug: {r['slug']})")
 
    print(f"\n{len(matched)} matched to a ride_id, {len(unmatched)} unmatched, {len(results)} total reporting.")
 
    return results
 
 
def scrape_date(ride_id, date):
    """
    Scrapes a single ride for a single date and inserts the rows.
    Returns the number of rows inserted.
    """
    info = RIDES[ride_id]
    date_str = date.strftime("%Y-%m-%d")
 
    data = fetch_rideavg(info["park"], info["title"], date_str)
 
    plot_html = data.get("plot1", "")
    if not plot_html:
        print(f"No plot1 data for ride {ride_id} on {date_str}")
        return 0
 
    traces = extract_traces(plot_html)
    rows = traces_to_rows(traces, ride_id)
 
    insert_rows(rows)
    return len(rows)
 
 
def scrape_range(start, end, ride_ids=None):
 
    if ride_ids is None:
        ride_ids = list(RIDES.keys())
 
    date = start
 
    while date <= end:
        print("DATE:", date)
 
        for ride_id in ride_ids:
            info = RIDES[ride_id]
 
            try:
                n = scrape_date(ride_id, date)
                print(f"  {info['title']}: {n} rows")
 
            except Exception as e:
                print(f"  FAILED {info['title']} on {date}: {e}")
 
            # small polite delay between requests
            time.sleep(random.uniform(1, 2.5))
 
        date += timedelta(days=1)
 
 
if __name__ == "__main__":
 
    print("Fetching current wait times for the whole park (1 request)...\n")
 
    results = get_current_waits_for_park("islands-of-adventure")
 
    # to insert the matched rides into your database, uncomment:
    #
    # now = datetime.now()
    # rows = [
    #     {
    #         "ride_id": r["ride_id"],
    #         "timestamp": now,
    #         "waittime": r["wait"],
    #         "issue_with_ride": False
    #     }
    #     for r in results
    #     if r["ride_id"] is not None and r["wait"] is not None
    # ]
    # insert_rows(rows)
 