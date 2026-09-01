"""
One-off diagnostic: run this locally (`py diagnose_park_page.py`) and paste
me the full output. It'll tell us why the Plotly chart extraction in
scrape_waits.py is coming back empty on the park page.
"""

import re
import requests

URL = "https://www.thrill-data.com/waits/park/unit/universal-studios/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

resp = requests.get(URL, headers=HEADERS, timeout=30)
html = resp.text

print(f"Status code: {resp.status_code}")
print(f"HTML length: {len(html)} chars")
print()

# Save it so we have the raw source for reference either way.
with open("park_page_raw.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved full raw HTML to park_page_raw.html")
print()

# Does the literal Plotly.newPlot( call exist at all?
count = html.count("Plotly.newPlot(")
print(f'Occurrences of "Plotly.newPlot(": {count}')

# Does the word "Plotly" show up anywhere, even differently?
print(f'Occurrences of "Plotly" (any form): {html.count("Plotly")}')

# Look for likely API/AJAX endpoints the page's JS might be calling instead
# (a sign the wait data is fetched client-side rather than embedded).
api_hints = re.findall(r'["\'](/api/[^"\']+|/waits/[^"\']*json[^"\']*|https?://[^"\']*api[^"\']*)["\']', html, re.IGNORECASE)
print(f"Possible API endpoint hints found: {len(api_hints)}")
for hint in sorted(set(api_hints))[:20]:
    print(f"  {hint}")

# Does the "Live Waits" tab / full ride list text appear anywhere in the raw HTML at all?
for needle in ["Harry Potter", "Men In Black", "TRANSFORMERS", "Live Waits", "customdata"]:
    idx = html.find(needle)
    print(f'"{needle}" found at index: {idx}')