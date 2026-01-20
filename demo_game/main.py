# main.py
from __future__ import annotations
import math
import random
import os
import ctypes

# Make pygame/SDL use physical pixels (fixes "small top-left" on Windows scaling)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Force window top-left (must be set before pygame.init)
os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"

import pygame
from pygame import Vector2
import sys
import subprocess
from pathlib import Path

import settings as S
from player import Player
from enemy import spawn_enemy_at_screen_edge
from weapons import WeaponSystem
from upgrades import UpgradeManager

# ============================================================
# Overlay pause bridge (ABSOLUTE PATH to project root)
# Project structure:
#   BRAINBUFF/
#     overlay_trigger.py
#     demo_game/
#       main.py   <-- this file
# Pause flag must be at:
#   BRAINBUFF/overlay_pause.txt
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # -> BRAINBUFF/
OVERLAY_PAUSE_FILE = PROJECT_ROOT / "overlay_pause.txt"


def overlay_requests_pause() -> bool:
    """
    Overlay writes PROJECT_ROOT/overlay_pause.txt:
      '1' => pause gameplay
      '0' or missing => continue
    """
    try:
        return OVERLAY_PAUSE_FILE.read_text(encoding="utf-8").strip() == "1"
    except FileNotFoundError:
        return False
    except Exception:
        # If overlay is writing while we read, don't pause this frame.
        return False


class ExpOrb:
    def __init__(self, pos: Vector2, value: int):
        self.pos = Vector2(pos)
        self.value = value
        self.radius = S.ORB_RADIUS

    def draw(self, surf: pygame.Surface, camera: Vector2):
        p = self.pos - camera
        pygame.draw.circle(surf, S.GREEN, (int(p.x), int(p.y)), self.radius)
        pygame.draw.circle(surf, (30, 30, 30), (int(p.x), int(p.y)), self.radius, 1)


def circle_hit(a_pos: Vector2, a_r: float, b_pos: Vector2, b_r: float) -> bool:
    return (a_pos - b_pos).length_squared() <= (a_r + b_r) ** 2


def format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    mm = s // 60
    ss = s % 60
    return f"{mm:02d}:{ss:02d}"


