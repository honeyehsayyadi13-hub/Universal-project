" Program that shows a user an optimized map of getting to rides at the amusement park Universal"
import pygame
import threading
import Data
 
 
pygame.init()
 
screen = pygame.display.set_mode((1200, 800))
pygame.display.set_caption("front_end")
 
threading.Thread(target=Data.update_backend, daemon=True).start()
 
clock = pygame.time.Clock()
 
# ── map image and scaling ──────────────────────────────────────────
mapImage = pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (1000, 800))
 
 
# ── helper functions ───────────────────────────────────────────────
def scale_img(img, target_width=90):
    orig_w, orig_h = img.get_size()
    target_height = int(target_width * orig_h / orig_w)
    return pygame.transform.smoothscale(img, (target_width, target_height))
 
 
def remove_white_background(img, threshold=240):
    img = img.convert_alpha()
    pixels = pygame.surfarray.pixels3d(img)
    alpha = pygame.surfarray.pixels_alpha(img)
    mask = (
        (pixels[:, :, 0] > threshold)
        & (pixels[:, :, 1] > threshold)
        & (pixels[:, :, 2] > threshold)
    )
    alpha[mask] = 0
    del pixels, alpha
    return img
 
 
def draw_speech_bubble(surface, px, py, lines, font,
                        padding=12, tail_h=14, tail_w=18, radius=10,
                        bg_color=(255, 255, 255), border_color=(30, 30, 30),
                        text_color=(20, 20, 20), border_width=2):
    """
    Draw a programmatic speech bubble with a downward tail, dynamically
    sized to fit `lines` of text.
 
    Parameters
    ----------
    px, py   : tip position of the tail (i.e. where the bubble points to)
    lines    : list of strings to render inside the bubble
    font     : pygame.font.Font used for measuring / rendering text
    """
    line_h = font.get_linesize()
    text_w = max(font.size(l)[0] for l in lines) if lines else 60
 
    box_w = text_w + padding * 2
    box_h = line_h * len(lines) + padding * 2
 
    # Position bubble so tail tip lands at (px, py).
    # Bubble sits above py; tail_h is the triangle height below the box.
    bx = px - box_w // 2          # left edge of box
    by = py - box_h - tail_h      # top edge of box
 
    # ── build a surface big enough for box + tail ──────────────────
    surf_w = box_w + border_width * 2
    surf_h = box_h + tail_h + border_width * 2
    bubble = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
 
    ox, oy = border_width, border_width  # drawing origin inside surf
 
    # ── rounded rectangle (body) ───────────────────────────────────
    body_rect = pygame.Rect(ox, oy, box_w, box_h)
 
    # filled body
    pygame.draw.rect(bubble, bg_color, body_rect, border_radius=radius)
    # border
    pygame.draw.rect(bubble, border_color, body_rect,
                     width=border_width, border_radius=radius)
 
    # ── tail (downward-pointing triangle) ─────────────────────────
    tail_tip_x = ox + box_w // 2          # horizontal centre of box
    tail_base_y = oy + box_h              # bottom of box
    tail_tip_y  = tail_base_y + tail_h   # tip of tail
 
    tail_left  = tail_tip_x - tail_w // 2
    tail_right = tail_tip_x + tail_w // 2
 
    # filled triangle (cover the bottom border line so it looks seamless)
    pygame.draw.polygon(bubble, bg_color, [
        (tail_left,  tail_base_y + border_width),
        (tail_right, tail_base_y + border_width),
        (tail_tip_x, tail_tip_y),
    ])
    # border on the two outer edges of the tail
    pygame.draw.line(bubble, border_color,
                     (tail_left,  tail_base_y), (tail_tip_x, tail_tip_y), border_width)
    pygame.draw.line(bubble, border_color,
                     (tail_right, tail_base_y), (tail_tip_x, tail_tip_y), border_width)
 
    # ── blit text ──────────────────────────────────────────────────
    for i, line in enumerate(lines):
        label = font.render(line, True, text_color)
        lx = ox + padding + (text_w - font.size(line)[0]) // 2  # centre each line
        ly = oy + padding + i * line_h
        bubble.blit(label, (lx, ly))
 
    # ── blit finished bubble onto main surface ────────────────────
    # Place so tail tip aligns with (px, py)
    dest_x = px - box_w // 2 - border_width
    dest_y = py - box_h - tail_h - border_width
    surface.blit(bubble, (dest_x, dest_y))
 
 
# ── load & process images ──────────────────────────────────────────
hulk_img           = scale_img(remove_white_background(pygame.image.load("logos/hulk_logo.png").convert_alpha()))
stormForce_img     = scale_img(remove_white_background(pygame.image.load("logos/stormForce_logo.png").convert_alpha()))
doctorDoom_img     = scale_img(remove_white_background(pygame.image.load("logos/Doctor-dooms-fearfall-ride-logo-b.png").convert_alpha()))
spiderMan_img      = scale_img(remove_white_background(pygame.image.load("logos/Amazing-adventures-spider-man-ride-logo-b.png").convert_alpha()))
ripsawFalls_img    = scale_img(remove_white_background(pygame.image.load("logos/Dudley-do-rights-ripsaw-falls-water-ride-logo-b.png").convert_alpha()))
riverAdventure_img = scale_img(remove_white_background(pygame.image.load("logos/jurrasicPark.png").convert_alpha()))
bilgeRat_img       = scale_img(remove_white_background(pygame.image.load("logos/bilge_rat.png").convert_alpha()))
skullIsland_img    = scale_img(remove_white_background(pygame.image.load("logos/Skull_Island-_Reign_of_Kong_Logo.png").convert_alpha()))
velociCoaster_img  = scale_img(remove_white_background(pygame.image.load("logos/velocicoaster.png").convert_alpha()))
hogwartsTrain_img  = scale_img(remove_white_background(pygame.image.load("logos/express.png").convert_alpha()))
hippogriff_img     = scale_img(remove_white_background(pygame.image.load("logos/hippogriph.png").convert_alpha()))
hagrid_img         = scale_img(remove_white_background(pygame.image.load("logos/Hagrid27s_Magical_Creatures_Motorbike_Adventure.png").convert_alpha()))
harryPotter_img    = scale_img(remove_white_background(pygame.image.load("logos/hogwarts.png").convert_alpha()))
catInTheHat_img    = scale_img(remove_white_background(pygame.image.load("logos/cat.png").convert_alpha()))
oneFishtwoFish_img = scale_img(remove_white_background(pygame.image.load("logos/blue.png").convert_alpha()))
drSeussAirRide_img = scale_img(remove_white_background(pygame.image.load("logos/seuss.png").convert_alpha()))
caroSeussel_img    = scale_img(remove_white_background(pygame.image.load("logos/caro.png").convert_alpha()))
 
