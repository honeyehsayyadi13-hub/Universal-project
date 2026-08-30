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

Expected schema in the target database:
    rides(id int8, ride_id int2, name text, ...)
    ride_waits(id int8, ride_id int2, timestamp timestamptz,
               waittime int2 null, issue_with_ride bool, created_at timestamptz)

A NULL waittime (with issue_with_ride = True) means the ride/house was
closed or Thrill Data was not reporting a wait at the time of the check.
created_at is left to the database's own default and is not set here.
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

BASE_URL = "https://www.thrill-data.com/waits/attraction/universal-studios/{slug}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 15  # seconds
DELAY_BETWEEN_REQUESTS = 1.5  # seconds, be polite to thrill-data.com

# id/name here must match the `rides` table in the NEW Supabase database.
# "Entrance" (id 15 in the reference screenshot) is intentionally omitted --
# it doesn't correspond to a Thrill Data attraction page.
RIDES = [
    {"id": 1, "name": "Revenge of the Mummy", "slug": "revengeofthemummy"},
    {"id": 2, "name": "Harry Potter and the Escape from Gringotts", "slug": "harrypotterandtheescapefromgringotts"},
    {"id": 3, "name": "Transformers", "slug": "transformerstherided"},
    {"id": 4, "name": "Men In Black", "slug": "meninblackalienattack"},
    {"id": 5, "name": "Stranger Things", "slug": "stranger-things"},
    {"id": 6, "name": "Evil Dead Burn", "slug": "evildeadburn"},
    {"id": 7, "name": "Jack and Oddfellow", "slug": "jackoddfellowchaoscontrol"},
    {"id": 8, "name": "Ozzy Osbourne", "slug": "ozzyosbourneprinceofdarkness"},
    {"id": 9, "name": "MADLANDS: Caged Cannibals", "slug": "madlandscagedcannibals"},
    {"id": 10, "name": "Cybergoria", "slug": "cybergoria"},
    {"id": 11, "name": "INVASION: Alien Abduction", "slug": "invasionalienabduction"},
    {"id": 12, "name": "H.R. Bloodengutz", "slug": "hrbloodengutzpresentsahalloweenfrighttacular"},
    {"id": 13, "name": "Hellraiser", "slug": "hellraiser"},
    {"id": 14, "name": "Sinners", "slug": "sinners"},
]

# Matches the "→80min now" style live-wait badge Thrill Data renders
# server-side on each attraction page.
WAIT_NOW_RE = re.compile(r"→\s*(\d+)\s*min\s*now", re.IGNORECASE)
# Fallback: any "→Nmin" style badge on the page (e.g. "avg" variants).
WAIT_ANY_RE = re.compile(r"→\s*(\d+)\s*min", re.IGNORECASE)


def fetch_wait_time(slug: str) -> int | None:
    """Fetch a single attraction page and extract the current live wait.

    Returns an int (minutes) if a wait is currently posted, or None if the
    ride is closed / not reporting / the page couldn't be parsed.
    """
    url = BASE_URL.format(slug=slug)
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = WAIT_NOW_RE.search(text)
    if match:
        return int(match.group(1))

    # Some pages may not use the exact "now" wording; fall back loosely,
    # but only within a small window near the ride name so we don't
    # accidentally grab an unrelated "avg" figure from a related-rides list.
    fallback = WAIT_ANY_RE.search(text[:2000])
    if fallback:
        return int(fallback.group(1))

    return None


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(
            "ERROR: HHN_SUPABASE_URL and HHN_SUPABASE_KEY must be set.",
            file=sys.stderr,
        )
        return 1

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows_to_insert = []
    errors = []

    for i, ride in enumerate(RIDES):
        try:
            wait = fetch_wait_time(ride["slug"])
            rows_to_insert.append(
                {
                    "ride_id": ride["id"],
                    "waittime": wait,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "issue_with_ride": wait is None,
                }
            )
            print(f"[ok] {ride['name']}: {wait if wait is not None else 'closed/no data'}")
        except Exception as exc:  # noqa: BLE001 - keep going on a per-ride failure
            errors.append((ride["name"], str(exc)))
            print(f"[error] {ride['name']}: {exc}", file=sys.stderr)

        # Be polite between requests, but skip the sleep after the last ride
        if i < len(RIDES) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    if rows_to_insert:
        result = supabase.table("ride_waits").insert(rows_to_insert).execute()
        print(f"Inserted {len(result.data)} rows into ride_waits.")

    if errors:
        print(f"Completed with {len(errors)} ride(s) failing to scrape.", file=sys.stderr)
        # Non-zero exit if EVERY ride failed, otherwise treat as a partial
        # success so a single flaky page doesn't red-flag every run.
        if len(errors) == len(RIDES):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())