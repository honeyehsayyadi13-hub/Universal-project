import requests
from datetime import datetime
import threading
import time

ride_waits = {}

now = datetime(2026, 8, 12, 8, 0)

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
    #print(f"Logged: {ride} on {date} at {time} — {waitTime} min wait")

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
                rideLog("hulk", current_day, current_time, wait)
                ride_waits["hulk"] = wait
                
            elif name=="Storm Force Accelatron®":
                rideLog("stormForce", current_day, current_time, wait)
                ride_waits["stormForce"] = wait
                
            elif name=="Doctor Doom's Fearfall®":
                rideLog("doctorDoom", current_day, current_time, wait)
                ride_waits["doctorDoom"] = wait
                
            elif name=="The Amazing Adventures of Spider-Man®":
                rideLog("spiderMan", current_day, current_time, wait)
                ride_waits["spiderMan"] = wait
                
            elif name=="Popeye & Bluto's Bilge-Rat Barges®":
                rideLog("bilgeRat", current_day, current_time, wait)
                ride_waits["bilgeRat"] = wait
                
            elif name=="Dudley Do-Right's Ripsaw Falls®":
                rideLog("ripsawFalls", current_day, current_time, wait)
                ride_waits["ripsawFalls"] = wait
                
            elif name=="Skull Island: Reign of Kong™":
                rideLog("skullIsland", current_day, current_time, wait)
                ride_waits["skullIsland"] = wait
                
            elif name=="Jurassic World VelociCoaster":
                rideLog("veloliCoaster", current_day, current_time, wait)
                ride_waits["velociCoaster"] = wait
                
            elif name=="Jurassic Park River Adventure":
                rideLog("riverAdventure", current_day, current_time, wait)
                ride_waits["riverAdventure"] = wait
                
            elif name=="Harry Potter and the Forbidden Journey™":
                rideLog("harryPotter", current_day, current_time, wait)
                ride_waits["harryPotter"] = wait

            elif name== "Hogwarts Express™ - Hogsmeade™ Station":
                rideLog("hogwartsTrain", current_day, current_time, wait)
                ride_waits["hogwartsTrain"] = wait
                
            elif name=="Flight of the Hippogriff™":
                rideLog("hippogriff", current_day, current_time, wait)
                ride_waits["hippogriff"] = wait
                
            elif name=="Hagrid's Magical Creatures Motorbike Adventure™":
                rideLog("hagrid", current_day, current_time, wait)
                ride_waits["hagrid"] = wait
                
            elif name=="The High in the Sky Seuss Trolley Train Ride!™":
                rideLog("drSeussAirRide", current_day, current_time, wait)
                ride_waits["drSeussAirRide"] = wait
                
            elif name=="Caro-Seuss-el™":
                rideLog("caroSeussel", current_day, current_time, wait)
                ride_waits["caroSeussel"] = wait
                
            elif name=="One Fish, Two Fish, Red Fish, Blue Fish™":
                rideLog("oneFishtwoFish", current_day, current_time, wait)
                ride_waits["oneFishtwoFish"] = wait
                
            elif name=="The Cat in The Hat™":
                rideLog("catInTheHat", current_day, current_time, wait)
                ride_waits["catInTheHat"] = wait
                
# Run:
def update_backend():
    while True:
        getLiveWaitTimes()   # your data.py function
        time.sleep(5)        # update every 5 seconds