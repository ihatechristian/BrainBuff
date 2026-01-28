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
PURPLE = (190, 120, 240)
ORANGE = (245, 160, 80)

# UI specific colors (cleaner HUD look)
UI_BG_DARK = (24, 24, 28)
UI_BG_LIGHT = (40, 40, 48)
UI_TEXT = (235, 235, 235)
UI_MUTED = (160, 160, 170)

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
PLAYER_IFRAMES = 0.55

# ============================================================
# ENEMY BASE STATS
# ============================================================
ENEMY_CONTACT_DPS = 22.0  # damage per second on contact
ENEMY_SPAWN_DISTANCE = 80.0  # spawn outside the visible screen by this much

# ============================================================
# DIFFICULTY SCALING
# ============================================================
DIFFICULTY_RAMP_PER_SEC = 0.015  # affects spawn rate and enemy stats over time

# ============================================================
# EXP / ORBS
# ============================================================
ORB_RADIUS = 10
ORB_EXP_VALUE = 6
EXP_PICKUP_RADIUS = 42

# ============================================================
# UI / HUD (BIGGER + TOP-LEFT STACK FRIENDLY)
# ============================================================

# Global HUD scaling
# 1.0 = original size, 1.2 = recommended for 1080p,
# 1.35+ = very large (demo/stream)
UI_SCALE = 1.25

# Top-left anchor spacing
UI_MARGIN_X = 20
UI_MARGIN_Y = 20
UI_ROW_GAP = 12  # spacing between HUD rows

# Bars
UI_BAR_W = 340  # wider than before
UI_BAR_H = 20   # slightly taller
UI_BAR_RADIUS = 6  # for rounded rects (optional if you implement)

# Font sizes (base sizes BEFORE scaling)
UI_FONT_SMALL = 16
UI_FONT_MEDIUM = 20
UI_FONT_LARGE = 28

# Show/hide HUD elements
SHOW_HP = True
SHOW_EXP = True
SHOW_LEVEL = True
SHOW_TIMER = True
SHOW_KILLS = True

# ============================================================
# WEAPONS: PROJECTILE
# ============================================================
PROJ_BASE_DAMAGE = 18.0
PROJ_BASE_COOLDOWN = 0.38
PROJ_BASE_SPEED = 720.0
PROJ_BASE_LIFETIME = 1.2
PROJ_RADIUS = 8

# ============================================================
# WEAPONS: BLADES (ORBITING)
# ============================================================
BLADE_BASE_DAMAGE = 10.0
BLADE_BASE_RADIUS = 100.0
BLADE_BASE_ROT_SPEED = 3.6  # radians/sec
BLADE_BASE_COUNT = 2
BLADE_HIT_INTERVAL = 0.22  # per enemy hit cooldown (prevents insane DPS)
BLADE_SIZE = 20

# ============================================================
# WEAPONS: LIGHTNING (PERIODIC STRIKE)
# ============================================================
LIGHTNING_BASE_DAMAGE = 32.0
LIGHTNING_BASE_COOLDOWN = 2.3
LIGHTNING_BASE_RADIUS = 72.0
LIGHTNING_STRIKE_COUNT = 1
LIGHTNING_TARGET_RANGE = 520.0

# ============================================================
# SCREEN SHAKE (BONUS)
# ============================================================
SHAKE_ON_HIT = True
SHAKE_STRENGTH = 9.0
SHAKE_DECAY = 22.0
