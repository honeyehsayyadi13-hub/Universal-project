from supabase import create_client
import json


# Supabase info
url = "https://azbjjemtcpaeqfqauzod.supabase.co"

key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF6YmpqZW10Y3BhZXFmcWF1em9kIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0Mzc3NDIsImV4cCI6MjA5NjAxMzc0Mn0.VQ84Z1DDokGWDaW11y_n0rXRKFfN6T7pcC-h4PsAT34"


supabase = create_client(url, key)


# Load scraped data
with open("wait_times.json", "r") as file:
    waits = json.load(file)


# Upload each wait time
for wait in waits:

    data = {
        "timestamp": wait["timestamp"],
        "waittime": wait["waittime"],
        "issue_with_ride": wait["issue_with_ride"],
        "ride_id": wait["ride_id"]
    }

    response = supabase.table("wait_times").insert(data).execute()

    print(response)


print("Upload complete!")