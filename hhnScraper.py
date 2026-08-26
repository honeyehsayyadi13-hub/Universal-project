"""
Pulls live Halloween Horror Nights Orlando wait times from Thrill Data and
uploads them to the `ride_waits` table in Supabase.

How it works
------------
Thrill Data server-renders each ride's *current* wait time straight into the
page as part of an embedded Plotly chart (no separate API call needed). We:

  1. Download the HHN page HTML.
  2. Find every embedded Plotly chart on the page and decode its data.
  3. Pick the bar chart whose ride names best match the rides we track in
     Supabase -- that's the "Live Waits" chart.
  4. Match each scraped ride name to a `rides.id` (names on the site are
     often longer/slightly different than what's in our table, e.g.
     "Ozzy Osbourne: Prince of Darkness" vs. "Ozzy Osbourne", so we match on
     overlapping words rather than requiring an exact string match).
  5. Insert one row per matched ride into `ride_waits`.

If HHN isn't currently running (no event tonight, or it's the off-season),
Thrill Data won't have a live-waits chart at all -- the script just prints a
message and exits cleanly (exit code 0) so a GitHub Actions cron job doesn't
get marked as failed for running outside event hours.

Environment variables (set as GitHub Actions secrets, or in a local .env):
  SUPABASE_URL
  SUPABASE_KEY
"""

import array
import base64
import json
import os
import re
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HHN_URL = "https://www.thrill-data.com/hhn/orlando/2026"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Plotly's typed-array dtype codes -> Python `array` module type codes
PLOTLY_DTYPE_MAP = {
    "i1": "b", "i2": "h", "i4": "i", "i8": "q",
    "u1": "B", "u2": "H", "u4": "I", "u8": "Q",
    "f4": "f", "f8": "d",
}

STOPWORDS = {"a", "an", "and", "the", "of", "in", "on", "at", "presents"}


# ---------------------------------------------------------------------------
# Pulling raw chart data out of the page
# ---------------------------------------------------------------------------

def _decode_plotly_array(value):
    """Plotly encodes numeric arrays either as plain JSON lists, or (to save
    bandwidth) as base64 typed arrays like {"dtype": "i1", "bdata": "..."}.
    Handle both."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "bdata" in value:
        type_code = PLOTLY_DTYPE_MAP.get(value.get("dtype", "i1"), "b")
        raw = base64.b64decode(value["bdata"])
        return list(array.array(type_code, raw))
    raise ValueError(f"Unrecognized Plotly array payload: {value!r}")


def _extract_json_array(html, start_index):
    """Given the index of an opening '[' in the HTML, return the substring
    up through its matching ']', correctly skipping over brackets that show
    up inside quoted strings."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start_index, len(html)):
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return html[start_index : i + 1]
    raise ValueError("Unbalanced brackets while extracting a Plotly data array")


def _find_all_plotly_traces(html):
    """Every `Plotly.newPlot(...)` call on the page embeds a JSON array of
    one or more "traces" (bar charts, heatmaps, etc). Pull all of them out
    of the raw HTML."""
    traces = []
    search_from = 0
    marker = "Plotly.newPlot("
    while True:
        call_index = html.find(marker, search_from)
        if call_index == -1:
            break
        search_from = call_index + len(marker)
        try:
            comma_index = html.index(",", call_index)
            array_start = html.index("[", comma_index)
            array_text = _extract_json_array(html, array_start)
            traces.extend(json.loads(array_text))
        except (ValueError, json.JSONDecodeError):
            # Not every newPlot call is one we care about / can parse -- skip it.
            continue
    return traces


# ---------------------------------------------------------------------------
# Matching Thrill Data's ride names to our `rides` table
# ---------------------------------------------------------------------------

def _normalize(name):
    cleaned = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    return [w for w in cleaned.split() if w not in STOPWORDS]


def _build_ride_matcher(rides):
    """rides: list of {"id": ..., "name": ...} rows from Supabase.

    Matches on overlapping words rather than exact strings, since Thrill
    Data's names are usually longer than ours, e.g.
    "H.R. Bloodengutz Presents: A Halloween Fright-Tacular" (site) vs.
    "H.R. Bloodengutz" (our table).
    """
    parsed = [(r["id"], set(_normalize(r["name"]))) for r in rides]

    def match(scraped_name):
        scraped_words = set(_normalize(scraped_name))
        if not scraped_words:
            return None
        best_id, best_score = None, 0.0
        for ride_id, ride_words in parsed:
            if not ride_words:
                continue
            overlap = len(ride_words & scraped_words) / len(ride_words)
            if overlap > best_score:
                best_id, best_score = ride_id, overlap
        return best_id if best_score >= 0.9 else None

    return match


# ---------------------------------------------------------------------------
# Picking the right chart out of everything on the page
# ---------------------------------------------------------------------------

def _get_live_waits(html, known_ride_names):
    """Returns {scraped_ride_name: wait_minutes} for whichever bar chart on
    the page overlaps best with the ride names we actually track -- that's
    almost certainly the live wait times chart, regardless of exactly where
    it sits in the page's HTML."""
    candidates = []
    for trace in _find_all_plotly_traces(html):
        if trace.get("type") != "bar":
            continue
        if "customdata" not in trace or "x" not in trace:
            continue
        try:
            names = [item[0] for item in trace["customdata"]]
            waits = _decode_plotly_array(trace["x"])
        except (KeyError, IndexError, ValueError):
            continue
        if len(names) != len(waits) or not names:
            continue
        candidates.append(dict(zip(names, waits)))

    if not candidates:
        return {}

    known_norm = {" ".join(_normalize(n)) for n in known_ride_names}

    def score(waits_by_name):
        return sum(
            1
            for name in waits_by_name
            if " ".join(_normalize(name)) in known_norm
            or any(k and k in " ".join(_normalize(name)) for k in known_norm)
        )

    return max(candidates, key=score)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY are not set.")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rides = supabase.table("rides").select("id, name").execute().data
    if not rides:
        raise SystemExit("The `rides` table is empty -- nothing to match against.")

    resp = requests.get(HHN_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    waits_by_name = _get_live_waits(resp.text, known_ride_names=[r["name"] for r in rides])

    if not waits_by_name:
        print("No live wait data on the page right now (HHN may not be running). Exiting.")
        return

    match_ride = _build_ride_matcher(rides)
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    unmatched = []
    for name, wait in waits_by_name.items():
        ride_id = match_ride(name)
        if ride_id is None:
            unmatched.append(name)
            continue
        rows.append(
            {
                "ride_id": ride_id,
                "timestamp": now,
                "waittime": int(wait),
                "issue_with_ride": False,
            }
        )

    if unmatched:
        print(f"Skipped {len(unmatched)} unmatched ride(s) from the page: {unmatched}")

    if not rows:
        print("Nothing matched our rides table -- nothing to upload.")
        return

    supabase.table("ride_waits").insert(rows).execute()
    print(f"Uploaded {len(rows)} wait time record(s) at {now}.")


if __name__ == "__main__":
    main()