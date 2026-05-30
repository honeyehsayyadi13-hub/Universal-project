" Program that shows a user an optimized map of getting to rides at the amusement park Universal"
import pygame
import requests
import threading
import Data


pygame.init()

screen = pygame.display.set_mode((1200,800))
pygame.display.set_caption("front_end")

threading.Thread(target=Data.update_backend, daemon=True).start()

clock = pygame.time.Clock()

##map image and scaling
mapImage=pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (1000, 800))

# ── helper functions ──────────────────────────────────────────────
def scale_img(img, target_width=90):
    orig_w, orig_h = img.get_size()
    target_height = int(target_width * orig_h / orig_w)
    return pygame.transform.smoothscale(img, (target_width, target_height))

def remove_white_background(img, threshold=240):
    img = img.convert_alpha()
    pixels = pygame.surfarray.pixels3d(img)
    alpha = pygame.surfarray.pixels_alpha(img)
    mask = (pixels[:,:,0] > threshold) & \
           (pixels[:,:,1] > threshold) & \
           (pixels[:,:,2] > threshold)
    alpha[mask] = 0
    del pixels, alpha
    return img

# ── load & process images ─────────────────────────────────────────
hulk_img          = scale_img(remove_white_background(pygame.image.load("logos/hulk_logo.png").convert_alpha()))
stormForce_img    = scale_img(remove_white_background(pygame.image.load("logos/stormForce_logo.png").convert_alpha()))
doctorDoom_img    = scale_img(remove_white_background(pygame.image.load("logos/Doctor-dooms-fearfall-ride-logo-b.png").convert_alpha()))
spiderMan_img     = scale_img(remove_white_background(pygame.image.load("logos/Amazing-adventures-spider-man-ride-logo-b.png").convert_alpha()))
ripsawFalls_img   = scale_img(remove_white_background(pygame.image.load("logos/Dudley-do-rights-ripsaw-falls-water-ride-logo-b.png").convert_alpha()))
riverAdventure_img= scale_img(remove_white_background(pygame.image.load("logos/jurrasicPark.png").convert_alpha()))
bilgeRat_img      = scale_img(remove_white_background(pygame.image.load("logos/bilge_rat.png").convert_alpha()))
skullIsland_img   = scale_img(remove_white_background(pygame.image.load("logos/Skull_Island-_Reign_of_Kong_Logo.png").convert_alpha()))
velociCoaster_img = scale_img(remove_white_background(pygame.image.load("logos/velocicoaster.png").convert_alpha()))
hogwartsTrain_img = scale_img(remove_white_background(pygame.image.load("logos/express.png").convert_alpha()))
hippogriff_img    = scale_img(remove_white_background(pygame.image.load("logos/hippogriph.png").convert_alpha()))
hagrid_img        = scale_img(remove_white_background(pygame.image.load("logos/Hagrid27s_Magical_Creatures_Motorbike_Adventure.png").convert_alpha()))
harryPotter_img   = scale_img(remove_white_background(pygame.image.load("logos/hogwarts.png").convert_alpha()))
catInTheHat_img   = scale_img(remove_white_background(pygame.image.load("logos/cat.png").convert_alpha()))
oneFishtwoFish_img= scale_img(remove_white_background(pygame.image.load("logos/blue.png").convert_alpha()))
drSeussAirRide_img= scale_img(remove_white_background(pygame.image.load("logos/seuss.png").convert_alpha()))
caroSeussel_img   = scale_img(remove_white_background(pygame.image.load("logos/caro.png").convert_alpha()))

# ── ride image dict ───────────────────────────────────────────────
ride_images = {
    "hulk":           hulk_img,
    "stormForce":     stormForce_img,
    "doctorDoom":     doctorDoom_img,
    "spiderMan":      spiderMan_img,
    "bilgeRat":       bilgeRat_img,
    "ripsawFalls":    ripsawFalls_img,
    "skullIsland":    skullIsland_img,
    "velociCoaster":  velociCoaster_img,
    "riverAdventure": riverAdventure_img,
    "hogwartsTrain":  hogwartsTrain_img,
    "hippogriff":     hippogriff_img,
    "hagrid":         hagrid_img,
    "drSeussAirRide": drSeussAirRide_img,
    "caroSeussel":    caroSeussel_img,
    "oneFishtwoFish": oneFishtwoFish_img,
    "catInTheHat":    catInTheHat_img,
    "harryPotter":    harryPotter_img,
}

