"""
Pulls live Halloween Horror Nights Orlando + regular Universal Studios wait
times from Thrill Data and uploads them to the `ride_waits` table in
Supabase.

How it works
------------
Two different page formats:

1. HHN page (https://www.thrill-data.com/hhn/orlando/2026) has a
   "Live HHN Orlando Waits" section near the top that's a list of links,
   one per house, each shaped like:

       <a href="https://www.thrill-data.com/waits/attraction/universal-studios/
                 cybergoria/" title="Cybergoria">Cybergoria <svg>...</svg> 5m</a>

2. Regular park page (https://www.thrill-data.com/waits/park/unit/
   universal-studios/) has a small "Longest Waits Right Now" widget with
   just the top 3 current waits, in that *same* link shape -- but the full
   ride list for that page is rendered as an embedded Plotly bar chart, not
   a link list. IMPORTANT: we must not let the top-3 widget's links stand
   in for the full ride list, or we silently lose most of the park's rides
   and pick up bogus non-standby entries like "Sinners Accessibility Return
   Time" (see `_filter_bad_names`).

For each page we:
  1. Download the page HTML.
  2. Extract {ride_name: wait_minutes} using whichever method fits that
     page (see `_scrape_hhn_waits` / `_scrape_park_waits` below).
  3. Drop any entries that aren't real standby waits (accessibility /
     return-time estimates etc).
  4. Match each scraped ride name to a `rides.id` (names on the site are
     often longer/slightly different than what's in our table, e.g.
     "Ozzy Osbourne: Prince of Darkness" vs. "Ozzy Osbourne", so we match on
     overlapping words rather than requiring an exact string match).
  5. Insert one row per matched ride into `ride_waits`.

If HHN isn't currently running (no event tonight, or it's the off-season),
there's no live-waits section on the HHN page at all -- that's fine, the
park page will still get scraped normally.

Environment variables (set as GitHub Actions secrets, or in a local .env):
  SUPABASE_URL
  SUPABASE_KEY

Usage
-----
  python scrape_waits.py            # loops forever, scraping every 5 min
  python scrape_waits.py --once     # single scrape, then exits (for cron)
  python scrape_waits.py --interval 120   # custom loop interval, in seconds
"""

import argparse
import array
import base64
import html as html_lib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://lxwpjknljuiaivpwixzj.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "sb_secret_qVf_tCgTEbeCszpAHRDiVQ_q-SVZr0W"

HHN_URL = "https://www.thrill-data.com/hhn/orlando/2026"
PARK_URL = "https://www.thrill-data.com/waits/park/unit/universal-studios/"

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

# Entries that show up as "/waits/attraction/..." links but are NOT real
# standby wait times -- e.g. accessibility/DAS return-time estimates. These
# would otherwise fuzzy-match onto the ride they're named after (e.g.
# "Sinners Accessibility Return Time" -> "Sinners") and clobber its real
# wait with a meaningless number.
BAD_NAME_RE = re.compile(r"accessibility|return\s*time", re.IGNORECASE)


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
# Parsing "<a href='.../waits/attraction/...'>Name ... 5m</a>" style links
# ---------------------------------------------------------------------------

LIVE_WAITS_SECTION_START = "Live HHN Orlando Waits"
LIVE_WAITS_SECTION_END_MARKERS = ("Low wait", "Event Years", "Wait Stats")

