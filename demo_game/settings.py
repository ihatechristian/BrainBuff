# settings.py
from __future__ import annotations

# ============================================================
# WINDOW
# ============================================================
WIDTH = 1280
HEIGHT = 720
FPS = 120
TITLE = "Survivor.io-style (pygame) - BrainBuff testbed"

# ============================================================
# COLORS
# ============================================================
WHITE = (240, 240, 240)
BLACK = (20, 20, 20)
GRAY = (110, 110, 110)
DARK_GRAY = (40, 40, 40)

RED = (220, 70, 70)
GREEN = (80, 220, 110)
BLUE = (80, 150, 240)
YELLOW = (240, 220, 80)
CYAN = (80, 220, 220)

# UI specific colors (HUD)
UI_BG_DARK = (24, 24, 28)
UI_BG_LIGHT = (40, 40, 48)
UI_TEXT = (235, 235, 235)

UI_HP = RED
UI_EXP = GREEN

# ============================================================
# WORLD / CAMERA
# ============================================================
GRID_SPACING = 64
GRID_COLOR = (45, 45, 45)

# ============================================================
# PLAYER BASE STATS
# ============================================================
PLAYER_RADIUS = 50
PLAYER_BASE_SPEED = 260.0
PLAYER_BASE_MAX_HP = 100.0
PLAYER_IFRAMES = 0.15

# ============================================================
# ENEMY
# ============================================================
ENEMY_SPAWN_DISTANCE = 80.0  # spawn outside the visible screen by this much
ENEMY_CONTACT_DPS = 1.0  # damage per second when touching player


# ============================================================
# DIFFICULTY SCALING
# ============================================================
DIFFICULTY_RAMP_PER_SEC = 0.015  # affects spawn rate and enemy stats over time

# ============================================================
# EXP / ORBS
# ============================================================
ORB_RADIUS = 10
EXP_PICKUP_RADIUS = 42

# ============================================================
# UI / HUD
# ============================================================
UI_SCALE = 1.25
UI_MARGIN_X = 20
UI_MARGIN_Y = 20
UI_ROW_GAP = 12

UI_BAR_W = 340
UI_BAR_H = 20
UI_BAR_RADIUS = 6

UI_FONT_SMALL = 16
UI_FONT_MEDIUM = 20
UI_FONT_LARGE = 28

SHOW_HP = True
SHOW_EXP = True
SHOW_LEVEL = True
SHOW_TIMER = True
SHOW_KILLS = True

# ============================================================
# WEAPONS: PROJECTILE (ONLY WEAPON USED)
# ============================================================
PROJ_BASE_DAMAGE = 18.0
PROJ_BASE_COOLDOWN = 0.38
PROJ_BASE_SPEED = 720.0
PROJ_BASE_LIFETIME = 1.2
PROJ_RADIUS = 8

# ============================================================
# SCREEN SHAKE
# ============================================================
SHAKE_ON_HIT = True
SHAKE_STRENGTH = 9.0
SHAKE_DECAY = 22.0