class Game:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("consolas", 20)
        self.font_big = pygame.font.SysFont("consolas", 44, bold=True)
        self.font_mid = pygame.font.SysFont("consolas", 28, bold=True)

        self.state = "start"  # start, playing, levelup, gameover
        self.reset_run()

    def reset_run(self):
        self.player = Player(Vector2(0, 0))
        self.weapons = WeaponSystem()
        self.upgrades = UpgradeManager(self)

        self.enemies: list = []
        self.orbs: list[ExpOrb] = []

        self.survival_time = 0.0
        self.difficulty = 0.0

        self.spawn_timer = 0.0
        self.base_spawn_interval = 0.65

        self.pending_choices = []

        # camera = top-left world coordinate for screen
        self.camera = Vector2(self.player.pos.x - S.WIDTH / 2, self.player.pos.y - S.HEIGHT / 2)

        # screenshake
        self.shake = 0.0
        self.shake_offset = Vector2(0, 0)

        # overlay pause state
        self.overlay_paused = False

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(S.FPS) / 1000.0
            dt = min(dt, 1 / 30)  # clamp for stability on hitches

            # Read overlay pause flag once per frame
            self.overlay_paused = overlay_requests_pause()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.state == "start":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        self.reset_run()
                        self.state = "playing"

                elif self.state == "gameover":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                        self.state = "start"

                elif self.state == "levelup":
                    if event.type == pygame.KEYDOWN:
                        # keys 1/2/3 choose upgrade
                        if event.key in (pygame.K_1, pygame.K_KP1) and len(self.pending_choices) >= 1:
                            self.upgrades.take(self.pending_choices[0])
                            self.state = "playing"
                        if event.key in (pygame.K_2, pygame.K_KP2) and len(self.pending_choices) >= 2:
                            self.upgrades.take(self.pending_choices[1])
                            self.state = "playing"
                        if event.key in (pygame.K_3, pygame.K_KP3) and len(self.pending_choices) >= 3:
                            self.upgrades.take(self.pending_choices[2])
                            self.state = "playing"

            # ✅ Only advance gameplay if playing AND overlay isn't requesting pause
            if self.state == "playing":
                if not self.overlay_paused:
                    self.update_playing(dt)
                    if self.player.is_dead():
                        self.state = "gameover"
                # else: do nothing -> fully paused, but still renders

            # draw
            self.draw()

        pygame.quit()

    def mouse_world_pos(self) -> Vector2:
        mx, my = pygame.mouse.get_pos()
        return Vector2(mx, my) + self.camera  # camera is top-left world

    def aim_dir_world(self) -> Vector2:
        # player -> mouse in world space
        mw = self.mouse_world_pos()
        v = mw - self.player.pos
        if v.length_squared() > 0:
            return v.normalize()
        return Vector2(1, 0)

    def update_camera(self, dt: float):
        target = Vector2(self.player.pos.x - S.WIDTH / 2, self.player.pos.y - S.HEIGHT / 2)
        # smooth camera
        self.camera += (target - self.camera) * min(1.0, 8.5 * dt)

        # screenshake
        if S.SHAKE_ON_HIT:
            if self.shake > 0:
                self.shake = max(0.0, self.shake - S.SHAKE_DECAY * dt)
                ang = random.random() * math.tau
                mag = self.shake
                self.shake_offset = Vector2(math.cos(ang), math.sin(ang)) * mag
            else:
                self.shake_offset = Vector2(0, 0)

    def update_playing(self, dt: float):
        self.survival_time += dt
        self.difficulty += S.DIFFICULTY_RAMP_PER_SEC * dt

        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)

        # camera
        self.update_camera(dt)

        # Spawn scaling
        spawn_interval = max(0.12, self.base_spawn_interval * (1.0 - 0.55 * self.difficulty))
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            # spawn count ramps
            extra = int(self.difficulty * 0.9)
            spawn_count = 1 + min(5, extra // 2)
            for _ in range(spawn_count):
                self.enemies.append(spawn_enemy_at_screen_edge(self.player.pos, self.camera, self.difficulty))
            self.spawn_timer = spawn_interval

        # Update enemies
        for e in self.enemies:
            e.update(dt, self.player.pos)

        # Contact damage
        for e in self.enemies:
            if circle_hit(self.player.pos, self.player.radius, e.pos, e.radius):
                took = self.player.take_damage(S.ENEMY_CONTACT_DPS * dt)
                if took and S.SHAKE_ON_HIT:
                    self.shake = max(self.shake, S.SHAKE_STRENGTH)

        # Weapons update
        aim_dir = self.aim_dir_world()
        mw = self.mouse_world_pos()
        self.weapons.update(dt, self.player, aim_dir, mw, self.enemies)

        # Cleanup dead enemies, spawn EXP orbs
        alive_enemies = []
        for e in self.enemies:
            if e.alive:
                alive_enemies.append(e)
            else:
                self.player.kills += 1
                drops = 1 if random.random() < 0.75 else 2
                for _ in range(drops):
                    jitter = Vector2(random.uniform(-10, 10), random.uniform(-10, 10))
                    self.orbs.append(ExpOrb(e.pos + jitter, e.exp_value))
        self.enemies = alive_enemies

        # EXP pickup (magnet-ish when close)
        picked = []
        for orb in self.orbs:
            d = self.player.pos.distance_to(orb.pos)
            if d <= S.EXP_PICKUP_RADIUS:
                if d > 1:
                    orb.pos += (self.player.pos - orb.pos).normalize() * (520 * dt)
            if d <= (self.player.radius + orb.radius + 4):
                picked.append(orb)

        for orb in picked:
            self.orbs.remove(orb)
            leveled = self.player.add_exp(orb.value)
            if leveled:
                # Pause gameplay completely for selection
                self.pending_choices = self.upgrades.roll_choices(3)
                self.state = "levelup"
                break

    def draw_grid(self, surf: pygame.Surface):
        cam = self.camera + self.shake_offset

        left = cam.x
        top = cam.y
        right = cam.x + S.WIDTH
        bottom = cam.y + S.HEIGHT

        gx0 = int(math.floor(left / S.GRID_SPACING) * S.GRID_SPACING)
        gy0 = int(math.floor(top / S.GRID_SPACING) * S.GRID_SPACING)

        surf.fill(S.BLACK)

        x = gx0
        while x < right:
            sx = int(x - cam.x)
            pygame.draw.line(surf, S.GRID_COLOR, (sx, 0), (sx, S.HEIGHT), 1)
            x += S.GRID_SPACING

        y = gy0
        while y < bottom:
            sy = int(y - cam.y)
            pygame.draw.line(surf, S.GRID_COLOR, (0, sy), (S.WIDTH, sy), 1)
            y += S.GRID_SPACING

    def draw_ui(self, surf: pygame.Surface):
        # HP bar
        hp_ratio = max(0.0, self.player.hp / max(1e-6, self.player.max_hp))
        pygame.draw.rect(surf, (30, 30, 30), (18, 16, S.UI_BAR_W, S.UI_BAR_H))
        pygame.draw.rect(surf, S.RED, (18, 16, int(S.UI_BAR_W * hp_ratio), S.UI_BAR_H))
        surf.blit(self.font.render(f"HP {int(self.player.hp)}/{int(self.player.max_hp)}", True, S.WHITE), (24, 14))

        # EXP bar
        exp_ratio = self.player.exp_ratio()
        y = 44
        pygame.draw.rect(surf, (30, 30, 30), (18, y, S.UI_BAR_W, S.UI_BAR_H))
        pygame.draw.rect(surf, S.GREEN, (18, y, int(S.UI_BAR_W * exp_ratio), S.UI_BAR_H))
        surf.blit(self.font.render(f"LV {self.player.level}  EXP {self.player.exp}/{self.player.exp_to_next}", True, S.WHITE), (24, y - 2))

        # Timer / kills
        t = format_time(self.survival_time)
        surf.blit(self.font.render(f"Time: {t}", True, S.WHITE), (S.WIDTH - 160, 16))
        surf.blit(self.font.render(f"Kills: {self.player.kills}", True, S.WHITE), (S.WIDTH - 160, 42))

        # Overlay pause indicator
        if self.state == "playing" and self.overlay_paused:
            label = self.font_mid.render("PAUSED (Overlay)", True, S.WHITE)
            surf.blit(label, (S.WIDTH / 2 - label.get_width() / 2, 90))

    def draw_levelup_overlay(self, surf: pygame.Surface):
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surf.blit(overlay, (0, 0))

        title = self.font_big.render("LEVEL UP!", True, S.WHITE)
        surf.blit(title, (S.WIDTH / 2 - title.get_width() / 2, 70))

        hint = self.font.render("Pick 1 upgrade: press 1 / 2 / 3", True, S.WHITE)
        surf.blit(hint, (S.WIDTH / 2 - hint.get_width() / 2, 135))

        card_w = 310
        card_h = 170
        gap = 28
        start_x = (S.WIDTH - (3 * card_w + 2 * gap)) / 2
        y = 220

        for i, u in enumerate(self.pending_choices):
            x = start_x + i * (card_w + gap)
            pygame.draw.rect(surf, (20, 20, 25), (x, y, card_w, card_h), border_radius=14)
            pygame.draw.rect(surf, (90, 90, 110), (x, y, card_w, card_h), 2, border_radius=14)

            idx = self.font_mid.render(str(i + 1), True, S.YELLOW)
            surf.blit(idx, (x + 14, y + 12))

            name = self.font_mid.render(u.name, True, S.WHITE)
            surf.blit(name, (x + 48, y + 10))

            lv_now = self.upgrades.level_of(u.key)
            lv_text = self.font.render(f"Level: {lv_now}/{u.max_level}", True, S.GRAY)
            surf.blit(lv_text, (x + 18, y + 54))

            desc = self.wrap_text(u.desc, self.font, card_w - 36)
            yy = y + 84
            for line in desc:
                surf.blit(self.font.render(line, True, S.WHITE), (x + 18, yy))
                yy += 22

    def wrap_text(self, text: str, font: pygame.font.Font, max_w: int):
        words = text.split(" ")
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if font.size(test)[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_start(self, surf: pygame.Surface):
        surf.fill(S.BLACK)
        title = self.font_big.render("SURVIVOR CLONE", True, S.WHITE)
        surf.blit(title, (S.WIDTH / 2 - title.get_width() / 2, 140))

        sub = self.font.render("WASD to move • Aim with mouse • Auto attacks", True, S.GRAY)
        surf.blit(sub, (S.WIDTH / 2 - sub.get_width() / 2, 210))

        sub2 = self.font.render("Survive as long as possible • Space to start", True, S.GRAY)
        surf.blit(sub2, (S.WIDTH / 2 - sub2.get_width() / 2, 240))

        info = self.font.render("Level-ups pause the game. Choose upgrades with 1/2/3.", True, S.GRAY)
        surf.blit(info, (S.WIDTH / 2 - info.get_width() / 2, 290))

        tip = self.font.render("Tip: your overlay can pause by writing overlay_pause.txt in project root.", True, (120, 120, 140))
        surf.blit(tip, (S.WIDTH / 2 - tip.get_width() / 2, 330))

    def draw_gameover(self, surf: pygame.Surface):
        surf.fill(S.BLACK)
        title = self.font_big.render("GAME OVER", True, S.RED)
        surf.blit(title, (S.WIDTH / 2 - title.get_width() / 2, 150))

        stats = [
            f"Time Survived: {format_time(self.survival_time)}",
            f"Level Reached: {self.player.level}",
            f"Kills: {self.player.kills}",
        ]
        y = 240
        for s in stats:
            txt = self.font_mid.render(s, True, S.WHITE)
            surf.blit(txt, (S.WIDTH / 2 - txt.get_width() / 2, y))
            y += 44

        hint = self.font.render("Press R to return to Start Screen", True, S.GRAY)
        surf.blit(hint, (S.WIDTH / 2 - hint.get_width() / 2, 450))

    def draw(self):
        if self.state == "start":
            self.draw_start(self.screen)
            pygame.display.flip()
            return

        if self.state == "gameover":
            self.draw_gameover(self.screen)
            pygame.display.flip()
            return

        self.draw_grid(self.screen)

        cam = self.camera + self.shake_offset

        for orb in self.orbs:
            orb.draw(self.screen, cam)

        for e in self.enemies:
            e.draw(self.screen, cam)

        self.player.draw(self.screen, cam)
        self.weapons.draw(self.screen, cam, self.player, self.aim_dir_world())

        self.draw_ui(self.screen)

        if self.state == "levelup":
            self.draw_levelup_overlay(self.screen)

        pygame.display.flip()


def start_overlay_process():
    # overlay_trigger.py is in PROJECT_ROOT (BRAINBUFF/)
    overlay_script = PROJECT_ROOT / "overlay_trigger.py"

    if not overlay_script.exists():
        print("overlay_trigger.py not found at:", overlay_script)
        return None

    try:
        proc = subprocess.Popen(
            [sys.executable, str(overlay_script)],
            cwd=str(PROJECT_ROOT),
        )
        print("BrainBuff overlay started:", overlay_script)
        print("Game reading pause flag at:", OVERLAY_PAUSE_FILE)
        return proc
    except Exception as e:
        print("Failed to start overlay:", e)
        return None


def main():
    pygame.init()
    pygame.display.set_caption(S.TITLE)

    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    S.WIDTH, S.HEIGHT = screen.get_size()

    overlay_proc = start_overlay_process()  # <-- starts overlay_trigger.py

    try:
        Game(screen).run()
    finally:
        if overlay_proc is not None:
            overlay_proc.terminate()


if __name__ == "__main__":
    main()