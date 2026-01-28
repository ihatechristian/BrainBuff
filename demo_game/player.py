# player.py
from __future__ import annotations
import math
from pathlib import Path

import pygame
from pygame import Vector2
import settings as S


class Player:
    def __init__(self, pos: Vector2):
        self.pos = Vector2(pos)
        self.vel = Vector2(0, 0)

        self.radius = S.PLAYER_RADIUS

        # Stats (upgradeable)
        self.base_speed = S.PLAYER_BASE_SPEED
        self.move_speed_mult = 1.0

        self.max_hp = S.PLAYER_BASE_MAX_HP
        self.hp = self.max_hp

        self.iframes = 0.0

        # EXP / leveling
        self.level = 1
        self.exp = 0
        self.exp_to_next = self._exp_needed_for(self.level)

        # Combat meta-stats (upgrades impact weapons directly too)
        self.damage_mult = 1.0
        self.attack_speed_mult = 1.0  # higher means faster attacks

        # Kills
        self.kills = 0

        # =========================
        # Sprite (player.png)
        # =========================
        self.sprite = None
        try:
            project_root = Path(__file__).resolve().parents[1]  # -> BRAINBUFF/
            img_path = project_root / "images" / "player.png"
            img = pygame.image.load(str(img_path)).convert_alpha()
            size = int(self.radius * 2.5)
            img = pygame.transform.smoothscale(img, (size, size))
            self.sprite = img
        except Exception as e:
            print("Player sprite load failed (fallback to circle):", e)

    def _exp_needed_for(self, level: int) -> int:
        return int(45 + (level - 1) * 18 + (level - 1) ** 1.25 * 10)

    def add_exp(self, amount: int) -> bool:
        self.exp += amount
        if self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            self.exp_to_next = self._exp_needed_for(self.level)
            return True
        return False

    def heal(self, amount: float):
        self.hp = min(self.max_hp, self.hp + amount)

    def take_damage(self, dmg: float):
        """Hit-based damage (uses i-frames)."""
        if self.iframes > 0:
            return False
        self.hp -= dmg
        self.iframes = S.PLAYER_IFRAMES
        return True

    def take_contact_damage(self, dmg: float):
        """TRUE DPS damage (ignores i-frames)."""
        self.hp -= dmg

    def is_dead(self) -> bool:
        return self.hp <= 0

    def speed(self) -> float:
        return self.base_speed * self.move_speed_mult

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper):
        # i-frames countdown
        if self.iframes > 0:
            self.iframes = max(0.0, self.iframes - dt)

        move = Vector2(0, 0)
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move.x += 1

        if move.length_squared() > 0:
            move = move.normalize()

        self.vel = move * self.speed()
        self.pos += self.vel * dt

    def draw(self, surf: pygame.Surface, camera: Vector2):
        screen_pos = self.pos - camera

        # blink during i-frames
        blink = (self.iframes > 0 and int(pygame.time.get_ticks() / 80) % 2 == 0)

        # Aim direction based on mouse (screen → world)
        mx, my = pygame.mouse.get_pos()
        mouse_world = Vector2(mx, my) + camera
        aim = mouse_world - self.pos
        if aim.length_squared() > 0:
            aim = aim.normalize()
        else:
            aim = Vector2(1, 0)

        if self.sprite is not None:
            angle_deg = -math.degrees(math.atan2(aim.y, aim.x))
            rotated = pygame.transform.rotate(self.sprite, angle_deg)
            rect = rotated.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))

            if blink:
                tmp = rotated.copy()
                tmp.set_alpha(110)
                surf.blit(tmp, rect)
            else:
                surf.blit(rotated, rect)
        else:
            color = S.CYAN if not blink else S.WHITE
            pygame.draw.circle(surf, color, (int(screen_pos.x), int(screen_pos.y)), self.radius)

        # tiny center dot
        pygame.draw.circle(surf, (10, 10, 10), (int(screen_pos.x), int(screen_pos.y)), 3)

    def exp_ratio(self) -> float:
        return self.exp / max(1, self.exp_to_next)
