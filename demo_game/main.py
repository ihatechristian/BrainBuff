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
from sound_manager import SoundManager

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


def _scaled(v: int | float) -> int:
    return int(round(float(v) * float(S.UI_SCALE)))


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

        # Keep actual fullscreen size (used everywhere)
        self.sw, self.sh = self.screen.get_size()

        # HUD fonts (ALL driven by settings.py)
        self.ui_font_small = pygame.font.SysFont("consolas", _scaled(S.UI_FONT_SMALL))
        self.ui_font_med = pygame.font.SysFont("consolas", _scaled(S.UI_FONT_MEDIUM), bold=True)
        self.ui_font_big = pygame.font.SysFont("consolas", _scaled(S.UI_FONT_LARGE), bold=True)

        # Existing menu fonts (can stay as-is, not part of HUD requirement)
        self.font = pygame.font.SysFont("consolas", 20)
        self.font_big = pygame.font.SysFont("consolas", 44, bold=True)
        self.font_mid = pygame.font.SysFont("consolas", 28, bold=True)

        # ✅ Back button (top-left) settings
        self.back_btn_rect = pygame.Rect(18, 18, 190, 44)

        self.sound_manager = SoundManager()

        self.state = "start"  # start, playing, levelup, gameover
        self.reset_run()

    def reset_run(self):
        self.player = Player(Vector2(0, 0))
        self.weapons = WeaponSystem(self.sound_manager)
        self.upgrades = UpgradeManager(self)

        self.enemies: list = []
        self.orbs: list[ExpOrb] = []

        self.survival_time = 0.0
        self.difficulty = 0.0

        self.spawn_timer = 0.0
        self.base_spawn_interval = 0.65

        self.pending_choices = []

        # camera = top-left world coordinate for screen
        self.camera = Vector2(self.player.pos.x - self.sw / 2, self.player.pos.y - self.sh / 2)

        # screenshake
        self.shake = 0.0
        self.shake_offset = Vector2(0, 0)

        # overlay pause state
        self.overlay_paused = False

    # ✅ Exit game back to launcher
    def exit_to_launcher(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))

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

                # ✅ ESC always exits back to launcher
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

                # ✅ Click "Back to Launcher" on start screen
                if self.state == "start":
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.back_btn_rect.collidepoint(event.pos):
                            running = False

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
        mw = self.mouse_world_pos()
        v = mw - self.player.pos
        if v.length_squared() > 0:
            return v.normalize()
        return Vector2(1, 0)

    def update_camera(self, dt: float):
        target = Vector2(self.player.pos.x - self.sw / 2, self.player.pos.y - self.sh / 2)
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
        self.difficulty = self.survival_time * S.DIFFICULTY_RAMP_PER_SEC

        # Player movement
        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)

        # Weapons auto-fire
        self.weapons.update(dt, self.player, self.aim_dir_world(), self.mouse_world_pos(), self.enemies)

        # Update enemies
        for e in self.enemies:
            e.update(dt, self.player.pos)

        # Remove dead enemies → spawn EXP orbs
        for e in self.enemies[:]:
            if not e.alive:
                self.enemies.remove(e)
                self.player.kills += 1
                self.orbs.append(ExpOrb(e.pos, e.exp_value))

        # Enemy collision damage (continuous DPS)
        for e in self.enemies:
            if circle_hit(self.player.pos, self.player.radius, e.pos, e.radius):
                self.player.take_contact_damage(S.ENEMY_CONTACT_DPS * dt)
                
                if random.random() < 0.05:
                    self.sound_manager.play_immediate("player_hit", volume_override=0.5)
                
                if S.SHAKE_ON_HIT:
                    self.shake = max(self.shake, S.SHAKE_STRENGTH * 0.4)

        # Pick up orbs
        for orb in self.orbs[:]:
            if circle_hit(self.player.pos, S.EXP_PICKUP_RADIUS, orb.pos, orb.radius):
                leveled_up = self.player.add_exp(orb.value)
                self.orbs.remove(orb)
                
                if leveled_up:
                    self.sound_manager.play_immediate("level_up", volume_override=0.6)
                    
                    self.pending_choices = self.upgrades.roll_choices(3)
                    if self.pending_choices:
                        self.state = "levelup"

        # Spawn enemies
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            spawn_rate = self.base_spawn_interval / (1.0 + 0.5 * self.difficulty)
            self.spawn_timer = spawn_rate
            
            enemy = spawn_enemy_at_screen_edge(
                self.player.pos,
                self.camera,
                self.difficulty,
                self.sound_manager
            )
            self.enemies.append(enemy)

        self.update_camera(dt)

    def draw_grid(self, surf: pygame.Surface):
        surf.fill(S.BLACK)
        cam = self.camera + self.shake_offset

        # Draw grid lines
        for x in range(int(cam.x // S.GRID_SPACING) - 1, int((cam.x + self.sw) // S.GRID_SPACING) + 2):
            sx = x * S.GRID_SPACING - cam.x
            pygame.draw.line(surf, S.GRID_COLOR, (sx, 0), (sx, self.sh), 1)

        for y in range(int(cam.y // S.GRID_SPACING) - 1, int((cam.y + self.sh) // S.GRID_SPACING) + 2):
            sy = y * S.GRID_SPACING - cam.y
            pygame.draw.line(surf, S.GRID_COLOR, (0, sy), (self.sw, sy), 1)

    def _draw_ui_bar(
        self,
        surf: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        ratio: float,
        color: tuple,
        label: str,
    ):
        """
        Draws a rounded-corner HP/EXP bar + label.
        """
        # background
        bg = (40, 40, 40)
        pygame.draw.rect(surf, bg, (x, y, width, height), border_radius=_scaled(S.UI_BAR_RADIUS))

        # fill
        fill_w = max(0, int(width * ratio))
        if fill_w > 0:
            pygame.draw.rect(surf, color, (x, y, fill_w, height), border_radius=_scaled(S.UI_BAR_RADIUS))

        # border
        border = (90, 90, 90)
        pygame.draw.rect(surf, border, (x, y, width, height), 1, border_radius=_scaled(S.UI_BAR_RADIUS))

        # label
        txt = self.ui_font_small.render(label, True, S.UI_TEXT)
        txt_x = x + (width - txt.get_width()) // 2
        txt_y = y + (height - txt.get_height()) // 2
        surf.blit(txt, (txt_x, txt_y))

    def draw_ui(self, surf: pygame.Surface):
        """
        Draws HUD (HP, EXP, time, kills, level) using settings-driven layout.
        """
        x0 = _scaled(S.UI_MARGIN_X)
        y = _scaled(S.UI_MARGIN_Y)
        gap = _scaled(S.UI_ROW_GAP)
        bar_w = _scaled(S.UI_BAR_W)
        bar_h = _scaled(S.UI_BAR_H)

        # HP
        if S.SHOW_HP:
            hp_ratio = max(0.0, self.player.hp / max(1e-6, self.player.max_hp))
            label = f"HP: {int(self.player.hp)}/{int(self.player.max_hp)}"
            self._draw_ui_bar(
                surf,
                x0,
                y,
                bar_w,
                bar_h,
                hp_ratio,
                S.UI_HP,
                label,
            )
            y += bar_h + gap

        # Level (small text) + EXP bar
        if S.SHOW_LEVEL:
            lvl_txt = self.ui_font_med.render(f"Level: {self.player.level}", True, S.UI_TEXT)
            surf.blit(lvl_txt, (x0, y))
            y += lvl_txt.get_height() + gap

        if S.SHOW_EXP:
            exp_ratio = self.player.exp_ratio()
            label = f"EXP: {self.player.exp}/{self.player.exp_to_next}"
            self._draw_ui_bar(
                surf,
                x0,
                y,
                bar_w,
                bar_h,
                exp_ratio,
                S.UI_EXP,
                label,
            )
            y += bar_h + gap

        # Time
        if S.SHOW_TIMER:
            t = format_time(self.survival_time)
            txt = self.ui_font_med.render(f"Time: {t}", True, S.UI_TEXT)
            surf.blit(txt, (x0, y))
            y += txt.get_height() + gap

        # Kills
        if S.SHOW_KILLS:
            txt = self.ui_font_med.render(f"Kills: {self.player.kills}", True, S.UI_TEXT)
            surf.blit(txt, (x0, y))
            y += txt.get_height() + gap

        # Overlay pause indicator (center top-ish)
        if self.state == "playing" and self.overlay_paused:
            label = self.font_mid.render("PAUSED (Overlay)", True, S.WHITE)
            surf.blit(label, (self.sw / 2 - label.get_width() / 2, 90))

    # ✅ Draw back button (only on start screen)
    def draw_back_button(self, surf: pygame.Surface):
        mx, my = pygame.mouse.get_pos()
        hovered = self.back_btn_rect.collidepoint((mx, my))

        bg = (255, 255, 255, 60) if hovered else (255, 255, 255, 30)
        border = (255, 255, 255, 120) if hovered else (255, 255, 255, 80)

        btn_surf = pygame.Surface((self.back_btn_rect.w, self.back_btn_rect.h), pygame.SRCALPHA)
        btn_surf.fill((0, 0, 0, 0))
        pygame.draw.rect(btn_surf, bg, (0, 0, self.back_btn_rect.w, self.back_btn_rect.h), border_radius=12)
        pygame.draw.rect(btn_surf, border, (0, 0, self.back_btn_rect.w, self.back_btn_rect.h), width=2, border_radius=12)

        txt = self.font.render("← Back to Launcher", True, (235, 235, 235))
        btn_surf.blit(txt, (12, (self.back_btn_rect.h - txt.get_height()) // 2))

        surf.blit(btn_surf, (self.back_btn_rect.x, self.back_btn_rect.y))

    def draw_levelup_overlay(self, surf: pygame.Surface):
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surf.blit(overlay, (0, 0))

        title = self.font_big.render("LEVEL UP!", True, S.WHITE)
        surf.blit(title, (self.sw / 2 - title.get_width() / 2, 70))

        hint = self.font.render("Pick 1 upgrade: press 1 / 2 / 3", True, S.WHITE)
        surf.blit(hint, (self.sw / 2 - hint.get_width() / 2, 135))

        card_w = 310
        card_h = 170
        gap = 28
        start_x = (self.sw - (3 * card_w + 2 * gap)) / 2
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

        # ✅ Back button (start screen only)
        self.draw_back_button(surf)

        title = self.font_big.render("SURVIVOR CLONE", True, S.WHITE)
        surf.blit(title, (self.sw / 2 - title.get_width() / 2, 140))

        sub = self.font.render("WASD to move • Aim with mouse • Auto attacks", True, S.GRAY)
        surf.blit(sub, (self.sw / 2 - sub.get_width() / 2, 210))

        sub2 = self.font.render("Survive as long as possible • Space to start", True, S.GRAY)
        surf.blit(sub2, (self.sw / 2 - sub2.get_width() / 2, 240))

        info = self.font.render("Level-ups pause the game. Choose upgrades with 1/2/3.", True, S.GRAY)
        surf.blit(info, (self.sw / 2 - info.get_width() / 2, 290))

        tip = self.font.render("Tip: overlay can pause by writing overlay_pause.txt in project root.", True, (120, 120, 140))
        surf.blit(tip, (self.sw / 2 - tip.get_width() / 2, 330))

        esc = self.font.render("Press ESC anytime to return to Launcher", True, (120, 120, 140))
        surf.blit(esc, (self.sw / 2 - esc.get_width() / 2, 360))

    def draw_gameover(self, surf: pygame.Surface):
        surf.fill(S.BLACK)
        title = self.font_big.render("GAME OVER", True, S.RED)
        surf.blit(title, (self.sw / 2 - title.get_width() / 2, 150))

        stats = [
            f"Time Survived: {format_time(self.survival_time)}",
            f"Level Reached: {self.player.level}",
            f"Kills: {self.player.kills}",
        ]
        y = 240
        for s in stats:
            txt = self.font_mid.render(s, True, S.WHITE)
            surf.blit(txt, (self.sw / 2 - txt.get_width() / 2, y))
            y += 44

        hint = self.font.render("Press R to return to Start Screen", True, S.GRAY)
        surf.blit(hint, (self.sw / 2 - hint.get_width() / 2, 450))

        esc = self.font.render("Press ESC to return to Launcher", True, (120, 120, 140))
        surf.blit(esc, (self.sw / 2 - esc.get_width() / 2, 485))

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

    # Fullscreen borderless at current monitor resolution
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)

    # Keep settings module in sync for any other modules that use S.WIDTH/S.HEIGHT
    S.WIDTH, S.HEIGHT = screen.get_size()

    overlay_proc = start_overlay_process()

    try:
        Game(screen).run()
    finally:
        if overlay_proc is not None:
            overlay_proc.terminate()


if __name__ == "__main__":
    main()