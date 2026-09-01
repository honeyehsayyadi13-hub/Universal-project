import os
from dotenv import load_dotenv
from supabase import create_client


load_dotenv()


supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


# Test rides table

rides = (
    supabase
    .table("rides")
    .select("*")
    .execute()
)


print("Rides:")
print(rides.data)


# Test wait_times table

waits = (
    supabase
    .table("ride_waits")
    .select("*")
    .limit(5)
    .execute()
)


print("\nWait times:")
print(waits.data)