# enemy.py
from __future__ import annotations
import random
import pygame
from pygame import Vector2
import settings as S


class Enemy:
    def __init__(self, pos: Vector2, kind: str, difficulty: float):
        self.pos = Vector2(pos)
        self.kind = kind

        # Base stats per type
        if kind == "runner":
            base_hp = 34
            base_speed = 185
            self.color = (240, 120, 120)
            self.radius = 13
            self.exp_value = 8
        else:  # "brute" / normal
            base_hp = 58
            base_speed = 125
            self.color = (240, 180, 90)
            self.radius = 16
            self.exp_value = 10

        # Scale with difficulty (time-based ramp)
        # difficulty ~ increases slowly; we scale hp & speed modestly
        self.max_hp = base_hp * (1.0 + 0.65 * difficulty)
        self.hp = self.max_hp
        self.speed = base_speed * (1.0 + 0.35 * difficulty)

        self.alive = True

    def take_damage(self, dmg: float) -> bool:
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def update(self, dt: float, player_pos: Vector2):
        to_player = (player_pos - self.pos)
        if to_player.length_squared() > 0:
            dir_vec = to_player.normalize()
        else:
            dir_vec = Vector2(1, 0)
        self.pos += dir_vec * self.speed * dt

    def draw(self, surf: pygame.Surface, camera: Vector2):
        p = self.pos - camera
        pygame.draw.circle(surf, self.color, (int(p.x), int(p.y)), self.radius)

        # HP mini-bar
        w = 26
        h = 4
        ratio = max(0.0, self.hp / max(1e-6, self.max_hp))
        x = int(p.x - w / 2)
        y = int(p.y - self.radius - 10)
        pygame.draw.rect(surf, (30, 30, 30), (x, y, w, h))
        pygame.draw.rect(surf, (80, 220, 110), (x, y, int(w * ratio), h))


def spawn_enemy_at_screen_edge(player_pos: Vector2, camera: Vector2, difficulty: float) -> Enemy:
    """
    Spawn outside visible screen edges in WORLD space.
    camera is top-left world coordinate of screen.
    """
    # Choose type (more runners over time)
    runner_chance = min(0.55, 0.25 + 0.18 * difficulty)
    kind = "runner" if random.random() < runner_chance else "brute"

    left = camera.x - S.ENEMY_SPAWN_DISTANCE
    right = camera.x + S.WIDTH + S.ENEMY_SPAWN_DISTANCE
    top = camera.y - S.ENEMY_SPAWN_DISTANCE
    bottom = camera.y + S.HEIGHT + S.ENEMY_SPAWN_DISTANCE

    side = random.choice(["l", "r", "t", "b"])
    if side == "l":
        pos = Vector2(left, random.uniform(camera.y, camera.y + S.HEIGHT))
    elif side == "r":
        pos = Vector2(right, random.uniform(camera.y, camera.y + S.HEIGHT))
    elif side == "t":
        pos = Vector2(random.uniform(camera.x, camera.x + S.WIDTH), top)
    else:
        pos = Vector2(random.uniform(camera.x, camera.x + S.WIDTH), bottom)

    return Enemy(pos, kind, difficulty)
