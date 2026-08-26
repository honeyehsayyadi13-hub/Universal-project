#frontEnd.py
"""Program that shows a user an optimized map of getting to rides at the amusement park Universal"""
import pygame
import threading
import Data
import routeOptimizer

pygame.init()

# ── layout constants ───────────────────────────────────────────────
SIDEBAR_WIDTH = 260
MAP_WIDTH = 1000
MAP_HEIGHT = 800
TOP_BAR_HEIGHT = 90   # new route bar above the map; pushes the map down
SCREEN_WIDTH = SIDEBAR_WIDTH + MAP_WIDTH
SCREEN_HEIGHT = MAP_HEIGHT + TOP_BAR_HEIGHT

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("front_end")

threading.Thread(target=Data.update_backend, daemon=True).start()

clock = pygame.time.Clock()

# ── map image and scaling ──────────────────────────────────────────
mapImage = pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (MAP_WIDTH, MAP_HEIGHT))


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

# ── ride visibility toggles (one bool per ride, default: all checked/on) ──
ride_visible = {ride_id: True for ride_id in ride_names}

# ── ride quantity counters (one int per ride, min 0, default 1) ──────
ride_counts = {ride_id: 1 for ride_id in ride_names}
RIDE_COUNT_MIN = 0

# remembers each ride's count from just before it was unchecked, so
# rechecking it can restore that value instead of resetting to 1
ride_last_count = {ride_id: 1 for ride_id in ride_names}

# ── ride lock toggles (one bool per ride, True = locked, default: unlocked) ──
# A ride can only be locked while it is checked AND its count is > 0.
# If it gets unchecked or its count drops to 0, it is automatically unlocked.
ride_locked = {ride_id: False for ride_id in ride_names}

# Whenever a ride's count first crosses from 1 -> 2 it gets auto-locked.
# This remembers whatever ride_locked was *right before* that happened, so
# that if the count later drops back down to 1, we know whether to auto
# -unlock it again or leave it locked (because the user had locked it
# manually beforehand, independent of the count).
ride_lock_before_bump = {ride_id: False for ride_id in ride_names}

# ── the most recently generated route (list of ride_id strings, in visit
# order) -- drawn in the new top bar. Updated by _run_route_computation()
# once the background thread finishes. Empty until the first successful run.
current_route = []

# ── buttons: [x, y, clicked, ride_id, rect] ───────────────────────
# NOTE: x/y below are in "map-local" coordinates (0-1000 / 0-800). We shift
# x by SIDEBAR_WIDTH and y by TOP_BAR_HEIGHT so they land in the right place
# on the wider/taller screen (sidebar on the left, route bar on top).
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
    sx = x + SIDEBAR_WIDTH   # shifted x, since map now starts after the sidebar
    sy = y + TOP_BAR_HEIGHT  # shifted y, since map now starts below the top bar
    if ride_id in ride_images:
        rect = ride_images[ride_id].get_rect(center=(sx, sy))
    else:
        rect = pygame.Rect(sx - 10, sy - 10, 20, 20)
    buttons.append([sx, sy, clicked, ride_id, rect])

# popup is either None or (ride_id, anchor_x, anchor_y, lines_list).
# Storing ride_id lets us auto-hide the bubble the moment its ride gets
# unchecked (via the sidebar checkbox OR the spinner dropping to 0),
# instead of it lingering on screen for a ride that's no longer selected.
popup = None

popup_font       = pygame.font.SysFont("Arial", 13, bold=False)
popup_font_bold  = pygame.font.SysFont("Arial", 13, bold=True)

# ── sidebar checklist setup ────────────────────────────────────────
SIDEBAR_BG_COLOR       = (245, 245, 245)
SIDEBAR_BORDER_COLOR   = (180, 180, 180)
CHECKBOX_SIZE          = 18
CHECKBOX_MARGIN_LEFT   = 14
CHECKBOX_CHECKED_COLOR = (40, 160, 70)
CHECKBOX_BORDER_COLOR  = (60, 60, 60)
LABEL_COLOR            = (20, 20, 20)

sidebar_font = pygame.font.SysFont("Arial", 14)
sidebar_title_font = pygame.font.SysFont("Arial", 18, bold=True)

TITLE_H = 40

# ── quantity spinner (number + up/down arrows) layout ───────────────
SPIN_RIGHT_MARGIN = 10   # gap from the sidebar's right border
SPIN_ARROW_SIZE   = 11   # width/height of each arrow's clickable box
SPIN_ARROW_GAP    = 3    # gap between arrow boxes and the number
SPIN_NUM_W        = 20   # width reserved for the number text
SPIN_AREA_W       = SPIN_ARROW_SIZE * 2 + SPIN_ARROW_GAP * 2 + SPIN_NUM_W
SPIN_ARROW_BG          = (255, 255, 255)
SPIN_ARROW_BORDER      = (60, 60, 60)
SPIN_ARROW_TRIANGLE    = (60, 60, 60)
SPIN_ARROW_DISABLED    = (200, 200, 200)
spin_num_font = pygame.font.SysFont("Arial", 13, bold=True)

# ── lock icon (sits just to the left of the quantity spinner) ───────
LOCK_SIZE           = 14   # width/height of the lock icon's clickable box
LOCK_GAP            = 6    # gap between the lock icon and the spinner group
LOCK_COLOR = (70, 70, 70)  # same solid color for both locked/unlocked shapes
LOCK_DISABLED_ALPHA = 110  # alpha used when the lock isn't interactive (half-transparent)

