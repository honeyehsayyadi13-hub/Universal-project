#frontEnd.py
"""Program that shows a user an optimized map of getting to rides at the amusement park Universal"""
import sys

# ── make the process DPI-aware BEFORE pygame/SDL creates a window ──
# Without this, Windows treats the app as DPI-unaware and has the OS
# compositor upscale (blur) the whole window to match display scaling.
if sys.platform == "win32":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pygame
import threading
import Data
import routeOptimizer

pygame.init()

# ── layout constants ───────────────────────────────────────────────
SIDEBAR_WIDTH = 260
MAP_WIDTH = 1000
MAP_HEIGHT = 800
# Default top-bar height only needs to comfortably fit ONE row of route
# items (icon pill + predicted-wait chip + delete-X below it). The bar
# grows dynamically at runtime (see EXTRA_ROW_TOPBAR_H / current_topbar_h)
# when a 2nd or 3rd row of items is actually needed.
TOP_BAR_HEIGHT = 104

# ── figure out available screen space and scale everything to fit ──
_display_info = pygame.display.Info()
_avail_w = _display_info.current_w
_avail_h = _display_info.current_h

# Leave a little margin for OS taskbars/window chrome
_margin_w = 40
_margin_h = 80

_desired_w = SIDEBAR_WIDTH + MAP_WIDTH
_desired_h = MAP_HEIGHT + TOP_BAR_HEIGHT

_scale = min(
    1.0,
    (_avail_w - _margin_w) / _desired_w,
    (_avail_h - _margin_h) / _desired_h,
)
_scale = max(_scale, 0.6)  # don't shrink small enough to look pixelated

SIDEBAR_WIDTH  = int(SIDEBAR_WIDTH * _scale)
MAP_WIDTH      = int(MAP_WIDTH * _scale)
MAP_HEIGHT     = int(MAP_HEIGHT * _scale)
TOP_BAR_HEIGHT = int(TOP_BAR_HEIGHT * _scale)

SCREEN_WIDTH = SIDEBAR_WIDTH + MAP_WIDTH
SCREEN_HEIGHT = MAP_HEIGHT + TOP_BAR_HEIGHT

screen = pygame.display.set_mode(
    (SCREEN_WIDTH, SCREEN_HEIGHT),
    pygame.RESIZABLE
)
pygame.display.set_caption("front_end")

threading.Thread(target=Data.update_backend, daemon=True).start()

clock = pygame.time.Clock()

# ── map image and scaling ──────────────────────────────────────────
mapImage = pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (MAP_WIDTH, MAP_HEIGHT))


# ── helper functions ───────────────────────────────────────────────
def scale_img(img, target_width=90):
    target_width = max(1, int(target_width * _scale))
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
    line_h = font.get_linesize()
    text_w = max(font.size(l)[0] for l in lines) if lines else 60

    box_w = text_w + padding * 2
    box_h = line_h * len(lines) + padding * 2

    bx = px - box_w // 2
    by = py - box_h - tail_h

    surf_w = box_w + border_width * 2
    surf_h = box_h + tail_h + border_width * 2
    bubble = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

    ox, oy = border_width, border_width

    body_rect = pygame.Rect(ox, oy, box_w, box_h)
    pygame.draw.rect(bubble, bg_color, body_rect, border_radius=radius)
    pygame.draw.rect(bubble, border_color, body_rect,
                     width=border_width, border_radius=radius)

    tail_tip_x = ox + box_w // 2
    tail_base_y = oy + box_h
    tail_tip_y  = tail_base_y + tail_h

    tail_left  = tail_tip_x - tail_w // 2
    tail_right = tail_tip_x + tail_w // 2

    pygame.draw.polygon(bubble, bg_color, [
        (tail_left,  tail_base_y + border_width),
        (tail_right, tail_base_y + border_width),
        (tail_tip_x, tail_tip_y),
    ])
    pygame.draw.line(bubble, border_color,
                     (tail_left,  tail_base_y), (tail_tip_x, tail_tip_y), border_width)
    pygame.draw.line(bubble, border_color,
                     (tail_right, tail_base_y), (tail_tip_x, tail_tip_y), border_width)

    for i, line in enumerate(lines):
        label = font.render(line, True, text_color)
        lx = ox + padding + (text_w - font.size(line)[0]) // 2
        ly = oy + padding + i * line_h
        bubble.blit(label, (lx, ly))

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

# ── ride visibility toggles ────────────────────────────────────────
ride_visible = {ride_id: True for ride_id in ride_names}

# ── ride quantity counters ─────────────────────────────────────────
ride_counts = {ride_id: 1 for ride_id in ride_names}
RIDE_COUNT_MIN = 0

ride_last_count = {ride_id: 1 for ride_id in ride_names}

# ── ride lock toggles ──────────────────────────────────────────────
ride_locked = {ride_id: False for ride_id in ride_names}
ride_lock_before_bump = {ride_id: False for ride_id in ride_names}

# ── current route + scroll state ───────────────────────────────────
current_route = []
# Parallel list, index-aligned with current_route: the PREDICTED wait time
# (in minutes) for each ride at the point it's reached in the optimized
# route -- not the live/current wait shown by the map-icon popup. An
# entry is None when no prediction is available for that stop.
current_route_predicted = []
topbar_scroll_x     = 0   # pixels scrolled rightward in the route bar
topbar_max_scroll_x = 0   # clamping ceiling; updated every frame by draw_top_bar

# ── route computation status + click-flash feedback ────────────────
route_generating = False
ROUTE_CLICK_FLASH_MS = 220
route_button_click_ms = -10_000
topbar_route_button_click_ms = -10_000
ROUTE_BUTTON_CLICK_COLOR = (90, 190, 130)  # brief green flash on click

# ── buttons ────────────────────────────────────────────────────────
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
    x = int(x * _scale)
    y = int(y * _scale)
    sx = x + SIDEBAR_WIDTH
    sy = y + TOP_BAR_HEIGHT
    if ride_id in ride_images:
        rect = ride_images[ride_id].get_rect(center=(sx, sy))
    else:
        rect = pygame.Rect(sx - 10, sy - 10, 20, 20)
    buttons.append([sx, sy, clicked, ride_id, rect])