ride_names = {
    "hulk": "The Incredible Hulk Coaster",
    "stormForce": "Storm Force Accelatron",
    "doctorDoom": "Doctor Doom's Fearfall",
    "spiderMan": "The Amazing Adventures of Spider-Man",
    "bilgeRat": "Popeye & Bluto's Bilge-Rat Barges",
    "ripsawFalls": "Dudley Do-Right's Ripsaw Falls",
    "skullIsland": "Skull Island: Reign of Kong",
    "velociCoaster": "Jurassic World VelociCoaster",
    "riverAdventure": "Jurassic Park River Adventure",
    "hogwartsTrain": "Hogwarts Express",
    "hippogriff": "Flight of the Hippogriff",
    "hagrid": "Hagrid's Magical Creatures Motorbike Adventure",
    "drSeussAirRide": "High in the Sky Seuss Trolley Train Ride",
    "caroSeussel": "Caro-Seuss-el",
    "oneFishtwoFish": "One Fish, Two Fish, Red Fish, Blue Fish",
    "catInTheHat": "The Cat in the Hat",
    "harryPotter": "Harry Potter and the Forbidden Journey"
}

# ── buttons: [x, y, clicked, ride_id, rect] ──────────────────────
raw_buttons = [
    [490, 620, False, "hulk"],
    [457, 622, False, "stormForce"],
    [404, 574, False, "doctorDoom"],
    [410, 530, False, "spiderMan"],
    [394, 380, False, "bilgeRat"],
    [276, 379, False, "ripsawFalls"],
    [271, 246, False, "skullIsland"],
    [514, 308, False, "velociCoaster"],
    [412, 217, False, "riverAdventure"],
    [745, 204, False, "hogwartsTrain"],
    [635, 186, False, "hippogriff"],
    [717, 248, False, "hagrid"],
    [715, 495, False, "drSeussAirRide"],
    [715, 495, False, "caroSeussel"],
    [714, 572, False, "oneFishtwoFish"],
    [695, 597, False, "catInTheHat"],
    [605, 192, False, "harryPotter"],
]

# attach a rect to each button
buttons = []
for b in raw_buttons:
    x, y, clicked, ride_id = b
    if ride_id in ride_images:
        rect = ride_images[ride_id].get_rect(center=(x, y))
    else:
        rect = pygame.Rect(x - 10, y - 10, 20, 20)
    buttons.append([x, y, clicked, ride_id, rect])

popup = None

# ── main loop ─────────────────────────────────────────────────────
running = True

while running:

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            popup = None

            for button in buttons:
                x, y, clicked, ride_id, rect = button[0], button[1], button[2], button[3], button[4]

                if rect.collidepoint(mx, my):

                    # deselect all
                    for b in buttons:
                        b[2] = False

                    # select clicked
                    button[2] = True

                    display_name = ride_names.get(ride_id, ride_id)

                    wait = Data.ride_waits.get(ride_id, None)

                    if wait is None:
                        text = f"{display_name}\nLoading..."
                    else:
                        text = f"{display_name} - {wait} min"

                    popup = (x + 15, y - 15, text)
                    break

    # ── draw ──────────────────────────────────────────────────────
    screen.fill((255, 255, 255))
    screen.blit(mapImage, (0, 0))

    for button in buttons:
        x, y, clicked, ride_id, rect = button[0], button[1], button[2], button[3], button[4]

        if ride_id in ride_images:
            img = ride_images[ride_id]
            screen.blit(img, rect)
        else:
            color = (0, 255, 0) if clicked else (255, 0, 0)
            pygame.draw.circle(screen, color, (x, y), 10)

    if popup is not None:
        px, py, text = popup
        lines = text.split("\n")
        box_w, box_h = 150, 20 + len(lines) * 18
        pygame.draw.rect(screen, (30, 30, 30), (px, py, box_w, box_h))
        pygame.draw.rect(screen, (255, 255, 255), (px, py, box_w, box_h), 2)
        font = pygame.font.SysFont("Arial", 14)
        for i, line in enumerate(lines):
            label = font.render(line, True, (255, 255, 255))
            screen.blit(label, (px + 10, py + 10 + i * 18))

    pygame.display.update()
    clock.tick(60)

pygame.quit()