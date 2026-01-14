# settings.py
from __future__ import annotations

# Window
WIDTH = 1280
HEIGHT = 720
FPS = 120
TITLE = "Survivor.io-style (pygame) - BrainBuff testbed"

# Colors
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

# World / camera
GRID_SPACING = 64
GRID_COLOR = (45, 45, 45)

# Player base stats
PLAYER_RADIUS = 50
PLAYER_BASE_SPEED = 260.0
PLAYER_BASE_MAX_HP = 100.0
PLAYER_IFRAMES = 0.55

# Enemy base stats
ENEMY_CONTACT_DPS = 22.0  # damage per second on contact

ENEMY_SPAWN_DISTANCE = 80.0  # spawn outside the visible screen by this much

# Scaling
DIFFICULTY_RAMP_PER_SEC = 0.015  # affects spawn rate and enemy stats over time

# EXP
ORB_RADIUS = 10
ORB_EXP_VALUE = 6
EXP_PICKUP_RADIUS = 42

# UI
UI_BAR_W = 320
UI_BAR_H = 18

# Weapons: Projectile
PROJ_BASE_DAMAGE = 18.0
PROJ_BASE_COOLDOWN = 0.38
PROJ_BASE_SPEED = 720.0
PROJ_BASE_LIFETIME = 1.2
PROJ_RADIUS = 8

# Weapons: Blades (orbiting)
BLADE_BASE_DAMAGE = 10.0
BLADE_BASE_RADIUS = 100.0
BLADE_BASE_ROT_SPEED = 3.6  # radians/sec
BLADE_BASE_COUNT = 2
BLADE_HIT_INTERVAL = 0.22  # per enemy hit cooldown (prevents insane DPS)
BLADE_SIZE = 20

# Weapons: Lightning (periodic strike)
LIGHTNING_BASE_DAMAGE = 32.0
LIGHTNING_BASE_COOLDOWN = 2.3
LIGHTNING_BASE_RADIUS = 72.0
LIGHTNING_STRIKE_COUNT = 1
LIGHTNING_TARGET_RANGE = 520.0

# Screen shake (bonus)
SHAKE_ON_HIT = True
SHAKE_STRENGTH = 9.0
SHAKE_DECAY = 22.0