ATTRACTION_LINK_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<inner>.*?)</a>", re.IGNORECASE | re.DOTALL
)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')
TRAILING_MINUTES_RE = re.compile(r"(\d+)\s*m\b", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def _get_live_waits_from_link_list(html, section_start=None, section_end_markers=()):
    """Parses out every `<a href=".../waits/attraction/...">Name ... 5m</a>`
    style link on the page and returns {ride_name: wait_minutes}.

    If `section_start` is given, only looks within the text between that
    marker and the first of `section_end_markers` that appears after it. If
    `section_start` is omitted, scans the whole page -- useful as a last
    resort, but note that stray "/waits/attraction/" links elsewhere on a
    page (e.g. a "Longest Waits Right Now" top-3 widget) will match too, so
    this should never be treated as authoritative for a page's *full* ride
    list -- only use it when nothing more specific is available.
    """
    if section_start is not None:
        start = html.find(section_start)
        if start == -1:
            return {}
        end_candidates = [
            html.find(marker, start + len(section_start)) for marker in section_end_markers
        ]
        end_candidates = [i for i in end_candidates if i != -1]
        end = min(end_candidates) if end_candidates else start + 8000
        section = html[start:end]
    else:
        section = html

    results = {}
    for match in ATTRACTION_LINK_RE.finditer(section):
        attrs = dict((k.lower(), v) for k, v in ATTR_RE.findall(match.group("attrs")))
        href = attrs.get("href", "")
        if "/waits/attraction/" not in href:
            continue

        inner_text = TAG_RE.sub(" ", match.group("inner"))
        inner_text = re.sub(r"\s+", " ", inner_text).strip()

        minutes_match = TRAILING_MINUTES_RE.search(inner_text)
        if not minutes_match:
            continue

        name = attrs.get("title") or inner_text[: minutes_match.start()].strip(" \u2193\u2191\u2192-")
        name = html_lib.unescape(name).strip()
        if not name:
            continue

        results[name] = int(minutes_match.group(1))

    return results


def _filter_bad_names(waits_by_name):
    """Drop scraped entries that aren't real standby wait times (see
    BAD_NAME_RE) before they ever get a chance to fuzzy-match onto a ride."""
    return {name: wait for name, wait in waits_by_name.items() if not BAD_NAME_RE.search(name)}


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
    parsed = [(r["id"], r["name"], set(_normalize(r["name"]))) for r in rides]

    def match(scraped_name):
        """Returns (ride_id_or_None, closest_ride_name, score) so callers
        can see *why* something didn't match, not just that it didn't."""
        scraped_words = set(_normalize(scraped_name))
        if not scraped_words:
            return None, None, 0.0
        best_id, best_name, best_score = None, None, 0.0
        for ride_id, ride_name, ride_words in parsed:
            if not ride_words:
                continue
            overlap = len(ride_words & scraped_words) / len(ride_words)
            if overlap > best_score:
                best_id, best_name, best_score = ride_id, ride_name, overlap
        matched_id = best_id if best_score >= 0.9 else None
        return matched_id, best_name, best_score

    return match


# ---------------------------------------------------------------------------
# Plotly chart extraction (used for the regular, non-HHN park page)
# ---------------------------------------------------------------------------

def _get_live_waits_from_plotly(html, known_ride_names):
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
# Per-page scraping strategies
# ---------------------------------------------------------------------------

def _fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _scrape_hhn_waits(url):
    """HHN page: the "Live HHN Orlando Waits" section is a proper anchored
    link list -- use it directly."""
    html = _fetch_html(url)
    waits = _get_live_waits_from_link_list(
        html, LIVE_WAITS_SECTION_START, LIVE_WAITS_SECTION_END_MARKERS
    )
    if not waits:
        # HHN isn't running right now (off night / off-season) -- fine.
        return {}
    return _filter_bad_names(waits)


def _scrape_park_waits(url, known_ride_names):
    """Regular park page: the full ride list lives in an embedded Plotly bar
    chart, NOT a link list. There IS a small "Longest Waits Right Now" (top
    3) widget on this page that uses the same link shape as HHN's list, but
    treating that as the full ride list would silently drop everything else
    on the page -- so we go straight for the chart, and only fall back to
    the (partial) link list if the chart can't be found at all.
    """
    html = _fetch_html(url)
    waits = _get_live_waits_from_plotly(html, known_ride_names)
    if not waits:
        waits = _get_live_waits_from_link_list(html)
    return _filter_bad_names(waits)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_once():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY are not set.")

    print(f"Connecting to Supabase project: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rides = supabase.table("rides").select("id, name").execute().data
    if not rides:
        raise SystemExit("The `rides` table is empty -- nothing to match against.")

    print(f"Fetched {len(rides)} ride(s) from Supabase.")
    known_names = [r["name"] for r in rides]

    park_waits = _scrape_park_waits(PARK_URL, known_names)
    print(f"Park page: found {len(park_waits)} live wait(s): {park_waits}")

    hhn_waits = _scrape_hhn_waits(HHN_URL)
    print(f"HHN page: found {len(hhn_waits)} live wait(s): {hhn_waits}")

    # Merge park first, then HHN -- if a name ever appeared on both (it
    # shouldn't, HHN houses aren't normal daytime attractions), the
    # HHN-specific figure wins since it's the more relevant one for an
    # event-only house.
    waits_by_name = {}
    waits_by_name.update(park_waits)
    waits_by_name.update(hhn_waits)

    if not waits_by_name:
        print("No live wait data found on either page right now. Exiting.")
        return

    match_ride = _build_ride_matcher(rides)
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    unmatched = []
    for name, wait in waits_by_name.items():
        ride_id, closest_name, score = match_ride(name)
        if ride_id is None:
            unmatched.append((name, closest_name, score))
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
        print(f"Skipped {len(unmatched)} unmatched ride(s) from the page:")
        for name, closest_name, score in unmatched:
            print(f"  {name!r} -- closest match in `rides` table: {closest_name!r} (score {score:.2f})")

    if not rows:
        print("Nothing matched our rides table -- nothing to upload.")
        return

    supabase.table("ride_waits").insert(rows).execute()
    print(f"Uploaded {len(rows)} wait time record(s) at {now}.")


def run_forever(interval_seconds=300):
    print(
        f"Starting scrape loop -- running every {interval_seconds} second(s) "
        f"({interval_seconds / 60:.1f} min). Press Ctrl+C to stop.\n"
    )
    while True:
        started = time.monotonic()
        print(f"--- Run started at {datetime.now(timezone.utc).isoformat()} ---")
        try:
            run_once()
        except Exception:
            # Never let one bad cycle (a network blip, a page-layout change,
            # etc) kill the whole loop -- log it and try again next cycle.
            print("Scrape cycle failed:")
            traceback.print_exc()
        elapsed = time.monotonic() - started
        sleep_for = max(0.0, interval_seconds - elapsed)
        print(f"--- Run finished, sleeping {sleep_for:.0f}s until next run ---\n")
        time.sleep(sleep_for)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single scrape cycle and exit (useful for a cron / GitHub Actions job).",
    )
    parser.add_argument(
        "--interval", type=int, default=300,
        help="Seconds between scrapes when looping (default: 300 = 5 minutes).",
    )
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_forever(args.interval)


if __name__ == "__main__":
    main()