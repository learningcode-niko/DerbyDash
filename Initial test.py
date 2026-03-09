"""
Derby Dash — First-Person Risk/Reward Runner
============================================
Course project implementation in Python + Pygame.

Install:  pip install pygame
Run:      python derby_dash.py

Controls
--------
BAR PHASE:
  LEFT / RIGHT   — browse drinks
  ENTER / SPACE  — add selected drink
  BACKSPACE      — remove last drink
  R              — start the race

RACE PHASE:
  LEFT / RIGHT   — switch lane
  UP             — jump  (clears fences, hay, hurdles)
  DOWN (hold)    — duck  (clears barriers)
"""

import pygame
import sys
import math
import random

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
W, H = 900, 600
FPS  = 60
TITLE = "DERBY DASH"

# Colours
C_BG        = (10, 5, 0)
C_SKY_TOP   = (13, 27, 42)
C_SKY_BOT   = (26, 58, 92)
C_GRASS     = (18, 52, 10)
C_GRASS2    = (14, 40, 8)
C_TRACK     = (90, 75, 50)
C_TRACK2    = (80, 65, 42)
C_WHITE     = (240, 230, 200)
C_GOLD      = (212, 160, 23)
C_DARK_GOLD = (139, 105, 20)
C_RED       = (192, 57,  43)
C_GREEN     = (39,  174, 96)
C_BLUE      = (52,  152, 219)
C_DARK      = (20, 10, 0)
C_PANEL     = (16, 8, 0)
C_WOOD      = (61, 31, 0)
C_WOOD2     = (92, 46, 0)

# Track / perspective
HORIZON_Y   = 200       # pixel row of vanishing point
GROUND_Y    = H         # pixel row at player's feet
LANE_COUNT  = 3
# At depth=0 (feet) the three lane centres in screen-X
LANE_FEET_X = [W * 0.18, W * 0.50, W * 0.82]

# Obstacle depth at which collision is checked
HIT_DEPTH_MIN = 0.00
HIT_DEPTH_MAX = 0.13

# ─────────────────────────────────────────────────────────────────────────────
#  DRINKS CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────
DRINKS = [
    dict(name="WATER",   emoji="💧", symbol="~", mult=1.0, drunk=0, color=(126, 200, 227)),
    dict(name="BEER",    emoji="🍺", symbol="B", mult=1.5, drunk=1, color=(240, 165,   0)),
    dict(name="CIDER",   emoji="🍎", symbol="C", mult=2.0, drunk=2, color=(192,  57,  43)),
    dict(name="WHISKEY", emoji="🥃", symbol="W", mult=3.0, drunk=3, color=(139,  69,  19)),
    dict(name="VODKA",   emoji="🍸", symbol="V", mult=5.0, drunk=5, color=(160, 216, 239)),
]
MAX_DRINKS = 5

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE CATALOGUE  (h/w are fractions of lane-width at full scale)
# ─────────────────────────────────────────────────────────────────────────────
OBS_TYPES = [
    dict(label="FENCE",   color=(200, 168, 75), alt=(139, 105, 20),
         rel_w=0.90, rel_h=0.55, block_jump=False, block_duck=True),
    dict(label="HAY",     color=(232, 192, 96), alt=(160, 120, 48),
         rel_w=0.95, rel_h=0.50, block_jump=False, block_duck=True),
    dict(label="BARRIER", color=(231,  76, 60), alt=(192,  57, 43),
         rel_w=1.00, rel_h=0.35, block_jump=True,  block_duck=False),
    dict(label="HURDLE",  color=(93,  173, 226), alt=(41, 128, 185),
         rel_w=0.85, rel_h=0.60, block_jump=False, block_duck=True),
]

# ─────────────────────────────────────────────────────────────────────────────
#  PERSPECTIVE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def depth_to_y(depth: float) -> float:
    """depth 1.0 = horizon, 0.0 = player feet"""
    return HORIZON_Y + (GROUND_Y - HORIZON_Y) * (1.0 - depth)

def depth_to_scale(depth: float) -> float:
    return max(0.0, 1.0 - depth)

def lane_to_x(lane: int, depth: float) -> float:
    t = 1.0 - depth  # 0 at horizon, 1 at feet
    cx = W / 2
    foot_x = LANE_FEET_X[lane]
    return cx + (foot_x - cx) * t

def lane_pixel_width(depth: float) -> float:
    """How wide (px) a lane appears at this depth."""
    t = 1.0 - depth
    full_span = LANE_FEET_X[2] - LANE_FEET_X[0]  # px span across 3 lanes at feet
    return (full_span / LANE_COUNT) * t

