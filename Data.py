#data.py
import requests
from datetime import datetime
import threading
import time

ride_waits = {}

# NEW: tracks whether each ride is actually running right now, straight from
# the API's own `is_open` flag -- this is the source of truth for "closed",
# NOT the wait time. A closed ride can report a stale nonzero wait (its last
# reading before going down), and an open ride can legitimately report 0
# (walk-on). Using wait==0 as a proxy for "closed" gets both of those wrong,
# and feeding a closed ride's stale wait into live-anchored predictions
# would poison the forecast for that ride. ride_open is the fix.
ride_open = {}

now = datetime.now()

##check current day
current_day = now.strftime("%A")
print(current_day)

##check current time
current_time = now.strftime("%H:%M:%S")
print(current_time)

##Rides available 
rides = ["hulk", "stormForce", "doctorDoom", "spiderMan", 
         "bilgeRat", "ripsawFalls", "skullIsland", "velociCoaster", 
         "riverAdventure", "hogwartsTrain", "hippogriff", "hagrid", 
         "drSeussAirRide", "caroSeussel", "oneFishtwoFish", "catInTheHat", "harryPotter"]

rideInfo = []

def rideLog(ride, date, time, waitTime, isOpen):
    rideInfo.append({
        "ride": ride,
        "date": date,
        "time": time,
        "wait_time": waitTime,
        "is_open": isOpen,
    })
    #print(f"Logged: {ride} on {date} at {time} — {waitTime} min wait")

def _process_ride(name, wait, is_open, current_day, current_time):
    """
    Matches one ride entry from the live feed against our known ride keys
    and updates ride_waits / ride_open for it. Isolated into its own
    function (called inside a try/except by the caller) so that if any
    single ride entry is malformed -- e.g. a future API change adds a ride
    with an unexpected shape, or `wait`/`is_open` come back None/missing --
    it can't take down the whole polling loop. Previously an uncaught
    exception ANYWHERE in this matching logic would propagate out of
    getLiveWaitTimes(), which had no try/except around the parsing loop
    (only around the initial HTTP request), silently killing the daemon
    thread in update_backend() for good. Every ride would then freeze at
    whatever ride_waits/ride_open last held -- which looks exactly like
    "some specific rides say Loading... forever" from the frontend, since
    /api/rides only reports rides that exist in ride_waits at all.
    """
    if name=="The Incredible Hulk Coaster®":
        rideLog("hulk", current_day, current_time, wait, is_open)
        ride_waits["hulk"] = wait
        ride_open["hulk"] = is_open

    elif name=="Storm Force Accelatron®":
        rideLog("stormForce", current_day, current_time, wait, is_open)
        ride_waits["stormForce"] = wait
        ride_open["stormForce"] = is_open

    elif name=="Doctor Doom's Fearfall®":
        rideLog("doctorDoom", current_day, current_time, wait, is_open)
        ride_waits["doctorDoom"] = wait
        ride_open["doctorDoom"] = is_open

    elif name=="The Amazing Adventures of Spider-Man®":
        rideLog("spiderMan", current_day, current_time, wait, is_open)
        ride_waits["spiderMan"] = wait
        ride_open["spiderMan"] = is_open

    elif name=="Popeye & Bluto's Bilge-Rat Barges®":
        rideLog("bilgeRat", current_day, current_time, wait, is_open)
        ride_waits["bilgeRat"] = wait
        ride_open["bilgeRat"] = is_open

    elif name=="Dudley Do-Right's Ripsaw Falls®":
        rideLog("ripsawFalls", current_day, current_time, wait, is_open)
        ride_waits["ripsawFalls"] = wait
        ride_open["ripsawFalls"] = is_open

    elif name=="Skull Island: Reign of Kong":
        rideLog("skullIsland", current_day, current_time, wait, is_open)
        ride_waits["skullIsland"] = wait
        ride_open["skullIsland"] = is_open

    elif name=="Jurassic World VelociCoaster":
        # NOTE: this key was previously misspelled "veloliCoaster" in
        # the rideLog() call (though the ride_waits/ride_open dicts
        # below were always spelled correctly). If anything ever
        # ingests `rideInfo` into the Supabase history table, that
        # typo would have silently orphaned every VelociCoaster
        # sample under a key that never matches `rides.name`,
        # leaving the optimizer with zero real history for it and
        # forcing the 30-min default every time. Fixed.
        rideLog("velociCoaster", current_day, current_time, wait, is_open)
        ride_waits["velociCoaster"] = wait
        ride_open["velociCoaster"] = is_open

    elif name=="Jurassic Park River Adventure":
        rideLog("riverAdventure", current_day, current_time, wait, is_open)
        ride_waits["riverAdventure"] = wait
        ride_open["riverAdventure"] = is_open

    elif name=="Harry Potter and the Forbidden Journey™":
        rideLog("harryPotter", current_day, current_time, wait, is_open)
        ride_waits["harryPotter"] = wait
        ride_open["harryPotter"] = is_open

    elif name== "Hogwarts Express™ - Hogsmeade™ Station":
        rideLog("hogwartsTrain", current_day, current_time, wait, is_open)
        ride_waits["hogwartsTrain"] = wait
        ride_open["hogwartsTrain"] = is_open

    elif name=="Flight of the Hippogriff™":
        rideLog("hippogriff", current_day, current_time, wait, is_open)
        ride_waits["hippogriff"] = wait
        ride_open["hippogriff"] = is_open

    elif name=="Hagrid's Magical Creatures Motorbike Adventure™":
        rideLog("hagrid", current_day, current_time, wait, is_open)
        ride_waits["hagrid"] = wait
        ride_open["hagrid"] = is_open

    elif name=="The High in the Sky Seuss Trolley Train Ride!™":
        rideLog("drSeussAirRide", current_day, current_time, wait, is_open)
        ride_waits["drSeussAirRide"] = wait
        ride_open["drSeussAirRide"] = is_open

    elif name=="Caro-Seuss-el™":
        rideLog("caroSeussel", current_day, current_time, wait, is_open)
        ride_waits["caroSeussel"] = wait
        ride_open["caroSeussel"] = is_open

    elif name=="One Fish, Two Fish, Red Fish, Blue Fish™":
        rideLog("oneFishtwoFish", current_day, current_time, wait, is_open)
        ride_waits["oneFishtwoFish"] = wait
        ride_open["oneFishtwoFish"] = is_open

    elif name=="The Cat in The Hat™":
        rideLog("catInTheHat", current_day, current_time, wait, is_open)
        ride_waits["catInTheHat"] = wait
        ride_open["catInTheHat"] = is_open