popup = None

popup_font       = pygame.font.SysFont("Arial", max(9, int(13 * _scale)), bold=False)
popup_font_bold  = pygame.font.SysFont("Arial", max(9, int(13 * _scale)), bold=True)

# ── sidebar checklist setup ────────────────────────────────────────
SIDEBAR_BG_COLOR       = (245, 245, 245)
SIDEBAR_BORDER_COLOR   = (180, 180, 180)
CHECKBOX_SIZE          = max(10, int(18 * _scale))
CHECKBOX_MARGIN_LEFT   = max(8, int(14 * _scale))
CHECKBOX_CHECKED_COLOR = (40, 160, 70)
CHECKBOX_BORDER_COLOR  = (60, 60, 60)
LABEL_COLOR            = (20, 20, 20)

sidebar_font = pygame.font.SysFont("Arial", max(9, int(14 * _scale)))
sidebar_title_font = pygame.font.SysFont("Arial", max(11, int(18 * _scale)), bold=True)

TITLE_H = max(24, int(40 * _scale))

# ── quantity spinner layout ────────────────────────────────────────
SPIN_RIGHT_MARGIN = max(6, int(10 * _scale))
SPIN_ARROW_SIZE   = max(7, int(11 * _scale))
SPIN_ARROW_GAP    = max(2, int(3 * _scale))
SPIN_NUM_W        = max(14, int(20 * _scale))
SPIN_AREA_W       = SPIN_ARROW_SIZE * 2 + SPIN_ARROW_GAP * 2 + SPIN_NUM_W
SPIN_ARROW_BG          = (255, 255, 255)
SPIN_ARROW_BORDER      = (60, 60, 60)
SPIN_ARROW_TRIANGLE    = (60, 60, 60)
SPIN_ARROW_DISABLED    = (200, 200, 200)
spin_num_font = pygame.font.SysFont("Arial", max(9, int(13 * _scale)), bold=True)

# ── lock icon ─────────────────────────────────────────────────────
LOCK_SIZE           = max(9, int(14 * _scale))
LOCK_GAP            = max(4, int(6 * _scale))
LOCK_COLOR          = (70, 70, 70)
LOCK_DISABLED_ALPHA = 110

# ── "Get Optimal Route" button ─────────────────────────────────────
ROUTE_BUTTON_H = max(30, int(46 * _scale))
ROUTE_BUTTON_MARGIN = max(8, int(12 * _scale))
ROUTE_BUTTON_COLOR = (30, 110, 200)
ROUTE_BUTTON_HOVER_COLOR = (20, 90, 170)
ROUTE_BUTTON_TEXT_COLOR = (255, 255, 255)
route_button_font = pygame.font.SysFont("Arial", max(10, int(15 * _scale)), bold=True)

route_button_rect = pygame.Rect(
    CHECKBOX_MARGIN_LEFT,
    SCREEN_HEIGHT - ROUTE_BUTTON_H - ROUTE_BUTTON_MARGIN,
    SIDEBAR_WIDTH - CHECKBOX_MARGIN_LEFT * 2,
    ROUTE_BUTTON_H,
)


def _truncate_label(text, font, max_w):
    if font.size(text)[0] <= max_w:
        return text
    ellipsis = "..."
    truncated = text
    while truncated and font.size(truncated + ellipsis)[0] > max_w:
        truncated = truncated[:-1]
    return truncated + ellipsis if truncated else ellipsis


# ── starting-location dropdown ─────────────────────────────────────
DROPDOWN_H           = max(16, int(24 * _scale))
DROPDOWN_ITEM_H      = max(15, int(22 * _scale))
DROPDOWN_BG          = (255, 255, 255)
DROPDOWN_BORDER      = (60, 60, 60)
DROPDOWN_HOVER_COLOR = (225, 235, 250)
DROPDOWN_SELECTED_BG = (235, 245, 255)
DROPDOWN_TEXT_COLOR  = (20, 20, 20)
dropdown_font = pygame.font.SysFont("Arial", max(9, int(13 * _scale)))

dropdown_open = False
selected_start = "entrance"

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

dropdown_items = []
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


# ── break entries ──────────────────────────────────────────────────
breaks = []
_break_id_counter = 0

BREAK_INPUT_H   = max(16, int(24 * _scale))
BREAK_ROW_GAP   = max(4, int(6 * _scale))
BREAK_BTN_H     = max(18, int(28 * _scale))
BREAK_SECTION_TOP = TITLE_H + 8
BREAK_SECTION_H   = BREAK_INPUT_H + BREAK_ROW_GAP + BREAK_BTN_H + 10

BREAK_INPUT_BG                = (255, 255, 255)
BREAK_INPUT_BORDER            = (150, 150, 150)
BREAK_INPUT_BORDER_ACTIVE     = (30, 110, 200)
BREAK_INPUT_TEXT_COLOR        = (20, 20, 20)
BREAK_INPUT_PLACEHOLDER_COLOR = (160, 160, 160)
BREAK_BTN_COLOR       = (200, 60, 60)
BREAK_BTN_HOVER_COLOR = (170, 40, 40)
BREAK_BTN_TEXT_COLOR  = (255, 255, 255)
DELETE_X_COLOR        = (190, 40, 40)

break_input_font = pygame.font.SysFont("Arial", max(9, int(13 * _scale)))
break_btn_font   = pygame.font.SysFont("Arial", max(10, int(14 * _scale)), bold=True)

time1_text = ""
time2_text = ""
active_time_input = None

TIME_ERROR_DURATION_MS = 2000
time_error_active = False
time_error_end_ms = 0

import re as _re

_TIME_INPUT_RE = _re.compile(r'(\d{1,2})(?::(\d{2}))?')


def _parse_time_input(text):
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

LIST_TOP = BREAK_SECTION_TOP + BREAK_SECTION_H

list_area_h = 0
row_h = 0
sidebar_rows = []


