"""
Universal Islands of Adventure - Interactive Map
Click the red dots to see ride info pop-ups!
"""

import pygame
import sys

pygame.init()

# --- Window Setup ---
SCREEN_W, SCREEN_H = 1200, 800
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Universal Islands of Adventure - Interactive Map")
clock = pygame.time.Clock()

# --- Load & Scale Map ---
mapImage = pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (1000, 900))

# --- Colors ---
RED         = (220, 30,  30)
RED_HOVER   = (255, 80,  80)
RED_OUTLINE = (140, 0,   0)
WHITE       = (255, 255, 255)
BLACK       = (10,  10,  10)
POPUP_BG    = (15,  15,  25,  230)   # dark, slightly transparent
POPUP_BORDER= (220, 30,  30)
GOLD        = (255, 200, 50)
GRAY_LIGHT  = (200, 200, 210)

# --- Fonts ---
font_title  = pygame.font.SysFont("Georgia",      18, bold=True)
font_body   = pygame.font.SysFont("Arial",        14)
font_small  = pygame.font.SysFont("Arial",        12, italic=True)
font_close  = pygame.font.SysFont("Arial",        14, bold=True)

# --- Ride Data: (x, y, name, wait_time, thrill_level, description) ---
# Coordinates are approximate pixel positions on the 1000x900 scaled map
RIDES = [
    {
        "pos": (530, 220),
        "name": "Jurassic World VelociCoaster",
        "wait": "45 min",
        "thrill": "⚡⚡⚡⚡⚡",
        "desc": "High-speed launch coaster.\nTop speed: 70 mph. Height req: 51\"",
        "type": "Roller Coaster",
        "icon": "🦕",
    },
    {
        "pos": (368, 105),
        "name": "Jurassic Park River Adventure",
        "wait": "30 min",
        "thrill": "⚡⚡⚡",
        "desc": "Raft ride with a thrilling 85-ft\nplunge. Height req: 42\"",
        "type": "Water Ride",
        "icon": "🌊",
    },
    {
        "pos": (230, 150),
        "name": "Skull Island: Reign of Kong",
        "wait": "20 min",
        "thrill": "⚡⚡⚡",
        "desc": "3D truck ride through Kong's island.\nHeight req: 36\"",
        "type": "Dark Ride",
        "icon": "🦍",
    },
    {
        "pos": (735, 135),
        "name": "Hagrid's Motorbike Adventure",
        "wait": "75 min",
        "thrill": "⚡⚡⚡⚡",
        "desc": "Magical creature adventure on a\nmotorbike. Height req: 48\"",
        "type": "Roller Coaster",
        "icon": "🧙",
    },
    {
        "pos": (680, 195),
        "name": "Hogsmeade - Harry Potter",
        "wait": "25 min",
        "thrill": "⚡⚡⚡",
        "desc": "Harry Potter and the Forbidden\nJourney. Height req: 48\"",
        "type": "Dark Ride",
        "icon": "⚡",
    },
    {
        "pos": (350, 380),
        "name": "The Amazing Adventures of Spider-Man",
        "wait": "15 min",
        "thrill": "⚡⚡⚡",
        "desc": "Classic 4K 3D dark ride.\nHeight req: 40\"",
        "type": "Dark Ride",
        "icon": "🕷️",
    },
    {
        "pos": (490, 490),
        "name": "The Incredible Hulk Coaster",
        "wait": "35 min",
        "thrill": "⚡⚡⚡⚡",
        "desc": "Zero-to-40 mph launch coaster.\nHeight req: 54\"",
        "type": "Roller Coaster",
        "icon": "💪",
    },
    {
        "pos": (620, 420),
        "name": "Caro-Seuss-el",
        "wait": "10 min",
        "thrill": "⚡",
        "desc": "A Dr. Seuss carousel for all ages.\nNo height requirement.",
        "type": "Family Ride",
        "icon": "🎠",
    },
    {
        "pos": (720, 460),
        "name": "The Cat in the Hat",
        "wait": "10 min",
        "thrill": "⚡",
        "desc": "Classic Seuss story dark ride.\nNo height requirement.",
        "type": "Family Ride",
        "icon": "🎩",
    },
    {
        "pos": (240, 255),
        "name": "Dudley Do-Right's Ripsaw Falls",
        "wait": "25 min",
        "thrill": "⚡⚡⚡",
        "desc": "Log flume ride — you WILL get wet!\nHeight req: 44\"",
        "type": "Water Ride",
        "icon": "💦",
    },
]

