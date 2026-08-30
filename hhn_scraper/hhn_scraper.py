import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from supabase import create_client

SUPABASE_URL = os.getenv("HHN_SUPABASE_URL")
SUPABASE_KEY = os.getenv("HHN_SUPABASE_KEY")

BASE_URL = "https://www.thrill-data.com/waits/attraction/universal-studios/{slug}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 1.5

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

WAIT_NOW_RE = re.compile(r"→\s*(\d+)\s*min\s*now", re.IGNORECASE)
WAIT_ANY_RE = re.compile(r"→\s*(\d+)\s*min", re.IGNORECASE)


def fetch_wait_time(slug):
    url = BASE_URL.format(slug=slug)
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


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: HHN_SUPABASE_URL and HHN_SUPABASE_KEY must be set.", file=sys.stderr)
        return 1

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows_to_insert = []
    errors = []

    for i, ride in enumerate(RIDES):
        try:
            wait = fetch_wait_time(ride["slug"])
            rows_to_insert.append({
                "ride_id": ride["id"],
                "wait_time": wait,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"[ok] {ride['name']}: {wait if wait is not None else 'closed/no data'}")
        except Exception as exc:
            errors.append((ride["name"], str(exc)))
            print(f"[error] {ride['name']}: {exc}", file=sys.stderr)

        if i < len(RIDES) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    if rows_to_insert:
        result = supabase.table("ride_waits").insert(rows_to_insert).execute()
        print(f"Inserted {len(result.data)} rows into ride_waits.")

    if errors:
        print(f"Completed with {len(errors)} ride(s) failing to scrape.", file=sys.stderr)
        if len(errors) == len(RIDES):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())