# ── ride image dict ────────────────────────────────────────────────
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
 
# ── ride display names ─────────────────────────────────────────────
ride_names = {
    "hulk":           "The Incredible Hulk Coaster",
    "stormForce":     "Storm Force Accelatron",
    "doctorDoom":     "Doctor Doom's Fearfall",
    "spiderMan":      "The Amazing Adventures of\nSpider-Man",
    "bilgeRat":       "Popeye & Bluto's\nBilge-Rat Barges",
    "ripsawFalls":    "Dudley Do-Right's\nRipsaw Falls",
    "skullIsland":    "Skull Island: Reign of Kong",
    "velociCoaster":  "Jurassic World\nVelociCoaster",
    "riverAdventure": "Jurassic Park\nRiver Adventure",
    "hogwartsTrain":  "Hogwarts Express",
    "hippogriff":     "Flight of the Hippogriff",
    "hagrid":         "Hagrid's Magical Creatures\nMotorbike Adventure",
    "drSeussAirRide": "High in the Sky\nSeuss Trolley Train Ride",
    "caroSeussel":    "Caro-Seuss-el",
    "oneFishtwoFish": "One Fish, Two Fish,\nRed Fish, Blue Fish",
    "catInTheHat":    "The Cat in the Hat",
    "harryPotter":    "Harry Potter and the\nForbidden Journey",
}
 
# ── buttons: [x, y, clicked, ride_id, rect] ───────────────────────
raw_buttons = [
    [488, 620, False, "hulk"],
    [469, 654, False, "stormForce"],
    [411, 572, False, "doctorDoom"],
    [418, 527, False, "spiderMan"],
    [394, 380, False, "bilgeRat"],
    [276, 379, False, "ripsawFalls"],
    [271, 246, False, "skullIsland"],
    [514, 308, False, "velociCoaster"],
    [412, 217, False, "riverAdventure"],
    [832, 262, False, "hogwartsTrain"],
    [668, 165, False, "hippogriff"],
    [742, 218, False, "hagrid"],
    [715, 495, False, "drSeussAirRide"],
    [715, 495, False, "caroSeussel"],
    [741, 562, False, "oneFishtwoFish"],
    [683, 631, False, "catInTheHat"],
    [595, 182, False, "harryPotter"],
]
 
buttons = []
for b in raw_buttons:
    x, y, clicked, ride_id = b
    if ride_id in ride_images:
        rect = ride_images[ride_id].get_rect(center=(x, y))
    else:
        rect = pygame.Rect(x - 10, y - 10, 20, 20)
    buttons.append([x, y, clicked, ride_id, rect])
 
popup = None  # (anchor_x, anchor_y, lines_list)
 
popup_font       = pygame.font.SysFont("Arial", 13, bold=False)
popup_font_bold  = pygame.font.SysFont("Arial", 13, bold=True)
 
# ── main loop ──────────────────────────────────────────────────────
running = True
 
while running:
 
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
 
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            popup = None
 
            for button in buttons:
                x, y, clicked, ride_id, rect = button
 
                if rect.collidepoint(mx, my):
                    for b in buttons:
                        b[2] = False
                    button[2] = True
 
                    display_name = ride_names.get(ride_id, ride_id)
                    wait = Data.ride_waits.get(ride_id, None)
                    wait_str = "Loading..." if wait is None else "Ride is currently closed" if wait is 0 else f"Wait: {wait} min"
 
                    # Split name lines + wait line
                    name_lines = display_name.split("\n")
                    all_lines  = name_lines + [wait_str]
 
                    # anchor = top-centre of the ride icon
                    anchor_x = rect.centerx
                    anchor_y = rect.top
                    popup = (anchor_x, anchor_y, all_lines)
                    break
 
    # ── draw ───────────────────────────────────────────────────────
    screen.fill((255, 255, 255))
    screen.blit(mapImage, (0, 0))
 
    for button in buttons:
        x, y, clicked, ride_id, rect = button
        if ride_id in ride_images:
            screen.blit(ride_images[ride_id], rect)
        else:
            color = (0, 200, 0) if clicked else (200, 0, 0)
            pygame.draw.circle(screen, color, (x, y), 10)
 
    if popup is not None:
        anchor_x, anchor_y, lines = popup
        draw_speech_bubble(
            screen,
            px=anchor_x,
            py=anchor_y,          # tail tip touches the top of the icon
            lines=lines,
            font=popup_font,
            padding=10,
            tail_h=12,
            tail_w=16,
            radius=8,
            bg_color=(255, 255, 255),
            border_color=(50, 50, 50),
            text_color=(20, 20, 20),
            border_width=2,
        )
 
    pygame.display.update()
    clock.tick(60)
 
pygame.quit()