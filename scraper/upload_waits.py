from supabase import create_client
import json


url = "https://azbjjemtcpaeqfqauzod.supabase.co"
key = "YOUR_KEY"

supabase = create_client(url, key)


with open("wait_times.json", "r") as file:
    waits = json.load(file)


BATCH_SIZE = 500


for i in range(0, len(waits), BATCH_SIZE):

    batch = waits[i:i+BATCH_SIZE]

    response = (
        supabase
        .table("wait_times")
        .insert(batch)
        .execute()
    )

    print(f"Uploaded {len(batch)} records")


print("Upload complete!")