# ─────────────────────────────────────────────────────────────────────────────
#  UTILITY — rounded-rect
# ─────────────────────────────────────────────────────────────────────────────
def draw_round_rect(surface, color, rect, radius=8, border=0, border_color=None):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surface, border_color, rect, border, border_radius=radius)

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE  (dataclass-style)
# ─────────────────────────────────────────────────────────────────────────────
class Obstacle:
    def __init__(self, lane: int, otype: dict):
        self.lane      = lane
        self.depth     = 1.0
        self.label     = otype["label"]
        self.color     = otype["color"]
        self.alt       = otype["alt"]
        self.rel_w     = otype["rel_w"]
        self.rel_h     = otype["rel_h"]
        self.block_jump = otype["block_jump"]
        self.block_duck = otype["block_duck"]

    def update(self, speed: float):
        self.depth -= speed

    def screen_rect(self) -> pygame.Rect:
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        lw   = lane_pixel_width(self.depth)
        w    = lw * self.rel_w
        h    = lw * self.rel_h
        return pygame.Rect(cx - w / 2, base - h, w, h)

    def draw(self, surf: pygame.Surface):
        r = self.screen_rect()
        if r.width < 2 or r.height < 2:
            return
        if self.label == "FENCE":
            self._draw_fence(surf, r)
        elif self.label == "HAY":
            self._draw_hay(surf, r)
        elif self.label == "BARRIER":
            self._draw_barrier(surf, r)
        elif self.label == "HURDLE":
            self._draw_hurdle(surf, r)

    def _draw_fence(self, surf, r):
        # Rails
        rail_h = max(2, r.height // 5)
        for frac in (0.25, 0.65):
            pygame.draw.rect(surf, self.color,
                             (r.x, r.y + int(r.height * frac), r.width, rail_h))
        # Posts
        post_w = max(2, r.width // 7)
        for i in range(5):
            px = r.x + i * r.width // 4
            pygame.draw.rect(surf, self.alt, (px, r.y, post_w, r.height))
        # Dark outline
        pygame.draw.rect(surf, (0, 0, 0), r, 1)

    def _draw_hay(self, surf, r):
        pygame.draw.rect(surf, self.color, r, border_radius=4)
        stripe_h = max(1, r.height // 6)
        for i in range(1, 5):
            y = r.y + i * r.height // 5
            pygame.draw.rect(surf, self.alt, (r.x, y, r.width, stripe_h))
        pygame.draw.rect(surf, (0, 0, 0), r, 1, border_radius=4)

    def _draw_barrier(self, surf, r):
        pygame.draw.rect(surf, self.alt, r, border_radius=3)
        # Diagonal warning stripes
        stripe_w = max(4, r.width // 6)
        for i in range(-2, 8):
            sx = r.x + i * stripe_w * 2
            pts = [
                (sx,            r.y),
                (sx + stripe_w, r.y),
                (sx + stripe_w + r.height, r.bottom),
                (sx + r.height,            r.bottom),
            ]
            # clip to rect bounds by clipping surface
            pygame.draw.polygon(surf, (240, 230, 50), pts)
        pygame.draw.rect(surf, self.alt, r, 3, border_radius=3)
        pygame.draw.rect(surf, (0, 0, 0), r, 1, border_radius=3)

    def _draw_hurdle(self, surf, r):
        post_w = max(2, r.width // 10)
        bar_h  = max(2, r.height // 6)
        # Two vertical posts
        pygame.draw.rect(surf, self.alt, (r.x, r.y, post_w, r.height))
        pygame.draw.rect(surf, self.alt, (r.right - post_w, r.y, post_w, r.height))
        # Cross bar
        bar_y = r.y + r.height // 3
        pygame.draw.rect(surf, self.color, (r.x, bar_y, r.width, bar_h))
        pygame.draw.rect(surf, (0, 0, 0), r, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  SECURITY GUARD  (enemy)
# ─────────────────────────────────────────────────────────────────────────────
class Guard:
    def __init__(self, lane: int):
        self.lane  = lane
        self.depth = 1.0
        self.anim  = 0  # walk cycle

    def update(self, speed: float, player_lane: int):
        self.depth -= speed * 0.70
        self.anim  += 1
        # Occasionally drift toward player lane (AI)
        if random.random() < 0.007:
            self.lane = player_lane

    def draw(self, surf: pygame.Surface):
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        sc   = depth_to_scale(self.depth)
        if sc < 0.05:
            return
        lw = lane_pixel_width(self.depth)
        bw = max(4, int(lw * 0.40))
        bh = max(6, int(lw * 0.80))
        bx = int(cx - bw / 2)
        by = int(base - bh)

        # Body (dark uniform)
        pygame.draw.rect(surf, (26, 26, 46), (bx, by, bw, bh), border_radius=3)
        # Hi-vis vest
        vest_h = max(2, bh // 3)
        pygame.draw.rect(surf, (243, 156, 18), (bx, by + bh // 4, bw, vest_h))
        pygame.draw.rect(surf, (0, 0, 0), (bx, by + bh // 4, bw, vest_h), 1)
        # Head
        head_r = max(3, bw // 2)
        pygame.draw.circle(surf, (212, 162, 122), (int(cx), by - head_r // 2), head_r)
        # Arms spread (blocking pose)
        arm_y  = by + bh // 3
        arm_len = max(4, bw)
        pygame.draw.line(surf, (26, 26, 46),
                         (bx, arm_y), (bx - arm_len, arm_y + arm_len // 2), max(1, bw // 4))
        pygame.draw.line(surf, (26, 26, 46),
                         (bx + bw, arm_y), (bx + bw + arm_len, arm_y + arm_len // 2), max(1, bw // 4))
        # Walk cycle — feet
        if sc > 0.3:
            kick = int(math.sin(self.anim * 0.25) * bw * 0.4)
            pygame.draw.line(surf, (26, 26, 46),
                             (int(cx) - bw // 4, by + bh),
                             (int(cx) - bw // 4 + kick, by + bh + max(3, bh // 4)),
                             max(1, bw // 5))
            pygame.draw.line(surf, (26, 26, 46),
                             (int(cx) + bw // 4, by + bh),
                             (int(cx) + bw // 4 - kick, by + bh + max(3, bh // 4)),
                             max(1, bw // 5))
        # SEC label when large enough
        if sc > 0.5 and bw > 20:
            font = pygame.font.SysFont("monospace", max(8, bw // 3), bold=True)
            txt  = font.render("SEC", True, (26, 26, 46))
            surf.blit(txt, txt.get_rect(center=(int(cx), by + vest_h // 2 + bh // 4)))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN GAME CLASS
# ─────────────────────────────────────────────────────────────────────────────
class DerbyDash:
    # ── states ────────────────────────────────────────────────────────────────
    STATE_BAR      = "bar"
    STATE_RACE     = "race"
    STATE_GAMEOVER = "gameover"

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption(TITLE)
        self.clock  = pygame.time.Clock()

        # Fonts
        self.f_huge   = pygame.font.SysFont("monospace", 64, bold=True)
        self.f_large  = pygame.font.SysFont("monospace", 32, bold=True)
        self.f_med    = pygame.font.SysFont("monospace", 18, bold=True)
        self.f_small  = pygame.font.SysFont("monospace", 13)
        self.f_tiny   = pygame.font.SysFont("monospace", 11)

        self._reset_bar()
        self.state = self.STATE_BAR

    # ── reset helpers ─────────────────────────────────────────────────────────
    def _reset_bar(self):
        self.drink_history = []   # list of drink dicts added
        self.drunk_level   = 0
        self.multiplier    = 1.0
        self.selected_drink = 0

    def _reset_race(self):
        self.obstacles     = []
        self.guards        = []
        self.player_lane   = 1
        self.player_y      = 0.0   # px offset (negative = in air)
        self.is_jumping    = False
        self.is_ducking    = False
        self.jump_vel      = 0.0
        self.base_score    = 0
        self.survive_time  = 0.0
        self.race_frame    = 0
        self.game_speed    = 0.010
        self.spawn_timer   = 0
        self.spawn_interval = 80
        self.bg_offset     = 0.0
        # Drunk FX
        self.input_queue   = []    # (frame_to_fire, action)
        self.sway_angle    = 0.0
        self.distort_phase = 0.0
        self.stumble_timer = 0
        self.stumble_dx    = 0.0
        self.drunk_flash   = 0     # countdown for flash overlay

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            self._handle_events()
            if self.state == self.STATE_BAR:
                self._update_bar()
                self._draw_bar()
            elif self.state == self.STATE_RACE:
                self._update_race()
                self._draw_race()
            elif self.state == self.STATE_GAMEOVER:
                self._draw_gameover()
            pygame.display.flip()

    # ─────────────────────────────────────────────────────────────────────────
    #  EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if self.state == self.STATE_BAR:
                    self._bar_keydown(event.key)
                elif self.state == self.STATE_RACE:
                    self._race_keydown(event.key)
                elif self.state == self.STATE_GAMEOVER:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
                        self._reset_bar()
                        self.state = self.STATE_BAR

            if event.type == pygame.KEYUP:
                if self.state == self.STATE_RACE:
                    if event.key == pygame.K_DOWN:
                        self.is_ducking = False

    # ─────────────────────────────────────────────────────────────────────────
    #  BAR PHASE
    # ─────────────────────────────────────────────────────────────────────────
    def _bar_keydown(self, key):
        if key == pygame.K_LEFT:
            self.selected_drink = (self.selected_drink - 1) % len(DRINKS)
        elif key == pygame.K_RIGHT:
            self.selected_drink = (self.selected_drink + 1) % len(DRINKS)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._add_drink()
        elif key == pygame.K_BACKSPACE:
            self._remove_drink()
        elif key == pygame.K_r:
            self._start_race()

    def _add_drink(self):
        if len(self.drink_history) >= MAX_DRINKS:
            return
        d = DRINKS[self.selected_drink]
        self.drink_history.append(d)
        self.drunk_level += d["drunk"]
        self.multiplier  *= d["mult"]

    def _remove_drink(self):
        if not self.drink_history:
            return
        d = self.drink_history.pop()
        self.drunk_level -= d["drunk"]
        self.multiplier  /= d["mult"]
        self.drunk_level  = max(0, self.drunk_level)
        self.multiplier   = max(1.0, self.multiplier)

    def _start_race(self):
        self._reset_race()
        self.state = self.STATE_RACE

    def _update_bar(self):
        pass  # nothing needs updating every frame in bar state

    def _draw_bar(self):
        surf = self.screen
        surf.fill(C_BG)

        # Background wood texture lines
        for i in range(0, H, 18):
            pygame.draw.line(surf, (18, 9, 0), (0, i), (W, i))

        # Title bar
        pygame.draw.rect(surf, (30, 15, 0), (0, 0, W, 56))
        pygame.draw.line(surf, C_DARK_GOLD, (0, 56), (W, 56), 2)
        title = self.f_large.render("🏇  DERBY DASH  —  THE BAR  🍺", True, C_WHITE)
        surf.blit(title, title.get_rect(center=(W // 2, 28)))

        # Stats row
        stats = self.f_med.render(
            f"DRINKS: {len(self.drink_history)}/{MAX_DRINKS}     "
            f"MULTIPLIER: x{self.multiplier:.1f}     "
            f"DRUNK LEVEL: {self.drunk_level}",
            True, C_GOLD)
        surf.blit(stats, stats.get_rect(center=(W // 2, 76)))

        # Drunk meter
        max_drunk = 15
        meter_w, meter_h = 340, 14
        mx = W // 2 - meter_w // 2
        my = 92
        pygame.draw.rect(surf, (30, 15, 0), (mx, my, meter_w, meter_h))
        frac = min(self.drunk_level / max_drunk, 1.0)
        bar_color = C_GREEN if frac < 0.4 else (C_GOLD if frac < 0.70 else C_RED)
        pygame.draw.rect(surf, bar_color, (mx, my, int(meter_w * frac), meter_h))
        pygame.draw.rect(surf, C_DARK_GOLD, (mx, my, meter_w, meter_h), 1)
        label_l = self.f_tiny.render("SOBER", True, C_DARK_GOLD)
        label_r = self.f_tiny.render("WRECKED", True, C_DARK_GOLD)
        surf.blit(label_l, (mx, my + meter_h + 3))
        surf.blit(label_r, (mx + meter_w - label_r.get_width(), my + meter_h + 3))

        # ── Drink cards ───────────────────────────────────────────────────────
        card_w, card_h = 140, 130
        gap = 12
        total_w = len(DRINKS) * card_w + (len(DRINKS) - 1) * gap
        start_x = W // 2 - total_w // 2
        card_y  = 128

        for i, d in enumerate(DRINKS):
            cx   = start_x + i * (card_w + gap)
            sel  = (i == self.selected_drink)
            border_col = d["color"] if sel else (60, 30, 0)
            bg_col     = (36, 18, 0) if sel else (20, 10, 0)
            draw_round_rect(surf, bg_col, (cx, card_y, card_w, card_h), 8,
                            border=2 if sel else 1, border_color=border_col)

            # Glow behind selected card
            if sel:
                glow_surf = pygame.Surface((card_w + 20, card_h + 20), pygame.SRCALPHA)
                glow_col  = d["color"] + (40,)
                pygame.draw.rect(glow_surf, glow_col, (0, 0, card_w + 20, card_h + 20), border_radius=14)
                surf.blit(glow_surf, (cx - 10, card_y - 10))
                draw_round_rect(surf, bg_col, (cx, card_y, card_w, card_h), 8,
                                border=2, border_color=border_col)

            # Drink symbol (large letter since emoji rendering varies)
            sym_surf = self.f_large.render(d["symbol"], True, d["color"])
            surf.blit(sym_surf, sym_surf.get_rect(center=(cx + card_w // 2, card_y + 34)))

            name_surf = self.f_small.render(d["name"], True, d["color"])
            surf.blit(name_surf, name_surf.get_rect(center=(cx + card_w // 2, card_y + 62)))

            mult_surf = self.f_tiny.render(f"x{d['mult']:.1f} MULT", True, C_WHITE)
            surf.blit(mult_surf, mult_surf.get_rect(center=(cx + card_w // 2, card_y + 82)))

            drunk_surf = self.f_tiny.render(f"+{d['drunk']} DRUNK", True, (180, 140, 60))
            surf.blit(drunk_surf, drunk_surf.get_rect(center=(cx + card_w // 2, card_y + 98)))

            # "SELECTED" arrow
            if sel:
                arr = self.f_tiny.render("▲ SELECTED", True, d["color"])
                surf.blit(arr, arr.get_rect(center=(cx + card_w // 2, card_y + 118)))

        # ── Added drinks history dots ─────────────────────────────────────────
        dot_y = card_y + card_h + 22
        for i in range(MAX_DRINKS):
            dot_x = W // 2 - (MAX_DRINKS * 22) // 2 + i * 22 + 11
            pygame.draw.circle(surf, C_DARK_GOLD, (dot_x, dot_y), 7)
            if i < len(self.drink_history):
                pygame.draw.circle(surf, self.drink_history[i]["color"], (dot_x, dot_y), 6)

        # ── Info panel (selected drink details) ──────────────────────────────
        panel_x, panel_y, panel_w, panel_h = 28, 130, 180, 200
        draw_round_rect(surf, C_PANEL, (panel_x, panel_y, panel_w, panel_h), 8,
                        border=1, border_color=(60, 30, 0))
        d = DRINKS[self.selected_drink]
        ph = self.f_med.render("SELECTED", True, C_DARK_GOLD)
        surf.blit(ph, ph.get_rect(center=(panel_x + panel_w // 2, panel_y + 18)))
        sym = self.f_huge.render(d["symbol"], True, d["color"])
        surf.blit(sym, sym.get_rect(center=(panel_x + panel_w // 2, panel_y + 70)))
        nm  = self.f_med.render(d["name"], True, d["color"])
        surf.blit(nm, nm.get_rect(center=(panel_x + panel_w // 2, panel_y + 108)))
        for j, line in enumerate([
                f"Multiplier: x{d['mult']:.1f}",
                f"Drunk add:  +{d['drunk']}",
        ]):
            t = self.f_tiny.render(line, True, C_WHITE)
            surf.blit(t, t.get_rect(center=(panel_x + panel_w // 2, panel_y + 132 + j * 16)))

        # Effects warning
        effects = []
        if d["drunk"] >= 1: effects.append("Input delay")
        if d["drunk"] >= 2: effects.append("Camera sway")
        if d["drunk"] >= 3: effects.append("Stumbles")
        if d["drunk"] >= 5: effects.append("Distortion")
        for j, ef in enumerate(effects):
            t = self.f_tiny.render(f"! {ef}", True, C_RED)
            surf.blit(t, t.get_rect(center=(panel_x + panel_w // 2, panel_y + 164 + j * 14)))

        # ── Current build panel ───────────────────────────────────────────────
        bp_x, bp_y, bp_w, bp_h = W - 28 - 180, 130, 180, 200
        draw_round_rect(surf, C_PANEL, (bp_x, bp_y, bp_w, bp_h), 8,
                        border=1, border_color=(60, 30, 0))
        bh_t = self.f_med.render("YOUR BUILD", True, C_DARK_GOLD)
        surf.blit(bh_t, bh_t.get_rect(center=(bp_x + bp_w // 2, bp_y + 18)))
        m_t = self.f_large.render(f"x{self.multiplier:.1f}", True, C_WHITE)
        surf.blit(m_t, m_t.get_rect(center=(bp_x + bp_w // 2, bp_y + 62)))
        ml = self.f_tiny.render("SCORE MULTIPLIER", True, C_DARK_GOLD)
        surf.blit(ml, ml.get_rect(center=(bp_x + bp_w // 2, bp_y + 86)))
        # Risk bar
        risk_frac = min(self.drunk_level / max_drunk, 1.0)
        rw = bp_w - 30
        rx, ry = bp_x + 15, bp_y + 108
        pygame.draw.rect(surf, (30, 15, 0), (rx, ry, rw, 10))
        rc = C_GREEN if risk_frac < 0.4 else (C_GOLD if risk_frac < 0.7 else C_RED)
        pygame.draw.rect(surf, rc, (rx, ry, int(rw * risk_frac), 10))
        pygame.draw.rect(surf, C_DARK_GOLD, (rx, ry, rw, 10), 1)
        risk_label = "LOW" if risk_frac < 0.33 else ("MEDIUM" if risk_frac < 0.66 else ("HIGH" if risk_frac < 0.9 else "EXTREME"))
        rl = self.f_tiny.render(f"RISK: {risk_label}", True, rc)
        surf.blit(rl, rl.get_rect(center=(bp_x + bp_w // 2, bp_y + 126)))

        # Drink history list
        for j, dh in enumerate(self.drink_history):
            dht = self.f_tiny.render(f"+ {dh['name']}", True, dh["color"])
            surf.blit(dht, dht.get_rect(center=(bp_x + bp_w // 2, bp_y + 148 + j * 13)))

        # ── Bottom bar ────────────────────────────────────────────────────────
        pygame.draw.rect(surf, C_WOOD, (0, H - 60, W, 60))
        pygame.draw.line(surf, C_DARK_GOLD, (0, H - 60), (W, H - 60), 2)
        controls = [
            "← → : SELECT DRINK",
            "ENTER/SPACE : ADD",
            "BACKSPACE : REMOVE LAST",
            "R : START RACE",
        ]
        for j, c in enumerate(controls):
            ct = self.f_tiny.render(c, True, C_DARK_GOLD)
            surf.blit(ct, (20 + j * 210, H - 38))

        # Start button
        btn_col = C_DARK_GOLD if self.drink_history else (60, 40, 0)
        draw_round_rect(surf, btn_col, (W - 175, H - 50, 160, 38), 6)
        bt = self.f_med.render("START RACE  R", True, C_DARK if self.drink_history else (80, 60, 20))
        surf.blit(bt, bt.get_rect(center=(W - 95, H - 31)))

    # ─────────────────────────────────────────────────────────────────────────
    #  RACE PHASE
    # ─────────────────────────────────────────────────────────────────────────
    def _race_keydown(self, key):
        delay_frames = self.drunk_level * 5
        if key == pygame.K_LEFT:
            self.input_queue.append((self.race_frame + delay_frames, "left"))
        elif key == pygame.K_RIGHT:
            self.input_queue.append((self.race_frame + delay_frames, "right"))
        elif key == pygame.K_UP:
            self.input_queue.append((self.race_frame + delay_frames, "jump"))
        elif key == pygame.K_DOWN:
            self.is_ducking = True  # duck is instant (hold key), no delay

    def _process_input_queue(self):
        remaining = []
        for (fire_at, action) in self.input_queue:
            if self.race_frame >= fire_at:
                if action == "left":
                    self.player_lane = max(0, self.player_lane - 1)
                elif action == "right":
                    self.player_lane = min(2, self.player_lane + 1)
                elif action == "jump" and not self.is_jumping:
                    self.is_jumping = True
                    self.jump_vel   = -16.0
            else:
                remaining.append((fire_at, action))
        self.input_queue = remaining

    def _update_race(self):
        self.race_frame  += 1
        self.survive_time = self.race_frame / FPS
        self.base_score   = int(self.survive_time * 10)

        # Speed / difficulty ramp
        self.game_speed    = 0.010 + self.survive_time * 0.00013
        self.spawn_interval = max(32, 80 - self.survive_time * 1.0)

        # Spawn
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            otype = random.choice(OBS_TYPES)
            lane  = random.randint(0, 2)
            self.obstacles.append(Obstacle(lane, otype))
            if random.random() < 0.22:
                self.guards.append(Guard(random.randint(0, 2)))

        # Jump physics
        if self.is_jumping:
            self.jump_vel   += 0.9
            self.player_y   += self.jump_vel
            if self.player_y >= 0:
                self.player_y  = 0
                self.is_jumping = False
                self.jump_vel   = 0.0

        # Drunk effects
        self.sway_angle    = math.sin(self.race_frame * 0.04) * self.drunk_level * 0.018
        self.distort_phase += 0.05 + self.drunk_level * 0.01
        if self.drunk_level >= 3:
            self.stumble_timer -= 1
            if self.stumble_timer <= 0:
                self.stumble_timer = random.randint(55, 130)
                self.stumble_dx    = (random.random() - 0.5) * 26 * self.drunk_level \
                                     if random.random() < 0.4 else 0.0

        self._process_input_queue()

        # Move objects
        for obs in self.obstacles:
            obs.update(self.game_speed)
        self.obstacles = [o for o in self.obstacles if o.depth > -0.08]

        for g in self.guards:
            g.update(self.game_speed, self.player_lane)
        self.guards = [g for g in self.guards if g.depth > -0.08]

        # Collision detection — hit zone is depth 0.0–0.13
        for obs in self.obstacles:
            if obs.lane != self.player_lane:
                continue
            if not (HIT_DEPTH_MIN <= obs.depth <= HIT_DEPTH_MAX):
                continue
            clear_jump = self.is_jumping and self.player_y < -28 and not obs.block_jump
            clear_duck = self.is_ducking and obs.block_duck
            if not clear_jump and not clear_duck:
                self.state = self.STATE_GAMEOVER
                return

        for g in self.guards:
            if g.lane == self.player_lane and HIT_DEPTH_MIN <= g.depth <= HIT_DEPTH_MAX:
                self.state = self.STATE_GAMEOVER
                return

        self.bg_offset += self.game_speed * 60

    def _draw_race(self):
        surf = self.screen

        # ── Camera shake / sway ───────────────────────────────────────────────
        sway_x = math.sin(self.race_frame * 0.055) * self.drunk_level * 5 + self.stumble_dx * 0.3
        # We draw everything onto a temp surface then rotate/offset it
        scene = pygame.Surface((W, H))

        self._draw_track_bg(scene)

        # Sort obstacles + guards back-to-front (high depth = far = draw first)
        all_objs = [(obs.depth, obs) for obs in self.obstacles] + \
                   [(g.depth,   g)   for g   in self.guards]
        all_objs.sort(key=lambda x: -x[0])
        for _, obj in all_objs:
            obj.draw(scene)

        self._draw_player(scene)

        # Drunk overlays
        if self.drunk_level >= 2:
            vig = pygame.Surface((W, H), pygame.SRCALPHA)
            alpha = min(180, self.drunk_level * 18)
            pygame.draw.circle(vig, (180, 0, 0, 0), (W // 2, H // 2), W // 2)
            # radial vignette
            for radius in range(W // 2, W // 2 - 80, -8):
                a = max(0, int((1 - radius / (W / 2)) * alpha * 2))
                pygame.draw.circle(vig, (0, 0, 0, a), (W // 2, H // 2), radius, 8)
            scene.blit(vig, (0, 0))

        if self.drunk_level >= 4:
            flash_alpha = int(abs(math.sin(self.distort_phase)) * (self.drunk_level - 3) * 20)
            flash = pygame.Surface((W, H), pygame.SRCALPHA)
            flash.fill((0, 180, 0, flash_alpha))
            scene.blit(flash, (0, 0))

        # Apply sway rotation to scene
        angle_deg = math.degrees(self.sway_angle)
        rotated   = pygame.transform.rotate(scene, angle_deg)
        rx = W // 2 - rotated.get_width()  // 2 + int(sway_x)
        ry = H // 2 - rotated.get_height() // 2
        surf.blit(rotated, (rx, ry))

        self._draw_hud(surf)

    def _draw_track_bg(self, surf):
        # Sky gradient (banded)
        sky_bands = 30
        for i in range(sky_bands):
            t   = i / sky_bands
            col = tuple(int(C_SKY_TOP[c] + (C_SKY_BOT[c] - C_SKY_TOP[c]) * t) for c in range(3))
            y   = int(HORIZON_Y * i / sky_bands)
            pygame.draw.rect(surf, col, (0, y, W, max(1, HORIZON_Y // sky_bands + 1)))

        # Sun glow at horizon
        glow_surf = pygame.Surface((W, 100), pygame.SRCALPHA)
        for r in range(200, 0, -10):
            a = max(0, int(30 - r // 7))
            pygame.draw.ellipse(glow_surf, (255, 200, 80, a),
                                (W // 2 - r, 50 - r // 4, r * 2, r // 2))
        surf.blit(glow_surf, (0, HORIZON_Y - 50))

        # Grandstand silhouettes (scrolling)
        for i in range(22):
            x = int((i * 68 + self.bg_offset * 0.4) % (W + 68)) - 34
            h2 = 40 + (i % 4) * 14
            col = (14 + (i % 3) * 4, 14, 20 + (i % 2) * 5)
            pygame.draw.rect(surf, col, (x, HORIZON_Y - h2, 55, h2))

        # ── Ground / track trapezoid ──────────────────────────────────────────
        # The track is drawn as alternating stripes receding to the horizon
        stripe_count = 16
        depth_step   = 1.0 / stripe_count
        for i in range(stripe_count - 1, -1, -1):
            d0 = i       * depth_step
            d1 = (i + 1) * depth_step
            y0 = depth_to_y(d0)
            y1 = depth_to_y(d1)
            # left and right track edges at these depths
            lx0 = lane_to_x(0, d0) - lane_pixel_width(d0) * 0.6
            rx0 = lane_to_x(2, d0) + lane_pixel_width(d0) * 0.6
            lx1 = lane_to_x(0, d1) - lane_pixel_width(d1) * 0.6
            rx1 = lane_to_x(2, d1) + lane_pixel_width(d1) * 0.6
            # Alternating track colour
            base_col = C_TRACK if i % 2 == 0 else C_TRACK2
            pygame.draw.polygon(surf, base_col, [
                (lx1, y1), (rx1, y1), (rx0, y0), (lx0, y0)
            ])

        # Grass either side
        pygame.draw.rect(surf, C_GRASS, (0, HORIZON_Y, W, H - HORIZON_Y))
        # Overdraw track area (we just did it above, grass fills the sides)

        # ── Lane dividers ─────────────────────────────────────────────────────
        for lane_edge in range(4):
            lane_idx = min(lane_edge, 2)
            side     = -0.5 if lane_edge == 0 else (0.5 if lane_edge == 3 else
                        (-0.5 if lane_edge == 1 else 0.5))
            # approximate: draw a line from horizon to bottom
            x_near = lane_to_x(lane_idx, 0.02) + lane_pixel_width(0.02) * (lane_edge - 1.5) / 1.5 * 0.5
            x_far  = W / 2 + (x_near - W / 2) * 0.02
            # simpler: just draw the 4 outer+inner lane lines
        # Lane lines
        for div in range(4):  # 0=left edge, 1=left-center, 2=center-right, 3=right edge
            offsets = [-0.5, 0.5]
            if div == 0:
                base_lane, off = 0, -0.5
            elif div == 1:
                base_lane, off = 0, 0.5
            elif div == 2:
                base_lane, off = 1, 0.5
            else:
                base_lane, off = 2, 0.5
            # near and far points
            near_x = lane_to_x(base_lane, 0.0) + lane_pixel_width(0.0) * off
            far_x  = lane_to_x(base_lane, 0.97) + lane_pixel_width(0.97) * off
            col = (255, 255, 255, 80)
            pygame.draw.line(surf, (200, 180, 120), (int(far_x), HORIZON_Y), (int(near_x), H), 2)

        # Scrolling dashed centre lines between lanes
        dash_spacing = 0.08
        for lane_gap in range(2):  # gap between lane 0-1 and lane 1-2
            for d_step in range(14):
                d_center = ((self.bg_offset * 0.01) % dash_spacing) + d_step * dash_spacing
                if d_center > 0.95:
                    continue
                d_end = d_center + dash_spacing * 0.4
                if d_end > 0.99:
                    continue
                lx_a = lane_to_x(lane_gap, d_center)
                rx_a = lane_to_x(lane_gap + 1, d_center)
                mx_a = (lx_a + rx_a) / 2
                lx_b = lane_to_x(lane_gap, d_end)
                rx_b = lane_to_x(lane_gap + 1, d_end)
                mx_b = (lx_b + rx_b) / 2
                lw   = max(1, int(lane_pixel_width(d_center) * 0.05))
                pygame.draw.line(surf, (220, 200, 140),
                                 (int(mx_a), int(depth_to_y(d_center))),
                                 (int(mx_b), int(depth_to_y(d_end))), lw)

    def _draw_player(self, surf):
        """Draw the player's visible body at the bottom of the screen."""
        px = int(lane_to_x(self.player_lane, 0.0) + self.stumble_dx)
        ground = H - 10

        bob = int(math.sin(self.bg_offset * 0.35) * (0 if self.is_ducking else 5))

        if self.is_ducking:
            # Crouched torso
            bw, bh = 52, 36
            by = ground - bh + bob
            pygame.draw.rect(surf, (44, 62, 80), (px - bw // 2, by, bw, bh), border_radius=6)
            pygame.draw.rect(surf, (231, 76, 60), (px - bw // 2, by + 4, bw, 12))
        else:
            # Jump offset
            jy = int(self.player_y)
            bw, bh = 44, 70
            by = ground - bh + bob + jy
            # Legs
            leg_kick = int(math.sin(self.bg_offset * 0.35) * 12)
            pygame.draw.line(surf, (44, 62, 80),
                             (px - 10, by + bh), (px - 10 + leg_kick, by + bh + 22), 10)
            pygame.draw.line(surf, (44, 62, 80),
                             (px + 10, by + bh), (px + 10 - leg_kick, by + bh + 22), 10)
            # Body
            pygame.draw.rect(surf, (44, 62, 80), (px - bw // 2, by, bw, bh), border_radius=6)
            # Shirt stripe
            pygame.draw.rect(surf, (231, 76, 60), (px - bw // 2, by + 6, bw, 14))
            # Head
            pygame.draw.circle(surf, (210, 160, 120), (px, by - 14), 18)
            # Hat
            pygame.draw.rect(surf, (30, 20, 10), (px - 20, by - 30, 40, 10))
            pygame.draw.rect(surf, (30, 20, 10), (px - 13, by - 46, 26, 18), border_radius=4)

        # Shadow on ground
        shadow_w = 48 if not self.is_ducking else 60
        shadow_surf = pygame.Surface((shadow_w, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, 70), (0, 0, shadow_w, 14))
        surf.blit(shadow_surf, (px - shadow_w // 2, ground - 7))

        # Lane indicators (dots at bottom)
        for i in range(3):
            dot_x = int(lane_to_x(i, 0.0))
            col   = C_WHITE if i == self.player_lane else C_DARK_GOLD
            pygame.draw.circle(surf, col, (dot_x, H - 12), 5)
            pygame.draw.circle(surf, (0, 0, 0), (dot_x, H - 12), 5, 1)

    def _draw_hud(self, surf):
        # Score
        score = int(self.base_score * self.multiplier)
        sc_t  = self.f_large.render(f"SCORE: {score:,}", True, C_WHITE)
        surf.blit(sc_t, (14, 8))

        # Multiplier
        mult_col = C_GOLD if self.multiplier > 2 else C_WHITE
        mt = self.f_med.render(f"x{self.multiplier:.1f}", True, mult_col)
        surf.blit(mt, mt.get_rect(center=(W // 2, 22)))

        # Time
        tt = self.f_med.render(f"TIME: {self.survive_time:.1f}s", True, C_WHITE)
        surf.blit(tt, (W - tt.get_width() - 14, 8))

        # Drunk indicator
        if self.drunk_level > 0:
            label = ("🌀 ABSOLUTELY WRECKED" if self.drunk_level >= 8 else
                     "😵 VERY DRUNK"         if self.drunk_level >= 4 else
                     "🍺 TIPSY")
            dcol = C_RED if self.drunk_level >= 4 else C_GOLD
            dt = self.f_small.render(label, True, dcol)
            surf.blit(dt, (14, H - 30))

        # Input delay warning
        if self.drunk_level > 0 and self.input_queue:
            wt = self.f_tiny.render(f"⚠ {len(self.input_queue)} input(s) delayed", True, C_RED)
            surf.blit(wt, (14, H - 50))

        # Jump / duck state
        if self.is_jumping:
            jt = self.f_small.render("JUMP!", True, C_BLUE)
            surf.blit(jt, jt.get_rect(center=(W // 2, H - 42)))
        elif self.is_ducking:
            dt2 = self.f_small.render("DUCK!", True, C_GREEN)
            surf.blit(dt2, dt2.get_rect(center=(W // 2, H - 42)))

        # Controls reminder (fades after 5s)
        if self.survive_time < 5:
            alpha = int(255 * min(1.0, (5 - self.survive_time)))
            ct = self.f_tiny.render("← → LANES   ↑ JUMP   ↓ DUCK", True, C_DARK_GOLD)
            surf.blit(ct, ct.get_rect(center=(W // 2, H - 22)))

    # ─────────────────────────────────────────────────────────────────────────
    #  GAME OVER
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_gameover(self):
        surf = self.screen
        surf.fill((8, 3, 0))

        # Scanline texture
        for y in range(0, H, 3):
            pygame.draw.line(surf, (0, 0, 0), (0, y), (W, y))

        # Panel
        pw, ph = 460, 360
        px, py = W // 2 - pw // 2, H // 2 - ph // 2
        draw_round_rect(surf, C_PANEL, (px, py, pw, ph), 12,
                        border=2, border_color=C_DARK_GOLD)

        # Title
        go_t = self.f_huge.render("GAME OVER", True, C_RED)
        surf.blit(go_t, go_t.get_rect(center=(W // 2, py + 56)))
        sub  = self.f_small.render("YOU WERE CAUGHT", True, C_DARK_GOLD)
        surf.blit(sub, sub.get_rect(center=(W // 2, py + 88)))

        # Score
        final = int(self.base_score * self.multiplier)
        fs_t  = self.f_huge.render(f"{final:,}", True, C_WHITE)
        surf.blit(fs_t, fs_t.get_rect(center=(W // 2, py + 150)))
        fl_t  = self.f_small.render("FINAL SCORE", True, C_DARK_GOLD)
        surf.blit(fl_t, fl_t.get_rect(center=(W // 2, py + 178)))

        # Breakdown
        for j, line in enumerate([
            f"Base score:  {self.base_score}",
            f"Multiplier:  x{self.multiplier:.1f}",
            f"Survived:    {self.survive_time:.1f}s",
            f"Drunk level: {self.drunk_level}",
        ]):
            lt = self.f_small.render(line, True, C_WHITE)
            surf.blit(lt, lt.get_rect(center=(W // 2, py + 210 + j * 24)))

        # Rank
        rank, rcol = (
            ("LEGENDARY", C_GOLD)   if final > 1000 else
            ("RECKLESS",  C_RED)    if final > 500  else
            ("RISKY",     C_GOLD)   if final > 200  else
            ("CAUTIOUS",  C_BLUE)
        )
        rt = self.f_med.render(f"RANK:  {rank}", True, rcol)
        surf.blit(rt, rt.get_rect(center=(W // 2, py + 310)))

        # Restart
        flash = int(abs(math.sin(pygame.time.get_ticks() / 600)) * 200 + 55)
        rc_t  = self.f_med.render("PRESS ENTER / R TO RESTART", True, (flash, flash, flash // 2))
        surf.blit(rc_t, rc_t.get_rect(center=(W // 2, py + ph + 28)))


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    game = DerbyDash()
    game.run()
