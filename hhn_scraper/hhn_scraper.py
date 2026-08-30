"""
hhn_scraper.py

Scrapes live wait times for a fixed set of Halloween Horror Nights Orlando /
Universal Studios rides & houses from Thrill Data, and writes them into a
Supabase database.

This is a STANDALONE scraper. It does not import or touch the existing
scraper.py / its database in this repo. It reads its own set of environment
variables (see below) so it can point at a completely separate Supabase
project without any risk of colliding with the existing one.

Required environment variables (set as GitHub Actions secrets):
    HHN_SUPABASE_URL   - the Supabase project URL for the NEW database
    HHN_SUPABASE_KEY   - the Supabase service key for the NEW database

Target table: ride_waits(id, ride_id int2, timestamp timestamptz,
                          waittime int2 null, issue_with_ride bool,
                          created_at timestamptz)

A NULL waittime (with issue_with_ride = True) means the ride/house was
closed or Thrill Data was not reporting a wait at the time of the check.

Data sources:
  - The 4 regular daytime rides (Mummy, Gringotts, Transformers, MIB) are
    scraped from their own Thrill Data attraction pages, which reliably
    show a "->Nmin now" live badge.
  - The 10 HHN haunted houses are scraped from Thrill Data's single HHN
    live dashboard page (/hhn) instead. Their individual attraction pages
    were found to sometimes display stale stats left over from a past
    year's version of the same house (e.g. an old "Stranger Things"
    incarnation), while the /hhn dashboard's "Live HHN Orlando Waits"
    section reliably reflects the current house.
"""

import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("HHN_SUPABASE_URL")
SUPABASE_KEY = os.getenv("HHN_SUPABASE_KEY")

RIDE_PAGE_URL = "https://www.thrill-data.com/waits/attraction/universal-studios/{slug}/"
HHN_LIVE_URL = "https://www.thrill-data.com/hhn"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 15  # seconds
DELAY_BETWEEN_REQUESTS = 1.5  # seconds, be polite to thrill-data.com

# Regular rides: scraped from their own attraction page.
THRILL_RIDES = [
    {"id": 1, "name": "Revenge of the Mummy", "slug": "revengeofthemummy"},
    {"id": 2, "name": "Harry Potter and the Escape from Gringotts", "slug": "harrypotterandtheescapefromgringotts"},
    {"id": 3, "name": "Transformers", "slug": "transformerstherided"},
    {"id": 4, "name": "Men In Black", "slug": "meninblackalienattack"},
]

# HHN houses: scraped from the /hhn live dashboard instead. "match" is the
# exact display name Thrill Data uses in that dashboard's live waits list
# (may differ slightly from our short `name`, e.g. includes a subtitle).
HOUSES = [
    {"id": 5, "name": "Stranger Things", "match": "Stranger Things 5"},
    {"id": 6, "name": "Evil Dead Burn", "match": "Evil Dead Burn"},
    {"id": 7, "name": "Jack and Oddfellow", "match": "Jack & Oddfellow: Chaos & Control"},
    {"id": 8, "name": "Ozzy Osbourne", "match": "Ozzy Osbourne: Prince of Darkness"},
    {"id": 9, "name": "MADLANDS: Caged Cannibals", "match": "Madlands: Caged Cannibals"},
    {"id": 10, "name": "Cybergoria", "match": "Cybergoria"},
    {"id": 11, "name": "INVASION: Alien Abduction", "match": "Invasion: Alien Abduction"},
    {"id": 12, "name": "H.R. Bloodengutz", "match": "H.R. Bloodengutz Presents: A Halloween Fright-Tacular"},
    {"id": 13, "name": "Hellraiser", "match": "Hellraiser"},
    {"id": 14, "name": "Sinners", "match": "Sinners"},
]

# Matches the "->80min now" style live-wait badge Thrill Data renders
# server-side on each individual attraction page.
WAIT_NOW_RE = re.compile(r"→\s*(\d+)\s*min\s*now", re.IGNORECASE)
WAIT_ANY_RE = re.compile(r"→\s*(\d+)\s*min", re.IGNORECASE)


def fetch_ride_wait(slug: str) -> int | None:
    """Fetch a single attraction page and extract the current live wait."""
    url = RIDE_PAGE_URL.format(slug=slug)
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = WAIT_NOW_RE.search(text)
    if match:
        return int(match.group(1))

    fallback = WAIT_ANY_RE.search(text[:2000])
    if fallback:
        return int(fallback.group(1))

    return None


def fetch_hhn_house_waits(house_names: list[str]) -> dict[str, int | None]:
    """Fetch the /hhn live dashboard once and pull out each house's wait.

    Looks for entries like "Stranger Things 5 v 25m" or
    "Invasion: Alien Abduction -> 10m" in the page's live-waits section.
    Returns a dict mapping each requested display name to an int (minutes)
    or None if not found / not currently reporting.
    """
    resp = requests.get(HHN_LIVE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    results: dict[str, int | None] = {}
    for name in house_names:
        pattern = re.compile(
            re.escape(name) + r"\s*[↑↓→]\s*(\d+)\s*m\b", re.IGNORECASE
        )
        match = pattern.search(text)
        results[name] = int(match.group(1)) if match else None

    return results


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: HHN_SUPABASE_URL and HHN_SUPABASE_KEY must be set.", file=sys.stderr)
        return 1

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows_to_insert = []
    errors = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # --- Regular rides: one page each ---
    for i, ride in enumerate(THRILL_RIDES):
        try:
            wait = fetch_ride_wait(ride["slug"])
            rows_to_insert.append(
                {
                    "ride_id": ride["id"],
                    "waittime": wait,
                    "timestamp": now_iso,
                    "issue_with_ride": wait is None,
                }
            )
            print(f"[ok] {ride['name']}: {wait if wait is not None else 'closed/no data'}")
        except Exception as exc:  # noqa: BLE001 - keep going on a per-ride failure
            errors.append((ride["name"], str(exc)))
            print(f"[error] {ride['name']}: {exc}", file=sys.stderr)

        if i < len(THRILL_RIDES) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # --- Houses: one shared dashboard fetch ---
    try:
        house_waits = fetch_hhn_house_waits([h["match"] for h in HOUSES])
        for house in HOUSES:
            wait = house_waits.get(house["match"])
            rows_to_insert.append(
                {
                    "ride_id": house["id"],
                    "waittime": wait,
                    "timestamp": now_iso,
                    "issue_with_ride": wait is None,
                }
            )
            print(f"[ok] {house['name']}: {wait if wait is not None else 'closed/no data'}")
    except Exception as exc:  # noqa: BLE001
        errors.append(("HHN live dashboard", str(exc)))
        print(f"[error] HHN live dashboard fetch failed: {exc}", file=sys.stderr)

    if rows_to_insert:
        result = supabase.table("ride_waits").insert(rows_to_insert).execute()
        print(f"Inserted {len(result.data)} rows into ride_waits.")

    total_items = len(THRILL_RIDES) + 1  # +1 for the single houses fetch
    if errors:
        print(f"Completed with {len(errors)} failure(s).", file=sys.stderr)
        if len(errors) == total_items:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())