def getLiveWaitTimes():
    now = datetime.now()
    current_day = now.strftime("%A")
    current_time = now.strftime("%H:%M:%S")

    url = "https://queue-times.com/parks/64/queue_times.json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch wait times: {e}")
        return
    except ValueError as e:
        # response.json() failed to parse (e.g. an HTML error page came
        # back instead of JSON) -- bail out for this poll rather than
        # crashing the whole background thread.
        print(f"Failed to parse wait-time response as JSON: {e}")
        return

    ##print(f"\n--- Islands of Adventure ({current_day} {current_time}) ---")
    try:
        lands = data["lands"]
    except (KeyError, TypeError) as e:
        print(f"Unexpected response shape from queue-times.com (no 'lands'): {e}")
        return

    for land in lands:
        try:
            land_rides = land["rides"]
        except (KeyError, TypeError) as e:
            print(f"Skipping malformed land entry: {e}")
            continue

        for ride in land_rides:
            # Each ride is handled in its own try/except so one bad/
            # unexpected entry can't silently kill the entire polling
            # thread and freeze every ride's data at whatever it last
            # held. Without this, a single ride missing a field (or a
            # future queue-times.com schema change) would raise up
            # through getLiveWaitTimes() -> update_backend()'s while
            # loop -> thread dies -- with no crash message anywhere the
            # frontend could see, just rides stuck showing "Loading..."
            # forever.
            try:
                name = ride["name"]
                wait = ride["wait_time"]
                is_open = ride["is_open"]
                _process_ride(name, wait, is_open, current_day, current_time)
            except Exception as e:
                print(f"Error processing ride entry {ride!r}: {e}")
                continue

# Run:
def update_backend():
    while True:
        try:
            getLiveWaitTimes()   # your data.py function
        except Exception as e:
            # Last-resort safety net: even with the try/excepts above, if
            # something truly unexpected happens, log it and keep the
            # polling loop alive rather than letting the daemon thread die
            # silently and freezing every ride's data forever.
            print(f"update_backend: unexpected error, will retry: {e}")
        time.sleep(5)        # update every 5 seconds