# ── "Get Optimal Route" button (reserved at the bottom of the sidebar) ──
ROUTE_BUTTON_H = 46
ROUTE_BUTTON_MARGIN = 12
ROUTE_BUTTON_COLOR = (30, 110, 200)
ROUTE_BUTTON_HOVER_COLOR = (20, 90, 170)
ROUTE_BUTTON_TEXT_COLOR = (255, 255, 255)
route_button_font = pygame.font.SysFont("Arial", 15, bold=True)

route_button_rect = pygame.Rect(
    CHECKBOX_MARGIN_LEFT,
    SCREEN_HEIGHT - ROUTE_BUTTON_H - ROUTE_BUTTON_MARGIN,
    SIDEBAR_WIDTH - CHECKBOX_MARGIN_LEFT * 2,
    ROUTE_BUTTON_H,
)


def _truncate_label(text, font, max_w):
    """Shorten `text` with a trailing ellipsis so it renders within max_w px."""
    if font.size(text)[0] <= max_w:
        return text
    ellipsis = "..."
    truncated = text
    while truncated and font.size(truncated + ellipsis)[0] > max_w:
        truncated = truncated[:-1]
    return truncated + ellipsis if truncated else ellipsis


# ── starting-location dropdown (sits next to the "Rides" title) ─────
# Lets the user pick where the route should start from. "Entrance" is
# the default and corresponds to id 0 in the Supabase `rides` table;
# picking any other ride uses that ride's short key instead.
DROPDOWN_H           = 24
DROPDOWN_ITEM_H      = 22
DROPDOWN_BG          = (255, 255, 255)
DROPDOWN_BORDER      = (60, 60, 60)
DROPDOWN_HOVER_COLOR = (225, 235, 250)
DROPDOWN_SELECTED_BG = (235, 245, 255)
DROPDOWN_TEXT_COLOR  = (20, 20, 20)
dropdown_font = pygame.font.SysFont("Arial", 13)

dropdown_open = False
selected_start = "entrance"  # currently chosen starting location's short key

# (key, display label) for every choice -- "Entrance" first, then every ride
start_options = [("entrance", "Entrance")]
for _ride_id, _name in ride_names.items():
    start_options.append((_ride_id, _name.replace("\n", " ")))
start_label_map = dict(start_options)

title_surface = sidebar_title_font.render("Rides", True, LABEL_COLOR)
dropdown_rect = pygame.Rect(
    CHECKBOX_MARGIN_LEFT + title_surface.get_width() + 10,
    (TITLE_H - DROPDOWN_H) // 2,
    SIDEBAR_WIDTH - (CHECKBOX_MARGIN_LEFT + title_surface.get_width() + 10) - CHECKBOX_MARGIN_LEFT,
    DROPDOWN_H,
)

# Precompute each dropdown item's rect + truncated label surface once.
dropdown_items = []  # list of (key, label_surface, item_rect)
for _i, (_key, _label) in enumerate(start_options):
    _item_rect = pygame.Rect(
        dropdown_rect.left,
        dropdown_rect.bottom + _i * DROPDOWN_ITEM_H,
        dropdown_rect.width,
        DROPDOWN_ITEM_H,
    )
    _short_label = _truncate_label(_label, dropdown_font, dropdown_rect.width - 16)
    _item_label_surface = dropdown_font.render(_short_label, True, DROPDOWN_TEXT_COLOR)
    dropdown_items.append((_key, _item_label_surface, _item_rect))


