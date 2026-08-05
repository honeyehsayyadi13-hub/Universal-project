import requests 
from datetime import datetime 
import threading
import time

ride_waits = {}

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

def rideLog(ride, date, time, waitTime):
    rideInfo.append({
        "ride": ride,
        "date": date,
        "time": time,
        "wait_time": waitTime
    })
    print(f"Logged: {ride} on {date} at {time} — {waitTime} min wait")##this is a print statement

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

    ##print(f"\n--- Islands of Adventure ({current_day} {current_time}) ---")
    for land in data["lands"]:
        for ride in land["rides"]:
            name = ride["name"]
            wait = ride["wait_time"]
            is_open = ride["is_open"]
            status = f"{wait} min wait" if is_open else "closed"
            if name=="The Incredible Hulk Coaster®":
                print(f"  {name}: {status}")
                rideLog("hulk", current_day, current_time, wait)
                ride_waits["hulk"] = wait
                print()
                
            elif name=="Storm Force Accelatron®":
                print(f"  {name}: {status}")
                rideLog("stormForce", current_day, current_time, wait)
                ride_waits["stormForce"] = wait
                print()
                
            elif name=="Doctor Doom's Fearfall®":
                print(f"  {name}: {status}")
                rideLog("doctorDoom", current_day, current_time, wait)
                ride_waits["doctorDoom"] = wait
                print()
                
            elif name=="The Amazing Adventures of Spider-Man®":
                print(f"  {name}: {status}")
                rideLog("spiderMan", current_day, current_time, wait)
                ride_waits["spiderMan"] = wait
                print()
                
            elif name=="Popeye & Bluto's Bilge-Rat Barges®":
                print(f"  {name}: {status}")
                rideLog("bilgeRat", current_day, current_time, wait)
                ride_waits["bilgeRat"] = wait
                print()
                
            elif name=="Dudley Do-Right's Ripsaw Falls®":
                print(f"  {name}: {status}")
                rideLog("ripsawFalls", current_day, current_time, wait)
                ride_waits["ripsawFalls"] = wait
                print()
                
            elif name=="Skull Island: Reign of Kong™":
                print(f"  {name}: {status}")
                rideLog("skullIsland", current_day, current_time, wait)
                ride_waits["skullIsland"] = wait
                print()
                
            elif name=="Jurassic World VelociCoaster":
                print(f"  {name}: {status}")
                rideLog("veloliCoaster", current_day, current_time, wait)
                ride_waits["velociCoaster"] = wait
                print()
                
            elif name=="Jurassic Park River Adventure":
                print(f"  {name}: {status}")
                rideLog("riverAdventure", current_day, current_time, wait)
                ride_waits["riverAdventure"] = wait
                print()
                
            elif name=="Harry Potter and the Forbidden Journey™":
                print(f"  {name}: {status}")
                rideLog("harryPotter", current_day, current_time, wait)
                ride_waits["harryPotter"] = wait
                print()

            elif name== "Hogwarts Express™ - Hogsmeade™ Station":
                print(f"  {name}: {status}")
                rideLog("hogwartsTrain", current_day, current_time, wait)
                ride_waits["hogwartsTrain"] = wait
                print()
                
            elif name=="Flight of the Hippogriff™":
                print(f"  {name}: {status}")
                rideLog("hippogriff", current_day, current_time, wait)
                ride_waits["hippogriff"] = wait
                print()
                
            elif name=="Hagrid's Magical Creatures Motorbike Adventure™":
                print(f"  {name}: {status}")
                rideLog("hagrid", current_day, current_time, wait)
                ride_waits["hagrid"] = wait
                print()
                
            elif name=="The High in the Sky Seuss Trolley Train Ride!™":
                print(f"  {name}: {status}")
                rideLog("drSeussAirRide", current_day, current_time, wait)
                ride_waits["drSeussAirRide"] = wait
                print()
                
            elif name=="Caro-Seuss-el™":
                print(f"  {name}: {status}")
                rideLog("caroSeussel", current_day, current_time, wait)
                ride_waits["caroSeussel"] = wait
                print()
                
            elif name=="One Fish, Two Fish, Red Fish, Blue Fish™":
                print(f"  {name}: {status}")
                rideLog("oneFishtwoFish", current_day, current_time, wait)
                ride_waits["oneFishtwoFish"] = wait
                print()
                
            elif name=="The Cat in The Hat™":
                print(f"  {name}: {status}")
                rideLog("catInTheHat", current_day, current_time, wait)
                ride_waits["catInTheHat"] = wait
                print()
                
# Run:
def update_backend():
    while True:
        getLiveWaitTimes()   # your data.py function
        time.sleep(5)        # update every 5 seconds