DOT_RADIUS      = 9
DOT_PULSE_MAX   = 5   # extra px for pulse ring
POPUP_W         = 290
POPUP_H         = 195
POPUP_PADDING   = 14
POPUP_CORNER    = 10

# --- State ---
active_popup = None   # index into RIDES, or None
hover_dot    = None   # index of hovered dot
pulse_tick   = 0      # for animated pulse ring


def draw_rounded_rect(surface, color, rect, radius, alpha=255):
    """Draw a filled rounded rectangle, optionally with alpha."""
    x, y, w, h = rect
    shape = pygame.Surface((w, h), pygame.SRCALPHA)
    r, g, b = color[:3]
    a = color[3] if len(color) == 4 else alpha
    pygame.draw.rect(shape, (r, g, b, a), (0, 0, w, h), border_radius=radius)
    surface.blit(shape, (x, y))


def draw_popup(surface, ride_idx):
    ride = RIDES[ride_idx]
    dot_x, dot_y = ride["pos"]

    # Position popup: try to the right, flip if near edge
    pop_x = dot_x + 18
    pop_y = dot_y - 20
    if pop_x + POPUP_W > SCREEN_W - 10:
        pop_x = dot_x - POPUP_W - 18
    if pop_y + POPUP_H > SCREEN_H - 10:
        pop_y = SCREEN_H - POPUP_H - 10
    if pop_y < 5:
        pop_y = 5

    # Shadow
    draw_rounded_rect(surface, (0, 0, 0, 120),
                      (pop_x + 4, pop_y + 4, POPUP_W, POPUP_H), POPUP_CORNER)

    # Background
    draw_rounded_rect(surface, POPUP_BG,
                      (pop_x, pop_y, POPUP_W, POPUP_H), POPUP_CORNER)

    # Border
    pygame.draw.rect(surface, POPUP_BORDER,
                     (pop_x, pop_y, POPUP_W, POPUP_H),
                     2, border_radius=POPUP_CORNER)

    # --- Header bar ---
    draw_rounded_rect(surface, (180, 10, 10, 200),
                      (pop_x, pop_y, POPUP_W, 36), POPUP_CORNER)
    # Only round top corners by overlapping a rect on the bottom half of header
    pygame.draw.rect(surface, (180, 10, 10, 200),
                     (pop_x, pop_y + 18, POPUP_W, 18))

    # Icon + title
    icon_surf = font_title.render(ride["icon"], True, WHITE)
    surface.blit(icon_surf, (pop_x + POPUP_PADDING, pop_y + 8))
    title_surf = font_title.render(ride["name"], True, WHITE)
    # Truncate title if too wide
    max_title_w = POPUP_W - 45
    if title_surf.get_width() > max_title_w:
        # Shorten with ellipsis
        name = ride["name"]
        while font_title.size(name + "…")[0] > max_title_w and len(name) > 0:
            name = name[:-1]
        title_surf = font_title.render(name + "…", True, WHITE)
    surface.blit(title_surf, (pop_x + POPUP_PADDING + 24, pop_y + 9))

    # Type tag
    cy = pop_y + 48
    tag_surf = font_small.render(ride["type"], True, GOLD)
    surface.blit(tag_surf, (pop_x + POPUP_PADDING, cy))

    # Wait time
    wait_label = font_body.render("⏱  Wait:", True, GRAY_LIGHT)
    wait_val   = font_body.render(ride["wait"], True, WHITE)
    surface.blit(wait_label, (pop_x + POPUP_PADDING, cy + 22))
    surface.blit(wait_val,   (pop_x + POPUP_PADDING + 70, cy + 22))

    # Thrill level
    thrill_label = font_body.render("Thrill:", True, GRAY_LIGHT)
    thrill_val   = font_body.render(ride["thrill"], True, (255, 160, 30))
    surface.blit(thrill_label, (pop_x + POPUP_PADDING, cy + 44))
    surface.blit(thrill_val,   (pop_x + POPUP_PADDING + 50, cy + 44))

    # Description (multi-line)
    desc_lines = ride["desc"].split("\n")
    for i, line in enumerate(desc_lines):
        d_surf = font_small.render(line, True, GRAY_LIGHT)
        surface.blit(d_surf, (pop_x + POPUP_PADDING, cy + 72 + i * 17))

    # Close button (×)
    close_rect = pygame.Rect(pop_x + POPUP_W - 28, pop_y + 6, 22, 22)
    pygame.draw.circle(surface, (80, 0, 0), close_rect.center, 11)
    pygame.draw.circle(surface, (220, 60, 60), close_rect.center, 11, 1)
    x_surf = font_close.render("×", True, WHITE)
    surface.blit(x_surf, (close_rect.x + 4, close_rect.y + 1))

    return close_rect   # so we can detect clicks on it