def _draw_dropdown_button(surface):
    """Draws the title text and the closed dropdown button (always visible)."""
    surface.blit(title_surface, (CHECKBOX_MARGIN_LEFT, 8))

    pygame.draw.rect(surface, DROPDOWN_BG, dropdown_rect, border_radius=4)
    pygame.draw.rect(surface, DROPDOWN_BORDER, dropdown_rect, width=1, border_radius=4)

    current_label = _truncate_label(start_label_map[selected_start], dropdown_font, dropdown_rect.width - 24)
    label_surface = dropdown_font.render(current_label, True, DROPDOWN_TEXT_COLOR)
    surface.blit(label_surface, (dropdown_rect.left + 8, dropdown_rect.centery - label_surface.get_height() // 2))

    ax, ay = dropdown_rect.right - 14, dropdown_rect.centery
    if dropdown_open:
        pts = [(ax - 5, ay + 2), (ax + 5, ay + 2), (ax, ay - 3)]
    else:
        pts = [(ax - 5, ay - 3), (ax + 5, ay - 3), (ax, ay + 3)]
    pygame.draw.polygon(surface, DROPDOWN_BORDER, pts)


def _draw_dropdown_list(surface):
    """Draws the open item list on top of everything else, if it's open."""
    if not dropdown_open:
        return
    mx, my = pygame.mouse.get_pos()
    list_h = len(dropdown_items) * DROPDOWN_ITEM_H
    panel_rect = pygame.Rect(dropdown_rect.left, dropdown_rect.bottom, dropdown_rect.width, list_h)
    pygame.draw.rect(surface, DROPDOWN_BG, panel_rect)

    for key, label_surface, item_rect in dropdown_items:
        if item_rect.collidepoint(mx, my):
            bg = DROPDOWN_HOVER_COLOR
        elif key == selected_start:
            bg = DROPDOWN_SELECTED_BG
        else:
            bg = DROPDOWN_BG
        pygame.draw.rect(surface, bg, item_rect)
        surface.blit(label_surface, (item_rect.left + 8, item_rect.centery - label_surface.get_height() // 2))

    pygame.draw.rect(surface, DROPDOWN_BORDER, panel_rect, width=1)


# ── break entries (dynamic list, prepended to the ride list) ────────
# Each entry is {"id": int, "label": str, "start_min": int, "end_min": int}.
# start_min/end_min are minutes-since-midnight so the optimizer can turn
# them into real datetimes. Newly generated breaks are inserted at the
# front so they always show up as the first row.
breaks = []
_break_id_counter = 0

# ── break time-entry boxes + "Generate Break" button ─────────────────
# Sits directly below the starting-location dropdown row.
BREAK_INPUT_H   = 24
BREAK_ROW_GAP   = 6
BREAK_BTN_H     = 28
BREAK_SECTION_TOP = TITLE_H + 8
BREAK_SECTION_H   = BREAK_INPUT_H + BREAK_ROW_GAP + BREAK_BTN_H + 10

BREAK_INPUT_BG            = (255, 255, 255)
BREAK_INPUT_BORDER        = (150, 150, 150)
BREAK_INPUT_BORDER_ACTIVE = (30, 110, 200)
BREAK_INPUT_TEXT_COLOR    = (20, 20, 20)
BREAK_INPUT_PLACEHOLDER_COLOR = (160, 160, 160)
BREAK_BTN_COLOR       = (200, 60, 60)
BREAK_BTN_HOVER_COLOR = (170, 40, 40)
BREAK_BTN_TEXT_COLOR  = (255, 255, 255)
DELETE_X_COLOR        = (190, 40, 40)

break_input_font = pygame.font.SysFont("Arial", 13)
break_btn_font   = pygame.font.SysFont("Arial", 14, bold=True)

time1_text = ""
time2_text = ""
active_time_input = None  # None | "time1" | "time2"

# ── error-flash state ────────────────────────────────────────────────
# When an entry is invalid, both boxes show "ERROR" for this long (ms)
# before clearing themselves.
TIME_ERROR_DURATION_MS = 2000
time_error_active = False
time_error_end_ms = 0

import re as _re

_TIME_INPUT_RE = _re.compile(r'(\d{1,2})(?::(\d{2}))?')


def _parse_time_input(text):
    """Parses 'H' or 'H:MM' (hour 1-12, minute 0-59). Returns (hour, minute)
    or None if the text isn't a valid time at all."""
    text = text.strip()
    if not text:
        return None
    match = _TIME_INPUT_RE.fullmatch(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    if not (1 <= hour <= 12) or not (0 <= minute <= 59):
        return None
    return hour, minute


def _to_ampm(hour, minute):
    """Universal's park day runs 9am-9pm with no AM/PM typed in: a bare hour
    of 9, 10, or 11 is AM; 12 and 1-8 are PM. Returns (minutes_since_midnight,
    display_label) so two parsed times can be compared and shown."""
    if hour in (9, 10, 11):
        period = "AM"
        hour24 = hour
    else:
        period = "PM"
        hour24 = 12 if hour == 12 else hour + 12
    total_minutes = hour24 * 60 + minute
    label = f"{hour}:{minute:02d} {period}"
    return total_minutes, label


def _trigger_time_error():
    global time_error_active, time_error_end_ms, time1_text, time2_text
    time_error_active = True
    time_error_end_ms = pygame.time.get_ticks() + TIME_ERROR_DURATION_MS
    time1_text = ""
    time2_text = ""

_dash_w = dropdown_font.render("-", True, LABEL_COLOR).get_width()
_input_w = (SIDEBAR_WIDTH - CHECKBOX_MARGIN_LEFT * 2 - _dash_w - 12) // 2

time1_rect = pygame.Rect(CHECKBOX_MARGIN_LEFT, BREAK_SECTION_TOP, _input_w, BREAK_INPUT_H)
time2_rect = pygame.Rect(time1_rect.right + _dash_w + 12, BREAK_SECTION_TOP, _input_w, BREAK_INPUT_H)

generate_break_rect = pygame.Rect(
    CHECKBOX_MARGIN_LEFT,
    BREAK_SECTION_TOP + BREAK_INPUT_H + BREAK_ROW_GAP,
    SIDEBAR_WIDTH - CHECKBOX_MARGIN_LEFT * 2,
    BREAK_BTN_H,
)

# top of the scrollable-looking checklist -- everything (breaks + rides)
# is laid out below this point, above the "Get Optimal Route" button.
LIST_TOP = BREAK_SECTION_TOP + BREAK_SECTION_H

list_area_h = 0
row_h = 0
sidebar_rows = []  # list of dicts, either type "break" or type "ride"


def rebuild_sidebar_rows():
    """Recomputes every row's rects/labels. Call whenever `breaks` changes,
    since adding/removing a break changes how many rows share the list area."""
    global list_area_h, row_h, sidebar_rows

    total_rows = len(breaks) + len(ride_names)
    list_area_h = route_button_rect.top - LIST_TOP
    row_h = list_area_h // total_rows if total_rows else list_area_h

    sidebar_rows = []
    row_index = 0

    # breaks show first (most recently generated on top)
    for b in breaks:
        row_top = LIST_TOP + row_index * row_h
        x_rect = pygame.Rect(
            CHECKBOX_MARGIN_LEFT,
            row_top + (row_h - CHECKBOX_SIZE) // 2,
            CHECKBOX_SIZE,
            CHECKBOX_SIZE,
        )
        label_x = x_rect.right + 10
        label_max_w = SIDEBAR_WIDTH - CHECKBOX_MARGIN_LEFT - label_x
        short_label = _truncate_label(b["label"], sidebar_font, label_max_w)
        label_surface = sidebar_font.render(short_label, True, LABEL_COLOR)

        sidebar_rows.append({
            "type": "break",
            "id": b["id"],
            "row_top": row_top,
            "x_rect": x_rect,
            "label_surface": label_surface,
        })
        row_index += 1

    # then every ride, in their fixed order
    for ride_id, name in ride_names.items():
        row_top = LIST_TOP + row_index * row_h
        cb_rect = pygame.Rect(
            CHECKBOX_MARGIN_LEFT,
            row_top + (row_h - CHECKBOX_SIZE) // 2,
            CHECKBOX_SIZE,
            CHECKBOX_SIZE,
        )

        # spinner: [down][number][up], with the lock icon rightmost against the sidebar edge
        lock_rect = pygame.Rect(
            SIDEBAR_WIDTH - SPIN_RIGHT_MARGIN - LOCK_SIZE,
            row_top + (row_h - LOCK_SIZE) // 2,
            LOCK_SIZE,
            LOCK_SIZE,
        )
        up_rect = pygame.Rect(
            lock_rect.left - LOCK_GAP - SPIN_ARROW_SIZE,
            row_top + (row_h - SPIN_ARROW_SIZE) // 2,
            SPIN_ARROW_SIZE,
            SPIN_ARROW_SIZE,
        )
        num_right = up_rect.left - SPIN_ARROW_GAP
        num_left = num_right - SPIN_NUM_W
        down_rect = pygame.Rect(
            num_left - SPIN_ARROW_GAP - SPIN_ARROW_SIZE,
            row_top + (row_h - SPIN_ARROW_SIZE) // 2,
            SPIN_ARROW_SIZE,
            SPIN_ARROW_SIZE,
        )

        label_x = cb_rect.right + 10
        label_max_w = down_rect.left - 6 - label_x
        single_line = _truncate_label(name.replace("\n", " "), sidebar_font, label_max_w)
        label_surface = sidebar_font.render(single_line, True, LABEL_COLOR)

        sidebar_rows.append({
            "type": "ride",
            "ride_id": ride_id,
            "row_top": row_top,
            "cb_rect": cb_rect,
            "label_surface": label_surface,
            "down_rect": down_rect,
            "up_rect": up_rect,
            "num_left": num_left,
            "num_right": num_right,
            "lock_rect": lock_rect,
        })
        row_index += 1


rebuild_sidebar_rows()


def _draw_spin_arrow(surface, rect, pointing_up, enabled=True):
    color = SPIN_ARROW_TRIANGLE if enabled else SPIN_ARROW_DISABLED
    pygame.draw.rect(surface, SPIN_ARROW_BG, rect, border_radius=3)
    pygame.draw.rect(surface, SPIN_ARROW_BORDER, rect, width=1, border_radius=3)
    pad = 2
    if pointing_up:
        pts = [
            (rect.left + pad, rect.bottom - pad),
            (rect.right - pad, rect.bottom - pad),
            (rect.centerx, rect.top + pad),
        ]
    else:
        pts = [
            (rect.left + pad, rect.top + pad),
            (rect.right - pad, rect.top + pad),
            (rect.centerx, rect.bottom - pad),
        ]
    pygame.draw.polygon(surface, color, pts)


def _draw_lock_icon(surface, rect, locked, transparent=False):
    """
    Draws a small padlock. `locked` picks the closed vs. open shackle shape.
    `transparent` half-fades the icon -- used only when the ride itself is
    unchecked, not merely because its count is at 0.
    """
    color = LOCK_COLOR

    icon = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

    body_h = int(rect.height * 0.55)
    body_rect = pygame.Rect(0, rect.height - body_h, rect.width, body_h)
    pygame.draw.rect(icon, color, body_rect, border_radius=2)
    # keyhole
    keyhole_center = body_rect.center
    pygame.draw.circle(icon, (255, 255, 255), keyhole_center, max(1, body_rect.height // 6))

    shackle_w = max(4, int(rect.width * 0.6))
    shackle_h = max(4, int(rect.height * 0.55))
    shackle_thickness = 2

    if locked:
        # centered, closed shackle
        shackle_rect = pygame.Rect((rect.width - shackle_w) // 2, 0, shackle_w, shackle_h)
        pygame.draw.arc(icon, color, shackle_rect, 0, 3.14159, shackle_thickness)
        pygame.draw.line(icon, color, (shackle_rect.left, shackle_rect.centery),
                          (shackle_rect.left, body_rect.top + 1), shackle_thickness)
        pygame.draw.line(icon, color, (shackle_rect.right, shackle_rect.centery),
                          (shackle_rect.right, body_rect.top + 1), shackle_thickness)
    else:
        # shifted/open shackle, swung off to one side
        shackle_rect = pygame.Rect((rect.width - shackle_w) // 2 + 3, -1, shackle_w, shackle_h)
        pygame.draw.arc(icon, color, shackle_rect, 0.6, 3.6, shackle_thickness)
        pygame.draw.line(icon, color, (shackle_rect.left + 1, shackle_rect.centery + 1),
                          (shackle_rect.left + 1, body_rect.top + 1), shackle_thickness)

    if transparent:
        icon.set_alpha(LOCK_DISABLED_ALPHA)

    surface.blit(icon, rect.topleft)


def _draw_time_box(surface, rect, text, active, placeholder, error=False):
    border_color = BREAK_INPUT_BORDER_ACTIVE if active else BREAK_INPUT_BORDER
    if error:
        border_color = DELETE_X_COLOR
    pygame.draw.rect(surface, BREAK_INPUT_BG, rect, border_radius=4)
    pygame.draw.rect(surface, border_color, rect, width=2 if (active or error) else 1, border_radius=4)

    if error:
        label = break_input_font.render("ERROR", True, DELETE_X_COLOR)
        surface.blit(label, label.get_rect(center=rect.center))
        return

    if text:
        label = break_input_font.render(text, True, BREAK_INPUT_TEXT_COLOR)
    else:
        label = break_input_font.render(placeholder, True, BREAK_INPUT_PLACEHOLDER_COLOR)
    surface.blit(label, (rect.left + 6, rect.centery - label.get_height() // 2))

    if active:
        cursor_x = rect.left + 6 + (break_input_font.size(text)[0] if text else 0) + 1
        pygame.draw.line(surface, BREAK_INPUT_TEXT_COLOR,
                          (cursor_x, rect.top + 4), (cursor_x, rect.bottom - 4), 1)


def _draw_delete_x(surface, rect):
    pygame.draw.rect(surface, (255, 255, 255), rect, border_radius=3)
    pygame.draw.rect(surface, DELETE_X_COLOR, rect, width=2, border_radius=3)
    pad = 4
    pygame.draw.line(surface, DELETE_X_COLOR, (rect.left + pad, rect.top + pad),
                      (rect.right - pad, rect.bottom - pad), 2)
    pygame.draw.line(surface, DELETE_X_COLOR, (rect.right - pad, rect.top + pad),
                      (rect.left + pad, rect.bottom - pad), 2)


def draw_sidebar(surface, route_button_hover):
    # background panel
    pygame.draw.rect(surface, SIDEBAR_BG_COLOR, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(surface, SIDEBAR_BORDER_COLOR, (SIDEBAR_WIDTH, 0), (SIDEBAR_WIDTH, SCREEN_HEIGHT), 2)

    _draw_dropdown_button(surface)

    # ── break time-entry boxes + Generate Break button ──
    _draw_time_box(surface, time1_rect, time1_text, active_time_input == "time1", "Start", error=time_error_active)
    dash_surface = dropdown_font.render("-", True, LABEL_COLOR)
    dash_x = time1_rect.right + (time2_rect.left - time1_rect.right - dash_surface.get_width()) // 2
    surface.blit(dash_surface, (dash_x, time1_rect.centery - dash_surface.get_height() // 2))
    _draw_time_box(surface, time2_rect, time2_text, active_time_input == "time2", "End", error=time_error_active)

    gen_hover = generate_break_rect.collidepoint(pygame.mouse.get_pos())
    gen_color = BREAK_BTN_HOVER_COLOR if gen_hover else BREAK_BTN_COLOR
    pygame.draw.rect(surface, gen_color, generate_break_rect, border_radius=6)
    gen_label = break_btn_font.render("Generate Break", True, BREAK_BTN_TEXT_COLOR)
    surface.blit(gen_label, gen_label.get_rect(center=generate_break_rect.center))

    # ── list rows: breaks (with red-X delete) then rides (checkbox/spinner/lock) ──
    for row in sidebar_rows:
        row_top = row["row_top"]

        if row["type"] == "break":
            _draw_delete_x(surface, row["x_rect"])
            label_y = row_top + (row_h - row["label_surface"].get_height()) // 2
            surface.blit(row["label_surface"], (row["x_rect"].right + 10, label_y))
            continue

        ride_id = row["ride_id"]
        cb_rect = row["cb_rect"]
        label_surface = row["label_surface"]
        down_rect = row["down_rect"]
        up_rect = row["up_rect"]
        num_left = row["num_left"]
        num_right = row["num_right"]
        lock_rect = row["lock_rect"]

        # checkbox
        pygame.draw.rect(surface, (255, 255, 255), cb_rect, border_radius=3)
        pygame.draw.rect(surface, CHECKBOX_BORDER_COLOR, cb_rect, width=2, border_radius=3)
        if ride_visible[ride_id]:
            inner = cb_rect.inflate(-6, -6)
            pygame.draw.rect(surface, CHECKBOX_CHECKED_COLOR, inner, border_radius=2)

        # label, vertically centered next to checkbox
        label_x = cb_rect.right + 10
        label_y = row_top + (row_h - label_surface.get_height()) // 2
        surface.blit(label_surface, (label_x, label_y))

        # quantity spinner
        count = ride_counts[ride_id]
        _draw_spin_arrow(surface, down_rect, pointing_up=False, enabled=count > RIDE_COUNT_MIN)
        _draw_spin_arrow(surface, up_rect, pointing_up=True, enabled=True)

        num_surface = spin_num_font.render(str(count), True, LABEL_COLOR)
        num_y = row_top + (row_h - num_surface.get_height()) // 2
        num_x = num_left + (num_right - num_left - num_surface.get_width()) // 2
        surface.blit(num_surface, (num_x, num_y))

        # lock icon -- only lockable while checked and count > 0
        lockable = ride_visible[ride_id] and count > RIDE_COUNT_MIN
        if not lockable:
            ride_locked[ride_id] = False  # can't stay "locked" while off/at zero
        _draw_lock_icon(surface, lock_rect, ride_locked[ride_id], transparent=not ride_visible[ride_id])

    # ── "Get Optimal Route" button ──
    color = ROUTE_BUTTON_HOVER_COLOR if route_button_hover else ROUTE_BUTTON_COLOR
    pygame.draw.rect(surface, color, route_button_rect, border_radius=8)
    label = route_button_font.render("Get Optimal Route", True, ROUTE_BUTTON_TEXT_COLOR)
    label_pos = label.get_rect(center=route_button_rect.center)
    surface.blit(label, label_pos)

    # drawn last so the open list overlays the rows/button beneath it
    _draw_dropdown_list(surface)


def trigger_route_computation():
    """Shared by both the sidebar's 'Get Optimal Route' button and the top
    bar's 'Generate Route' button -- snapshots the current selection/live
    data and kicks off the optimizer on a background thread."""
    # only checked rides with a count > 0 are candidates
    selected_counts = {
        ride_id: ride_counts[ride_id]
        for ride_id in ride_names
        if ride_visible[ride_id] and ride_counts[ride_id] > RIDE_COUNT_MIN
    }
    # locked rides among those -- the optimizer force-includes these
    selected_locked = {
        ride_id: True
        for ride_id in ride_names
        if ride_locked[ride_id]
    }

    # Take one consistent snapshot of the live data right now, instead
    # of handing the optimizer thread a live reference into dicts that
    # Data.update_backend() keeps mutating every 5 seconds in the
    # background. Without this, the wait times the optimizer reads
    # while it's mid-calculation could shift out from under it.
    live_waits_snapshot = dict(Data.ride_waits)
    live_open_snapshot = dict(Data.ride_open)

    # A ride is closed if the API's own is_open flag says so -- NOT if
    # its live wait happens to read 0. A 0-min wait is a legitimate
    # walk-on and shouldn't be treated as a closure; conversely a
    # closed ride can still be reporting a stale nonzero wait from
    # before it went down, so wait==0 was both a false-positive and a
    # false-negative detector.
    closed_ride_keys = [
        ride_id for ride_id in ride_names
        if live_open_snapshot.get(ride_id) is False
    ]
    break_windows = [(b["start_min"], b["end_min"]) for b in breaks]

    print(f"\nComputing optimal route for: {selected_counts} "
          f"(locked: {list(selected_locked)}, closed: {closed_ride_keys}, "
          f"starting from: {selected_start})")
    threading.Thread(
        target=_run_route_computation,
        args=(selected_counts, selected_locked, closed_ride_keys, break_windows),
        kwargs={"start_key": selected_start, "live_waits": live_waits_snapshot},
        daemon=True,
    ).start()


def _run_route_computation(counts, locked, closed_keys, break_windows, start_key="entrance", live_waits=None):
    """Runs on a background thread. Calls the optimizer (which still prints
    its usual terminal output) and, if it returned a real result, updates
    `current_route` so the top bar picks it up on the next frame."""
    global current_route
    result = routeOptimizer.compute_and_print_route(
        counts, locked, closed_keys, break_windows,
        start_key=start_key, live_waits=live_waits,
    )
    if result is not None:
        current_route = result


def handle_sidebar_click(mx, my):
    """Returns True if the click was consumed by the sidebar."""
    global dropdown_open, selected_start, active_time_input, time1_text, time2_text, _break_id_counter, popup

    if dropdown_rect.collidepoint(mx, my):
        dropdown_open = not dropdown_open
        active_time_input = None
        return True

    if dropdown_open:
        for key, _label_surface, item_rect in dropdown_items:
            if item_rect.collidepoint(mx, my):
                selected_start = key
                dropdown_open = False
                return True
        # clicked elsewhere while it was open -- just close it
        dropdown_open = False
        return True

    if time_error_active:
        # boxes are locked while flashing "ERROR" -- ignore clicks on them/the button
        if time1_rect.collidepoint(mx, my) or time2_rect.collidepoint(mx, my) \
                or generate_break_rect.collidepoint(mx, my):
            return True

    if time1_rect.collidepoint(mx, my):
        active_time_input = "time1"
        return True

    if time2_rect.collidepoint(mx, my):
        active_time_input = "time2"
        return True

    if generate_break_rect.collidepoint(mx, my):
        active_time_input = None

        t1 = _parse_time_input(time1_text)
        t2 = _parse_time_input(time2_text)

        valid = False
        label1 = label2 = None
        m1 = m2 = None
        if t1 is not None and t2 is not None:
            m1, label1 = _to_ampm(*t1)
            m2, label2 = _to_ampm(*t2)
            valid = m2 > m1  # end must come after start

        if valid:
            _break_id_counter += 1
            breaks.insert(0, {
                "id": _break_id_counter,
                "label": f"Break: {label1} - {label2}",
                "start_min": m1,
                "end_min": m2,
            })
            time1_text = ""
            time2_text = ""
            rebuild_sidebar_rows()
        else:
            _trigger_time_error()
        return True

    active_time_input = None  # any other sidebar click defocuses the time inputs

    if route_button_rect.collidepoint(mx, my):
        trigger_route_computation()
        return True

    for row in sidebar_rows:
        if row["type"] == "break":
            if row["x_rect"].collidepoint(mx, my):
                break_id = row["id"]
                breaks[:] = [b for b in breaks if b["id"] != break_id]
                rebuild_sidebar_rows()
            return True

        ride_id = row["ride_id"]
        cb_rect = row["cb_rect"]
        down_rect = row["down_rect"]
        up_rect = row["up_rect"]
        lock_rect = row["lock_rect"]

        if cb_rect.collidepoint(mx, my):
            ride_visible[ride_id] = not ride_visible[ride_id]
            if ride_visible[ride_id]:
                # re-checked: restore whatever count it had before unchecking
                ride_counts[ride_id] = ride_last_count[ride_id]
            else:
                # unchecked: remember the current count, then zero it out
                ride_last_count[ride_id] = ride_counts[ride_id]
                ride_counts[ride_id] = RIDE_COUNT_MIN
                ride_locked[ride_id] = False  # can't be locked while unchecked
                # hide this ride's wait-time speech bubble too, if it's showing
                if popup is not None and popup[0] == ride_id:
                    popup = None
            return True
        if up_rect.collidepoint(mx, my):
            old_count = ride_counts[ride_id]
            ride_counts[ride_id] += 1
            if not ride_visible[ride_id]:
                # incrementing an unchecked ride checks it back in
                ride_visible[ride_id] = True
            if old_count == 1 and ride_counts[ride_id] == 2:
                # crossing above 1 -- auto-lock, but remember whether it was
                # already locked so a later drop back to 1 knows what to do
                ride_lock_before_bump[ride_id] = ride_locked[ride_id]
                ride_locked[ride_id] = True
            return True
        if down_rect.collidepoint(mx, my):
            old_count = ride_counts[ride_id]
            new_count = max(RIDE_COUNT_MIN, old_count - 1)
            ride_counts[ride_id] = new_count
            if old_count == 2 and new_count == 1:
                # dropping back down to 1 -- restore whatever the lock state
                # was before the count first went above 1, instead of
                # blindly unlocking (in case it was locked manually)
                ride_locked[ride_id] = ride_lock_before_bump[ride_id]
            if new_count == RIDE_COUNT_MIN and old_count > RIDE_COUNT_MIN:
                # hit zero: remember what it was, then uncheck it
                ride_last_count[ride_id] = old_count
                ride_visible[ride_id] = False
                ride_locked[ride_id] = False  # can't be locked at zero
                # spinner drop-to-zero also unchecks the ride -- hide its
                # wait-time speech bubble too, if it's showing
                if popup is not None and popup[0] == ride_id:
                    popup = None
            return True
        if lock_rect.collidepoint(mx, my):
            # only togglable while the ride is checked and its count > 0
            if ride_visible[ride_id] and ride_counts[ride_id] > RIDE_COUNT_MIN:
                ride_locked[ride_id] = not ride_locked[ride_id]
            return True
    return False


# ── top route bar (shows the generated route, pushes the map down) ──
TOP_BAR_BG_COLOR = (235, 240, 246)
TOP_BAR_PLACEHOLDER_COLOR = (130, 130, 130)
ROUTE_ITEM_BG = (255, 255, 255)
ROUTE_ITEM_BORDER = SIDEBAR_BORDER_COLOR
ROUTE_ARROW_COLOR = (90, 90, 90)

ROUTE_ITEM_H = 32
ROUTE_ITEM_PAD_X = 10
ROUTE_ITEM_MAX_LABEL_W = 130
ROUTE_ARROW_GAP = 22   # horizontal space reserved for the arrow between items
ROUTE_ITEM_GAP = 10    # extra breathing room on either side of the arrow
ROUTE_X_BTN_SIZE = 14
ROUTE_X_GAP = 6        # gap between the item box and its delete-X

topbar_font = pygame.font.SysFont("Arial", 13, bold=True)
topbar_placeholder_font = pygame.font.SysFont("Arial", 13)
topbar_arrow_font = pygame.font.SysFont("Arial", 16, bold=True)
topbar_btn_font = pygame.font.SysFont("Arial", 14, bold=True)

top_bar_rect = pygame.Rect(SIDEBAR_WIDTH, 0, MAP_WIDTH, TOP_BAR_HEIGHT)

TOPBAR_BTN_W = 150
TOPBAR_BTN_H = 42
topbar_route_button_rect = pygame.Rect(
    SCREEN_WIDTH - TOPBAR_BTN_W - 16,
    (TOP_BAR_HEIGHT - TOPBAR_BTN_H) // 2,
    TOPBAR_BTN_W,
    TOPBAR_BTN_H,
)

# rebuilt every draw call: list of {"ride_id": str, "x_rect": pygame.Rect}
# for hit-testing each route item's delete-X button.
topbar_item_rects = []


def draw_top_bar(surface, generate_hover):
    """Draws the route bar across the top of the map area: the generated
    route (ride -> ride -> ride, each with a red X below it to remove),
    and a 'Generate Route' button on the right."""
    global topbar_item_rects
    topbar_item_rects = []

    pygame.draw.rect(surface, TOP_BAR_BG_COLOR, top_bar_rect)
    pygame.draw.line(surface, SIDEBAR_BORDER_COLOR,
                      (SIDEBAR_WIDTH, TOP_BAR_HEIGHT), (SCREEN_WIDTH, TOP_BAR_HEIGHT), 2)

    # ── "Generate Route" button (right side of the bar) ──
    btn_color = ROUTE_BUTTON_HOVER_COLOR if generate_hover else ROUTE_BUTTON_COLOR
    pygame.draw.rect(surface, btn_color, topbar_route_button_rect, border_radius=8)
    btn_label = topbar_btn_font.render("Generate Route", True, ROUTE_BUTTON_TEXT_COLOR)
    surface.blit(btn_label, btn_label.get_rect(center=topbar_route_button_rect.center))

    items_left = top_bar_rect.left + 16
    items_right = topbar_route_button_rect.left - 16

    if not current_route:
        placeholder = topbar_placeholder_font.render(
            "No route generated yet -- check some rides and hit Generate Route",
            True, TOP_BAR_PLACEHOLDER_COLOR,
        )
        surface.blit(placeholder, (items_left, top_bar_rect.centery - placeholder.get_height() // 2))
        return

    # pre-render each item's label
    labels = []
    for ride_id in current_route:
        name = ride_names.get(ride_id, ride_id).replace("\n", " ")
        short = _truncate_label(name, topbar_font, ROUTE_ITEM_MAX_LABEL_W)
        labels.append((ride_id, topbar_font.render(short, True, LABEL_COLOR)))

    item_top = top_bar_rect.centery - ROUTE_ITEM_H // 2 - 6
    x = items_left

    for i, (ride_id, label_surface) in enumerate(labels):
        box_w = label_surface.get_width() + ROUTE_ITEM_PAD_X * 2
        box_rect = pygame.Rect(x, item_top, box_w, ROUTE_ITEM_H)

        if box_rect.right > items_right:
            break  # ran out of horizontal room -- stop drawing further stops

        pygame.draw.rect(surface, ROUTE_ITEM_BG, box_rect, border_radius=6)
        pygame.draw.rect(surface, ROUTE_ITEM_BORDER, box_rect, width=1, border_radius=6)
        surface.blit(
            label_surface,
            (box_rect.left + ROUTE_ITEM_PAD_X, box_rect.centery - label_surface.get_height() // 2),
        )

        # red-X delete button, under this ride
        x_rect = pygame.Rect(
            box_rect.centerx - ROUTE_X_BTN_SIZE // 2,
            box_rect.bottom + ROUTE_X_GAP,
            ROUTE_X_BTN_SIZE,
            ROUTE_X_BTN_SIZE,
        )
        _draw_delete_x(surface, x_rect)
        topbar_item_rects.append({"ride_id": ride_id, "x_rect": x_rect})

        x = box_rect.right

        # arrow separating this item from the next
        if i != len(labels) - 1:
            arrow_x = x + (ROUTE_ARROW_GAP - topbar_arrow_font.size("->")[0]) // 2 + ROUTE_ITEM_GAP // 2
            arrow_surface = topbar_arrow_font.render("->", True, ROUTE_ARROW_COLOR)
            surface.blit(arrow_surface, (arrow_x, box_rect.centery - arrow_surface.get_height() // 2))
            x += ROUTE_ARROW_GAP + ROUTE_ITEM_GAP


def handle_top_bar_click(mx, my):
    """Returns True if the click was consumed by the top bar."""
    global current_route, popup

    if topbar_route_button_rect.collidepoint(mx, my):
        trigger_route_computation()
        return True

    for item in topbar_item_rects:
        if item["x_rect"].collidepoint(mx, my):
            ride_id = item["ride_id"]

            # remove this stop from the displayed route
            current_route = [r for r in current_route if r != ride_id]

            # ...and uncheck the ride itself, same as the sidebar checkbox
            if ride_visible[ride_id]:
                ride_last_count[ride_id] = ride_counts[ride_id]
            ride_counts[ride_id] = RIDE_COUNT_MIN
            ride_visible[ride_id] = False
            ride_locked[ride_id] = False
            if popup is not None and popup[0] == ride_id:
                popup = None
            return True

    return top_bar_rect.collidepoint(mx, my)  # swallow any other click inside the bar


# ── main loop ──────────────────────────────────────────────────────
running = True

while running:

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()

            # sidebar clicks (checkbox toggles / spinner / route button / time
            # inputs / generate-break) take priority
            if mx < SIDEBAR_WIDTH:
                handle_sidebar_click(mx, my)
                continue

            # top route bar (above the map) is checked next
            if my < TOP_BAR_HEIGHT:
                active_time_input = None
                popup = None
                handle_top_bar_click(mx, my)
                continue

            active_time_input = None  # clicking the map defocuses any time input
            popup = None

            for button in buttons:
                x, y, clicked, ride_id, rect = button

                if not ride_visible[ride_id]:
                    continue  # hidden rides aren't clickable

                if rect.collidepoint(mx, my):
                    for b in buttons:
                        b[2] = False
                    button[2] = True

                    display_name = ride_names.get(ride_id, ride_id)
                    wait = Data.ride_waits.get(ride_id, None)
                    is_open = Data.ride_open.get(ride_id, None)
                    # is_open is the source of truth for "closed" now -- a
                    # 0-min wait is a legitimate walk-on, not a closure.
                    wait_str = "Loading..." if wait is None else "Ride is currently closed" if is_open is False else f"Wait: {wait} min"

                    # Split name lines + wait line
                    name_lines = display_name.split("\n")
                    all_lines  = name_lines + [wait_str]

                    # anchor = top-centre of the ride icon
                    anchor_x = rect.centerx
                    anchor_y = rect.top
                    popup = (ride_id, anchor_x, anchor_y, all_lines)
                    break

        if event.type == pygame.KEYDOWN and active_time_input is not None and not time_error_active:
            if event.key == pygame.K_BACKSPACE:
                if active_time_input == "time1":
                    time1_text = time1_text[:-1]
                else:
                    time2_text = time2_text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                # Enter/Tab hops from the first box to the second, then defocuses
                active_time_input = "time2" if active_time_input == "time1" else None
            elif event.unicode and event.unicode.isprintable():
                if active_time_input == "time1" and len(time1_text) < 8:
                    time1_text += event.unicode
                elif active_time_input == "time2" and len(time2_text) < 8:
                    time2_text += event.unicode

    if time_error_active and pygame.time.get_ticks() >= time_error_end_ms:
        time_error_active = False

    # Safety net: if the ride behind the current popup somehow ended up
    # unchecked through a path other than the two handled above, don't
    # let a stale bubble render for a ride that's no longer selected.
    if popup is not None and not ride_visible[popup[0]]:
        popup = None

    # ── draw ───────────────────────────────────────────────────────
    screen.fill((255, 255, 255))
    screen.blit(mapImage, (SIDEBAR_WIDTH, TOP_BAR_HEIGHT))

    for button in buttons:
        x, y, clicked, ride_id, rect = button
        if not ride_visible[ride_id]:
            continue
        if ride_id in ride_images:
            screen.blit(ride_images[ride_id], rect)
        else:
            color = (0, 200, 0) if clicked else (200, 0, 0)
            pygame.draw.circle(screen, color, (x, y), 10)

    mx, my = pygame.mouse.get_pos()
    draw_top_bar(screen, topbar_route_button_rect.collidepoint(mx, my))

    if popup is not None:
        _popup_ride_id, anchor_x, anchor_y, lines = popup
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

    draw_sidebar(screen, route_button_rect.collidepoint(mx, my))

    pygame.display.update()
    clock.tick(60)

pygame.quit()