def rebuild_sidebar_rows():
    global list_area_h, row_h, sidebar_rows

    total_rows = len(breaks) + len(ride_names)
    list_area_h = route_button_rect.top - LIST_TOP
    row_h = list_area_h // total_rows if total_rows else list_area_h

    sidebar_rows = []
    row_index = 0

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

    for ride_id, name in ride_names.items():
        row_top = LIST_TOP + row_index * row_h
        cb_rect = pygame.Rect(
            CHECKBOX_MARGIN_LEFT,
            row_top + (row_h - CHECKBOX_SIZE) // 2,
            CHECKBOX_SIZE,
            CHECKBOX_SIZE,
        )

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
    color = LOCK_COLOR
    icon = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

    body_h = int(rect.height * 0.55)
    body_rect = pygame.Rect(0, rect.height - body_h, rect.width, body_h)
    pygame.draw.rect(icon, color, body_rect, border_radius=2)
    keyhole_center = body_rect.center
    pygame.draw.circle(icon, (255, 255, 255), keyhole_center, max(1, body_rect.height // 6))

    shackle_w = max(4, int(rect.width * 0.6))
    shackle_h = max(4, int(rect.height * 0.55))
    shackle_thickness = 2

    if locked:
        shackle_rect = pygame.Rect((rect.width - shackle_w) // 2, 0, shackle_w, shackle_h)
        pygame.draw.arc(icon, color, shackle_rect, 0, 3.14159, shackle_thickness)
        pygame.draw.line(icon, color, (shackle_rect.left, shackle_rect.centery),
                          (shackle_rect.left, body_rect.top + 1), shackle_thickness)
        pygame.draw.line(icon, color, (shackle_rect.right, shackle_rect.centery),
                          (shackle_rect.right, body_rect.top + 1), shackle_thickness)
    else:
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
    pygame.draw.rect(surface, SIDEBAR_BG_COLOR, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(surface, SIDEBAR_BORDER_COLOR, (SIDEBAR_WIDTH, 0), (SIDEBAR_WIDTH, SCREEN_HEIGHT), 2)

    _draw_dropdown_button(surface)

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

        pygame.draw.rect(surface, (255, 255, 255), cb_rect, border_radius=3)
        pygame.draw.rect(surface, CHECKBOX_BORDER_COLOR, cb_rect, width=2, border_radius=3)
        if ride_visible[ride_id]:
            inner = cb_rect.inflate(-6, -6)
            pygame.draw.rect(surface, CHECKBOX_CHECKED_COLOR, inner, border_radius=2)

        label_x = cb_rect.right + 10
        label_y = row_top + (row_h - label_surface.get_height()) // 2
        surface.blit(label_surface, (label_x, label_y))

        count = ride_counts[ride_id]
        _draw_spin_arrow(surface, down_rect, pointing_up=False, enabled=count > RIDE_COUNT_MIN)
        _draw_spin_arrow(surface, up_rect, pointing_up=True, enabled=True)

        num_surface = spin_num_font.render(str(count), True, LABEL_COLOR)
        num_y = row_top + (row_h - num_surface.get_height()) // 2
        num_x = num_left + (num_right - num_left - num_surface.get_width()) // 2
        surface.blit(num_surface, (num_x, num_y))

        lockable = ride_visible[ride_id] and count > RIDE_COUNT_MIN
        if not lockable:
            ride_locked[ride_id] = False
        _draw_lock_icon(surface, lock_rect, ride_locked[ride_id], transparent=not ride_visible[ride_id])

    if pygame.time.get_ticks() - route_button_click_ms < ROUTE_CLICK_FLASH_MS:
        color = ROUTE_BUTTON_CLICK_COLOR
    else:
        color = ROUTE_BUTTON_HOVER_COLOR if route_button_hover else ROUTE_BUTTON_COLOR
    pygame.draw.rect(surface, color, route_button_rect, border_radius=8)
    label = route_button_font.render("Get Optimal Route", True, ROUTE_BUTTON_TEXT_COLOR)
    label_pos = label.get_rect(center=route_button_rect.center)
    surface.blit(label, label_pos)

    _draw_dropdown_list(surface)


def trigger_route_computation():
    global route_generating
    route_generating = True

    selected_counts = {
        ride_id: ride_counts[ride_id]
        for ride_id in ride_names
        if ride_visible[ride_id] and ride_counts[ride_id] > RIDE_COUNT_MIN
    }
    selected_locked = {
        ride_id: True
        for ride_id in ride_names
        if ride_locked[ride_id]
    }

    live_waits_snapshot = dict(Data.ride_waits)
    live_open_snapshot  = dict(Data.ride_open)

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


def _extract_ride_id_and_predicted_wait(entry):
    """
    Normalizes one entry of routeOptimizer's returned route into
    (ride_id, predicted_wait_minutes). Accepts several shapes so this
    keeps working whether routeOptimizer returns:
      - a plain ride_id string (predicted wait unknown -> None)
      - a (ride_id, predicted_wait) tuple/list
      - a dict like {"ride_id": ..., "predicted_wait": ...}
        (also tries "id"/"ride", and "predicted_wait_minutes"/"wait")
    """
    if isinstance(entry, dict):
        ride_id = entry.get("ride_id", entry.get("id", entry.get("ride")))
        predicted_wait = entry.get(
            "predicted_wait",
            entry.get("predicted_wait_minutes", entry.get("wait")),
        )
        return ride_id, predicted_wait
    if isinstance(entry, (tuple, list)):
        ride_id = entry[0] if len(entry) > 0 else None
        predicted_wait = entry[1] if len(entry) > 1 else None
        return ride_id, predicted_wait
    return entry, None


def _run_route_computation(counts, locked, closed_keys, break_windows, start_key="entrance", live_waits=None):
    global current_route, current_route_predicted, topbar_scroll_x, route_generating
    result = routeOptimizer.compute_and_print_route(
        counts, locked, closed_keys, break_windows,
        start_key=start_key, live_waits=live_waits,
    )
    if result is not None:
        route_list = []
        predicted_list = []
        for entry in result:
            ride_id, predicted_wait = _extract_ride_id_and_predicted_wait(entry)
            route_list.append(ride_id)
            predicted_list.append(predicted_wait)
        current_route = route_list
        current_route_predicted = predicted_list
        topbar_scroll_x = 0  # reset scroll when a new route arrives
    route_generating = False


def handle_sidebar_click(mx, my):
    global dropdown_open, selected_start, active_time_input, time1_text, time2_text, _break_id_counter, popup, route_button_click_ms

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
        dropdown_open = False
        return True

    if time_error_active:
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
            valid = m2 > m1

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

    active_time_input = None

    if route_button_rect.collidepoint(mx, my):
        route_button_click_ms = pygame.time.get_ticks()
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
                ride_counts[ride_id] = ride_last_count[ride_id]
            else:
                ride_last_count[ride_id] = ride_counts[ride_id]
                ride_counts[ride_id] = RIDE_COUNT_MIN
                ride_locked[ride_id] = False
                if popup is not None and popup[0] == ride_id:
                    popup = None
            return True
        if up_rect.collidepoint(mx, my):
            old_count = ride_counts[ride_id]
            ride_counts[ride_id] += 1
            if not ride_visible[ride_id]:
                ride_visible[ride_id] = True
            if old_count == 1 and ride_counts[ride_id] == 2:
                ride_lock_before_bump[ride_id] = ride_locked[ride_id]
                ride_locked[ride_id] = True
            return True
        if down_rect.collidepoint(mx, my):
            old_count = ride_counts[ride_id]
            new_count = max(RIDE_COUNT_MIN, old_count - 1)
            ride_counts[ride_id] = new_count
            if old_count == 2 and new_count == 1:
                ride_locked[ride_id] = ride_lock_before_bump[ride_id]
            if new_count == RIDE_COUNT_MIN and old_count > RIDE_COUNT_MIN:
                ride_last_count[ride_id] = old_count
                ride_visible[ride_id] = False
                ride_locked[ride_id] = False
                if popup is not None and popup[0] == ride_id:
                    popup = None
            return True
        if lock_rect.collidepoint(mx, my):
            if ride_visible[ride_id] and ride_counts[ride_id] > RIDE_COUNT_MIN:
                ride_locked[ride_id] = not ride_locked[ride_id]
            return True
    return False


# ── top route bar ──────────────────────────────────────────────────
TOP_BAR_BG_COLOR           = (235, 240, 246)
TOP_BAR_PLACEHOLDER_COLOR  = (130, 130, 130)
ROUTE_ITEM_BG              = (255, 255, 255)
ROUTE_ITEM_BORDER          = SIDEBAR_BORDER_COLOR
ROUTE_ARROW_COLOR          = (90, 90, 90)

ROUTE_ITEM_H         = max(36, int(52 * _scale))
ROUTE_ITEM_PAD_X     = max(4, int(6 * _scale))
ROUTE_ITEM_MAX_LABEL_W = max(80, int(130 * _scale))
ROUTE_ARROW_GAP      = max(14, int(22 * _scale))
ROUTE_ITEM_GAP       = max(6, int(10 * _scale))
ROUTE_X_BTN_SIZE     = max(9, int(14 * _scale))
ROUTE_X_GAP          = max(4, int(6 * _scale))

# ── ride icons in the route bar: square pills sized to the row height ─
ROUTE_ICON_PAD    = max(1, int(2 * _scale))
ROUTE_ICON_MAX    = ROUTE_ITEM_H - ROUTE_ICON_PAD * 2  # icon drawn inside the pill

# original (unscaled) image paths, reused so topbar icons aren't scaled
# down twice (once for map buttons, again for the pill) which looked blurry
_ride_image_paths = {
    "hulk":           "logos/hulk_logo.png",
    "stormForce":     "logos/stormForce_logo.png",
    "doctorDoom":     "logos/Doctor-dooms-fearfall-ride-logo-b.png",
    "spiderMan":      "logos/Amazing-adventures-spider-man-ride-logo-b.png",
    "bilgeRat":       "logos/bilge_rat.png",
    "ripsawFalls":    "logos/Dudley-do-rights-ripsaw-falls-water-ride-logo-b.png",
    "skullIsland":    "logos/Skull_Island-_Reign_of_Kong_Logo.png",
    "velociCoaster":  "logos/velocicoaster.png",
    "riverAdventure": "logos/jurrasicPark.png",
    "hogwartsTrain":  "logos/express.png",
    "hippogriff":     "logos/hippogriph.png",
    "hagrid":         "logos/Hagrid27s_Magical_Creatures_Motorbike_Adventure.png",
    "harryPotter":    "logos/hogwarts.png",
    "catInTheHat":    "logos/cat.png",
    "oneFishtwoFish": "logos/blue.png",
    "drSeussAirRide": "logos/seuss.png",
    "caroSeussel":    "logos/caro.png",
}

_topbar_icon_cache = {}


def _get_topbar_icon(ride_id):
    icon = _topbar_icon_cache.get(ride_id)
    if icon is not None:
        return icon

    path = _ride_image_paths.get(ride_id)
    if path is None:
        return None

    src = remove_white_background(pygame.image.load(path).convert_alpha())
    w, h = src.get_size()
    if w <= 0 or h <= 0:
        return None
    # "cover" scaling: scale up until the image fills the square in both
    # dimensions, then crop the overflow, so there's no leftover whitespace
    # on the shorter axis (as a plain aspect-fit would leave).
    scale_factor = max(ROUTE_ICON_MAX / w, ROUTE_ICON_MAX / h)
    new_w = max(1, round(w * scale_factor))
    new_h = max(1, round(h * scale_factor))
    scaled = pygame.transform.smoothscale(src, (new_w, new_h))

    icon = pygame.Surface((ROUTE_ICON_MAX, ROUTE_ICON_MAX), pygame.SRCALPHA)
    crop_x = (new_w - ROUTE_ICON_MAX) // 2
    crop_y = (new_h - ROUTE_ICON_MAX) // 2
    icon.blit(scaled, (0, 0), area=pygame.Rect(crop_x, crop_y, ROUTE_ICON_MAX, ROUTE_ICON_MAX))

    _topbar_icon_cache[ride_id] = icon
    return icon


# ── predicted-wait chip (sits below each ride icon in the route bar) ──
# Shows the PREDICTED wait for that ride at the point it's reached in the
# optimized route -- distinct from the live/current wait shown when a
# ride icon on the map is clicked.
PRED_CHIP_H       = max(13, int(16 * _scale))
PRED_CHIP_GAP     = max(2, int(3 * _scale))     # gap: icon->chip, and chip->delete-X
PRED_CHIP_RADIUS  = max(3, int(5 * _scale))
topbar_pred_font  = pygame.font.SysFont("Arial", max(8, int(11 * _scale)), bold=True)

PRED_CHIP_UNKNOWN_BG   = (225, 227, 231)
PRED_CHIP_UNKNOWN_TEXT = (110, 110, 110)
PRED_CHIP_LOW_BG       = (60, 170, 90)     # short wait -- green
PRED_CHIP_MED_BG       = (230, 160, 40)    # moderate wait -- amber
PRED_CHIP_HIGH_BG      = (210, 70, 70)     # long wait -- red
PRED_CHIP_TEXT         = (255, 255, 255)


def _predicted_wait_chip_style(predicted_wait):
    """Returns (bg_color, text_color, label) for a predicted-wait chip."""
    if predicted_wait is None:
        return PRED_CHIP_UNKNOWN_BG, PRED_CHIP_UNKNOWN_TEXT, "--"
    try:
        minutes = int(round(float(predicted_wait)))
    except (TypeError, ValueError):
        return PRED_CHIP_UNKNOWN_BG, PRED_CHIP_UNKNOWN_TEXT, "--"
    if minutes <= 10:
        bg = PRED_CHIP_LOW_BG
    elif minutes <= 25:
        bg = PRED_CHIP_MED_BG
    else:
        bg = PRED_CHIP_HIGH_BG
    return bg, PRED_CHIP_TEXT, f"~{minutes}m"


def _draw_predicted_wait_chip(surface, rect, predicted_wait):
    bg_color, text_color, label_text = _predicted_wait_chip_style(predicted_wait)
    pygame.draw.rect(surface, bg_color, rect, border_radius=PRED_CHIP_RADIUS)
    label_surface = topbar_pred_font.render(label_text, True, text_color)
    surface.blit(label_surface, label_surface.get_rect(center=rect.center))


# ── multi-row + scrollbar constants ───────────────────────────────
TOPBAR_ROWS        = 3
TOPBAR_ROW_GAP     = max(4, int(6 * _scale))    # vertical gap between rows
TOPBAR_ROW_SLOT_H  = ROUTE_ITEM_H + PRED_CHIP_GAP + PRED_CHIP_H + ROUTE_X_GAP + ROUTE_X_BTN_SIZE
TOPBAR_SCROLLBAR_H     = max(3, int(5 * _scale))
TOPBAR_SCROLLBAR_BG    = (210, 215, 225)
TOPBAR_SCROLLBAR_COLOR = (130, 140, 170)
# fixed width of each item pill (square, sized to row height so it holds an icon)
TOPBAR_ITEM_FIXED_W = ROUTE_ITEM_H

# Extra vertical room the bar needs to grow into when a 2nd or 3rd row of
# route items is required (each additional row needs one more row-slot
# plus the gap between rows). TOP_BAR_HEIGHT itself is sized for one row.
EXTRA_ROW_TOPBAR_H = TOPBAR_ROW_SLOT_H + TOPBAR_ROW_GAP

topbar_font             = pygame.font.SysFont("Arial", max(9, int(13 * _scale)), bold=True)
topbar_placeholder_font = pygame.font.SysFont("Arial", max(9, int(13 * _scale)))
topbar_generating_font  = pygame.font.SysFont("Arial", max(14, int(20 * _scale)), bold=True)
topbar_arrow_font       = pygame.font.SysFont("Arial", max(10, int(16 * _scale)), bold=True)
topbar_btn_font         = pygame.font.SysFont("Arial", max(10, int(15 * _scale)), bold=True)

top_bar_rect = pygame.Rect(SIDEBAR_WIDTH, 0, MAP_WIDTH, TOP_BAR_HEIGHT)  # placeholder, recomputed per-frame

# "Generate Route" button matches "Get Optimal Route" button's size exactly.
TOPBAR_BTN_W = route_button_rect.width
TOPBAR_BTN_H = ROUTE_BUTTON_H
topbar_route_button_rect = pygame.Rect(
    SCREEN_WIDTH - TOPBAR_BTN_W - 16,
    0,  # y recomputed each frame once the current bar height is known
    TOPBAR_BTN_W,
    TOPBAR_BTN_H,
)

# rebuilt every draw call
topbar_item_rects = []

# How many rows the route bar actually needed last time it was drawn.
# Read by current_topbar_h() so the bar can grow past its default
# (1-row) height when 2 or 3 rows are required, and shrink back down
# once they're no longer needed.
topbar_rows_needed = 1


def draw_top_bar(surface, generate_hover, cur_sb_w, bar_h):
    """
    Draws the route bar across the top of the map area.

    The bar's left edge always starts at the sidebar's *current* animated
    width (cur_sb_w), so when the sidebar is collapsed the top bar expands
    to reclaim that space (dropping to fewer rows if everything now fits),
    and gives the space back smoothly as the sidebar re-expands.

    `bar_h` is the actual pixel height of the bar for this frame (already
    grown to accommodate multiple rows if needed -- see current_topbar_h).

    Items are wrapped into up to TOPBAR_ROWS rows, filling each row to
    capacity left-to-right before starting the next -- so the bar defaults
    to a single row and only adds more when needed. If even 3 full rows
    aren't enough, all rows are split evenly and the whole block scrolls
    horizontally together via the mouse-wheel; a thin scrollbar appears
    at the bottom of the bar to show position.
    """
    global topbar_item_rects, topbar_max_scroll_x, top_bar_rect, topbar_rows_needed
    topbar_item_rects = []

    top_bar_rect = pygame.Rect(cur_sb_w, 0, SCREEN_WIDTH - cur_sb_w, bar_h)

    pygame.draw.rect(surface, TOP_BAR_BG_COLOR, top_bar_rect)
    pygame.draw.line(surface, SIDEBAR_BORDER_COLOR,
                     (cur_sb_w, bar_h),
                     (SCREEN_WIDTH,  bar_h), 2)

    # ── "Generate Route" button (right side of bar, vertically centred) ─
    topbar_route_button_rect.top = (bar_h - TOPBAR_BTN_H) // 2
    if pygame.time.get_ticks() - topbar_route_button_click_ms < ROUTE_CLICK_FLASH_MS:
        btn_color = ROUTE_BUTTON_CLICK_COLOR
    else:
        btn_color = ROUTE_BUTTON_HOVER_COLOR if generate_hover else ROUTE_BUTTON_COLOR
    pygame.draw.rect(surface, btn_color, topbar_route_button_rect, border_radius=8)
    btn_label = topbar_btn_font.render("Generate Route", True, ROUTE_BUTTON_TEXT_COLOR)
    surface.blit(btn_label, btn_label.get_rect(center=topbar_route_button_rect.center))

    items_left  = cur_sb_w + 16
    items_right = topbar_route_button_rect.left - 16
    viewport_w  = max(1, items_right - items_left)

    if not current_route:
        topbar_rows_needed = 1
        if route_generating:
            placeholder = topbar_generating_font.render("Generating...", True, (0, 0, 0))
        else:
            placeholder = topbar_generating_font.render(
                'No route generate yet -- check or uncheck rides and click "generate route"',
                True, (0, 0, 0),
            )
        surface.blit(placeholder,
                     (items_left, bar_h // 2 - placeholder.get_height() // 2))
        return

    # (ride_id, predicted_wait) pairs, index-aligned with current_route
    combined_route = list(zip(current_route, current_route_predicted))

    n        = len(combined_route)
    col_step = TOPBAR_ITEM_FIXED_W + ROUTE_ARROW_GAP + ROUTE_ITEM_GAP  # px per column

    # How many items fit in one row within the visible viewport?
    fit_per_row = max(1, (viewport_w + ROUTE_ARROW_GAP + ROUTE_ITEM_GAP) // col_step)

    if n <= fit_per_row * TOPBAR_ROWS:
        # Everything fits without scrolling: fill each row to capacity
        # before starting the next one (last row holds the remainder).
        needed_rows = max(1, -(-n // fit_per_row))  # ceil(n / fit_per_row)
        row_item_lists = []
        idx = 0
        for _ in range(needed_rows):
            row_item_lists.append(combined_route[idx: idx + fit_per_row])
            idx += fit_per_row
        virtual_w = viewport_w
        topbar_max_scroll_x = 0
    else:
        # Too many items even at 3 full rows: split evenly across all
        # rows and let the whole block scroll horizontally together.
        needed_rows = TOPBAR_ROWS
        items_per_row = -(-n // needed_rows)  # ceil(n / needed_rows)
        row_item_lists = []
        idx = 0
        for _ in range(needed_rows):
            row_item_lists.append(combined_route[idx: idx + items_per_row])
            idx += items_per_row
        virtual_w = items_per_row * col_step - (ROUTE_ARROW_GAP + ROUTE_ITEM_GAP)
        topbar_max_scroll_x = max(0, virtual_w - viewport_w)

    topbar_rows_needed = needed_rows

    # Vertically centre the block of rows (reserve scrollbar space at bottom)
    content_h    = bar_h - TOPBAR_SCROLLBAR_H - 4
    total_rows_h = needed_rows * TOPBAR_ROW_SLOT_H + (needed_rows - 1) * TOPBAR_ROW_GAP
    v_offset     = max(4, (content_h - total_rows_h) // 2)

    # Clip so items never overdraw the Generate-Route button or the sidebar
    clip_rect = pygame.Rect(items_left, 0, viewport_w, bar_h)
    old_clip  = surface.get_clip()
    surface.set_clip(clip_rect)

    for row_idx in range(needed_rows):
        row_items = row_item_lists[row_idx]

        item_y = v_offset + row_idx * (TOPBAR_ROW_SLOT_H + TOPBAR_ROW_GAP)

        for col_idx, (ride_id, predicted_wait) in enumerate(row_items):
            item_x   = items_left + col_idx * col_step - topbar_scroll_x
            box_rect = pygame.Rect(item_x, item_y, TOPBAR_ITEM_FIXED_W, ROUTE_ITEM_H)

            # predicted-wait chip sits directly below the icon pill
            chip_rect = pygame.Rect(
                box_rect.left,
                box_rect.bottom + PRED_CHIP_GAP,
                TOPBAR_ITEM_FIXED_W,
                PRED_CHIP_H,
            )

            # draw the pill only when at least partially in the viewport
            if box_rect.right > items_left and box_rect.left < items_right:
                pygame.draw.rect(surface, ROUTE_ITEM_BG,    box_rect, border_radius=6)
                pygame.draw.rect(surface, ROUTE_ITEM_BORDER, box_rect, width=1, border_radius=6)

                icon = _get_topbar_icon(ride_id)
                if icon is not None:
                    icon_rect = icon.get_rect(center=box_rect.center)
                    surface.blit(icon, icon_rect)
                else:
                    name  = ride_names.get(ride_id, ride_id).replace("\n", " ")
                    short = _truncate_label(name, topbar_font, ROUTE_ITEM_MAX_LABEL_W)
                    label_surface = topbar_font.render(short, True, LABEL_COLOR)
                    surface.blit(label_surface, label_surface.get_rect(center=box_rect.center))

                _draw_predicted_wait_chip(surface, chip_rect, predicted_wait)

                # arrow to the next item in the same row
                if col_idx < len(row_items) - 1:
                    arrow_surface = topbar_arrow_font.render("->", True, ROUTE_ARROW_COLOR)
                    ax = box_rect.right + (ROUTE_ARROW_GAP - arrow_surface.get_width()) // 2
                    surface.blit(arrow_surface,
                                 (ax, box_rect.centery - arrow_surface.get_height() // 2))

            # delete-X sits below the chip; register it for hit-testing
            x_rect = pygame.Rect(
                box_rect.centerx - ROUTE_X_BTN_SIZE // 2,
                chip_rect.bottom + ROUTE_X_GAP,
                ROUTE_X_BTN_SIZE,
                ROUTE_X_BTN_SIZE,
            )
            if x_rect.right > items_left and x_rect.left < items_right:
                _draw_delete_x(surface, x_rect)
                topbar_item_rects.append({"ride_id": ride_id, "x_rect": x_rect})

    surface.set_clip(old_clip)

    # ── scrollbar (only shown when content overflows the viewport) ─
    if topbar_max_scroll_x > 0:
        sb_y     = bar_h - TOPBAR_SCROLLBAR_H - 2
        sb_track = pygame.Rect(items_left, sb_y, viewport_w, TOPBAR_SCROLLBAR_H)
        pygame.draw.rect(surface, TOPBAR_SCROLLBAR_BG, sb_track, border_radius=3)

        thumb_w = max(40, int(viewport_w * viewport_w / max(viewport_w, virtual_w)))
        thumb_x = items_left + int(
            (viewport_w - thumb_w) * topbar_scroll_x / max(1, topbar_max_scroll_x)
        )
        pygame.draw.rect(surface, TOPBAR_SCROLLBAR_COLOR,
                         pygame.Rect(thumb_x, sb_y, thumb_w, TOPBAR_SCROLLBAR_H),
                         border_radius=3)


def handle_top_bar_click(mx, my):
    global current_route, current_route_predicted, popup, topbar_route_button_click_ms

    if topbar_route_button_rect.collidepoint(mx, my):
        topbar_route_button_click_ms = pygame.time.get_ticks()
        trigger_route_computation()
        return True

    for item in topbar_item_rects:
        if item["x_rect"].collidepoint(mx, my):
            ride_id = item["ride_id"]
            kept = [(r, p) for r, p in zip(current_route, current_route_predicted) if r != ride_id]
            current_route = [r for r, _p in kept]
            current_route_predicted = [p for _r, p in kept]

            if ride_visible[ride_id]:
                ride_last_count[ride_id] = ride_counts[ride_id]
            ride_counts[ride_id] = RIDE_COUNT_MIN
            ride_visible[ride_id] = False
            ride_locked[ride_id] = False
            if popup is not None and popup[0] == ride_id:
                popup = None
            return True

    return top_bar_rect.collidepoint(mx, my)


# ── collapse/expand toggle state ───────────────────────────────────
COLLAPSE_ANIM_SPEED = 0.12   # fraction of full size per frame (~8 frames to animate, cheap)

sidebar_collapsed = False
sidebar_anim = 1.0          # 1.0 = fully expanded, 0.0 = fully collapsed
sidebar_anim_target = 1.0

topbar_collapsed = False
topbar_anim = 1.0
topbar_anim_target = 1.0

# Larger, more visible toggle arrows (bigger tab + more opaque colors)
TOGGLE_ARROW_W = max(30, int(34 * _scale))
TOGGLE_ARROW_H = max(56, int(64 * _scale))
TOGGLE_ARROW_COLOR = (60, 60, 60, 235)   # dark gray, mostly opaque
TOGGLE_ARROW_BG     = (255, 255, 255, 220)


def _make_toggle_arrow_surface(pointing_left):
    """Pre-render once: tab with a triangle, large and clearly visible."""
    surf = pygame.Surface((TOGGLE_ARROW_W, TOGGLE_ARROW_H), pygame.SRCALPHA)
    pygame.draw.rect(surf, TOGGLE_ARROW_BG, surf.get_rect(), border_radius=8)
    pygame.draw.rect(surf, (120, 120, 120, 235), surf.get_rect(), width=1, border_radius=8)
    cx, cy = TOGGLE_ARROW_W // 2, TOGGLE_ARROW_H // 2
    tri_half_h = int(TOGGLE_ARROW_H * 0.22)
    tri_reach  = int(TOGGLE_ARROW_W * 0.32)
    if pointing_left:
        pts = [(cx + tri_reach, cy - tri_half_h), (cx + tri_reach, cy + tri_half_h), (cx - tri_reach, cy)]
    else:
        pts = [(cx - tri_reach, cy - tri_half_h), (cx - tri_reach, cy + tri_half_h), (cx + tri_reach, cy)]
    pygame.draw.polygon(surf, TOGGLE_ARROW_COLOR, pts)
    return surf


# pre-rendered once at startup — no per-frame cost beyond a blit
sidebar_arrow_left  = _make_toggle_arrow_surface(pointing_left=True)   # points into sidebar (expanded)
sidebar_arrow_right = _make_toggle_arrow_surface(pointing_left=False)  # points away (collapsed)

_topbar_arrow_base_down = _make_toggle_arrow_surface(pointing_left=False)
_topbar_arrow_base_up   = _make_toggle_arrow_surface(pointing_left=True)
topbar_arrow_down = pygame.transform.rotate(_topbar_arrow_base_down, 90)  # points down (expanded)
topbar_arrow_up    = pygame.transform.rotate(_topbar_arrow_base_up, 90)   # points up (collapsed)


def current_sidebar_w():
    return int(SIDEBAR_WIDTH * sidebar_anim)


def current_topbar_h():
    """
    Base height (sized for exactly one row) scaled by the collapse
    animation, PLUS extra room grown in to fit any additional rows that
    were needed the last time the bar was drawn (2nd/3rd row of route
    items). The extra room only applies while the bar is expanded, and
    scales down smoothly along with the collapse animation so collapsing
    still shrinks the bar to nothing.
    """
    extra = EXTRA_ROW_TOPBAR_H * max(0, topbar_rows_needed - 1)
    return int((TOP_BAR_HEIGHT + extra) * topbar_anim)


# ── main loop ──────────────────────────────────────────────────────
running = True

while running:

    cur_sb_w = current_sidebar_w()
    cur_tb_h = current_topbar_h()

    sb_arrow = sidebar_arrow_right if sidebar_collapsed else sidebar_arrow_left
    sb_arrow_rect = sb_arrow.get_rect(midleft=(cur_sb_w, SCREEN_HEIGHT // 2))

    tb_arrow = topbar_arrow_up if topbar_collapsed else topbar_arrow_down
    tb_arrow_rect = tb_arrow.get_rect(midtop=(SCREEN_WIDTH // 2, cur_tb_h))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # ── mouse-wheel: scroll the route bar horizontally ─────────
        if event.type == pygame.MOUSEWHEEL:
            emx, emy = pygame.mouse.get_pos()
            if emx >= cur_sb_w and emy < cur_tb_h:
                # event.x  = horizontal wheel axis (some mice/trackpads)
                # event.y  = vertical wheel axis (standard scroll wheel);
                #            positive = scroll up, so we invert it to mean
                #            "scroll the view left" which is natural.
                delta = event.x * 40 - event.y * 40
                topbar_scroll_x = max(0, min(topbar_max_scroll_x,
                                             topbar_scroll_x + delta))

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()

            if sb_arrow_rect.collidepoint(mx, my):
                sidebar_collapsed = not sidebar_collapsed
                sidebar_anim_target = 0.0 if sidebar_collapsed else 1.0
                continue

            if tb_arrow_rect.collidepoint(mx, my):
                topbar_collapsed = not topbar_collapsed
                topbar_anim_target = 0.0 if topbar_collapsed else 1.0
                continue

            if mx < cur_sb_w:
                handle_sidebar_click(mx, my)
                continue

            if my < cur_tb_h:
                active_time_input = None
                popup = None
                handle_top_bar_click(mx, my)
                continue

            active_time_input = None
            popup = None

            for button in buttons:
                x, y, clicked, ride_id, rect = button

                if not ride_visible[ride_id]:
                    continue

                if rect.collidepoint(mx, my):
                    for b in buttons:
                        b[2] = False
                    button[2] = True

                    display_name = ride_names.get(ride_id, ride_id)
                    wait = Data.ride_waits.get(ride_id, None)
                    is_open = Data.ride_open.get(ride_id, None)
                    wait_str = ("Loading..." if wait is None
                                else "Ride is currently closed" if is_open is False
                                else f"Wait: {wait} min")

                    name_lines = display_name.split("\n")
                    all_lines  = name_lines + [wait_str]

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
                active_time_input = "time2" if active_time_input == "time1" else None
            elif event.unicode and event.unicode.isprintable():
                if active_time_input == "time1" and len(time1_text) < 8:
                    time1_text += event.unicode
                elif active_time_input == "time2" and len(time2_text) < 8:
                    time2_text += event.unicode

    if time_error_active and pygame.time.get_ticks() >= time_error_end_ms:
        time_error_active = False

    if popup is not None and not ride_visible[popup[0]]:
        popup = None

    # ── step collapse/expand animations (cheap: one float compare+add) ─
    if sidebar_anim != sidebar_anim_target:
        if sidebar_anim < sidebar_anim_target:
            sidebar_anim = min(sidebar_anim_target, sidebar_anim + COLLAPSE_ANIM_SPEED)
        else:
            sidebar_anim = max(sidebar_anim_target, sidebar_anim - COLLAPSE_ANIM_SPEED)

    if topbar_anim != topbar_anim_target:
        if topbar_anim < topbar_anim_target:
            topbar_anim = min(topbar_anim_target, topbar_anim + COLLAPSE_ANIM_SPEED)
        else:
            topbar_anim = max(topbar_anim_target, topbar_anim - COLLAPSE_ANIM_SPEED)

    # recompute post-step sizes/rects for drawing this frame
    cur_sb_w = current_sidebar_w()
    cur_tb_h = current_topbar_h()

    sb_arrow = sidebar_arrow_right if sidebar_collapsed else sidebar_arrow_left
    sb_arrow_rect = sb_arrow.get_rect(midleft=(cur_sb_w, SCREEN_HEIGHT // 2))

    tb_arrow = topbar_arrow_up if topbar_collapsed else topbar_arrow_down
    tb_arrow_rect = tb_arrow.get_rect(midtop=(SCREEN_WIDTH // 2, cur_tb_h))

    # ── draw ───────────────────────────────────────────────────────
    screen.fill((255, 255, 255))
    screen.blit(mapImage, (cur_sb_w, cur_tb_h),
                area=pygame.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    for button in buttons:
        x, y, clicked, ride_id, rect = button
        if not ride_visible[ride_id]:
            continue
        offset_rect = rect.move(cur_sb_w - SIDEBAR_WIDTH, cur_tb_h - TOP_BAR_HEIGHT)
        if ride_id in ride_images:
            screen.blit(ride_images[ride_id], offset_rect)
        else:
            color = (0, 200, 0) if clicked else (200, 0, 0)
            pygame.draw.circle(screen, color,
                                (x + cur_sb_w - SIDEBAR_WIDTH, y + cur_tb_h - TOP_BAR_HEIGHT), 10)

    mx, my = pygame.mouse.get_pos()

    if cur_tb_h > 0:
        full_bar_h = TOP_BAR_HEIGHT + EXTRA_ROW_TOPBAR_H * max(0, topbar_rows_needed - 1)
        if cur_tb_h >= full_bar_h:
            draw_top_bar(screen, topbar_route_button_rect.collidepoint(mx, my), cur_sb_w, cur_tb_h)
        else:
            topbar_surface = pygame.Surface((SCREEN_WIDTH, full_bar_h), pygame.SRCALPHA)
            draw_top_bar(topbar_surface, topbar_route_button_rect.collidepoint(mx, my), cur_sb_w, full_bar_h)
            scaled_topbar = pygame.transform.smoothscale(topbar_surface, (SCREEN_WIDTH, cur_tb_h))
            screen.blit(scaled_topbar, (0, 0))

    if popup is not None:
        _popup_ride_id, anchor_x, anchor_y, lines = popup
        draw_speech_bubble(
            screen,
            px=anchor_x,
            py=anchor_y,
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

    if cur_sb_w > 0:
        old_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(0, 0, cur_sb_w, SCREEN_HEIGHT))
        draw_sidebar(screen, route_button_rect.collidepoint(mx, my))
        screen.set_clip(old_clip)

    # ── toggle arrows: larger, dark, mostly opaque, pre-rendered ─
    screen.blit(sb_arrow, sb_arrow_rect)
    screen.blit(tb_arrow, tb_arrow_rect)

    pygame.display.update()
    clock.tick(60)

pygame.quit()