def draw_dots(surface, hover_idx, active_idx, pulse):
    close_btn = None
    for i, ride in enumerate(RIDES):
        x, y = ride["pos"]
        is_active = (i == active_idx)
        is_hover  = (i == hover_idx)

        # Pulse ring for hovered/active dot
        if is_active or is_hover:
            pulse_r = DOT_RADIUS + int(pulse * DOT_PULSE_MAX)
            pulse_a = max(30, 160 - int(pulse * 160))
            ring_surf = pygame.Surface((pulse_r * 2 + 4, pulse_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (220, 30, 30, pulse_a),
                               (pulse_r + 2, pulse_r + 2), pulse_r, 2)
            surface.blit(ring_surf, (x - pulse_r - 2, y - pulse_r - 2))

        # Outer shadow dot
        pygame.draw.circle(surface, (80, 0, 0), (x + 2, y + 2), DOT_RADIUS)
        # Main dot
        color = RED_HOVER if (is_hover or is_active) else RED
        pygame.draw.circle(surface, color, (x, y), DOT_RADIUS)
        # Outline
        pygame.draw.circle(surface, RED_OUTLINE, (x, y), DOT_RADIUS, 2)
        # White center glint
        pygame.draw.circle(surface, (255, 180, 180), (x - 2, y - 2), 3)

    # Draw active popup on top of all dots
    if active_idx is not None:
        close_btn = draw_popup(surface, active_idx)

    return close_btn


# ─── Main Loop ────────────────────────────────────────────────────────────────
running = True
close_btn_rect = None

while running:
    pulse_tick = (pulse_tick + 1) % 60
    pulse_norm = abs((pulse_tick / 30.0) - 1.0)   # 0→1→0 over 60 frames

    mx, my = pygame.mouse.get_pos()

    # Determine hovered dot
    hover_dot = None
    for i, ride in enumerate(RIDES):
        dx, dy = mx - ride["pos"][0], my - ride["pos"][1]
        if dx * dx + dy * dy <= (DOT_RADIUS + 4) ** 2:
            hover_dot = i
            break

    # Change cursor
    if hover_dot is not None or (close_btn_rect and close_btn_rect.collidepoint(mx, my)):
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
    else:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            active_popup = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Close button?
            if close_btn_rect and close_btn_rect.collidepoint(mx, my):
                active_popup = None
            # Dot clicked?
            elif hover_dot is not None:
                active_popup = hover_dot if active_popup != hover_dot else None
            # Click outside popup closes it
            elif active_popup is not None:
                active_popup = None

    # ── Draw ──
    screen.fill((20, 20, 30))
    screen.blit(mapImage, (0, 0))

    close_btn_rect = draw_dots(screen, hover_dot, active_popup, pulse_norm)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()