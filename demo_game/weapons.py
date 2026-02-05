# weapons.py
from __future__ import annotations
import math

import pygame
from pygame import Vector2
import settings as S


def circle_hit(a_pos: Vector2, a_r: float, b_pos: Vector2, b_r: float) -> bool:
    return (a_pos - b_pos).length_squared() <= (a_r + b_r) ** 2


class Projectile:
    def __init__(self, pos: Vector2, vel: Vector2, damage: float, lifetime: float):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.damage = damage
        self.life = lifetime
        self.alive = True
        self.radius = S.PROJ_RADIUS

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf: pygame.Surface, camera: Vector2):
        p = self.pos - camera
        pygame.draw.circle(surf, S.YELLOW, (int(p.x), int(p.y)), self.radius)


class ProjectileWeapon:
    """
    Auto-shoots toward mouse direction (world-space).
    Supports projectile_count (spread) if you keep that upgrade.
    """
    def __init__(self, sound_manager=None):
        self.level = 1
        self.damage = S.PROJ_BASE_DAMAGE
        self.cooldown = S.PROJ_BASE_COOLDOWN
        self.projectile_speed = S.PROJ_BASE_SPEED
        self.projectile_count = 2
        self.projectile_lifetime = S.PROJ_BASE_LIFETIME

        self.timer = 0.0
        self.projectiles: list[Projectile] = []
        
        # 🔊 Sound manager reference
        self.sound_manager = sound_manager

    def update(self, dt: float, player_pos: Vector2, aim_dir: Vector2, enemies: list):
        # Update projectiles + collision
        for p in self.projectiles:
            p.update(dt)
            for e in enemies:
                if circle_hit(p.pos, p.radius, e.pos, e.radius):
                    e.take_damage(p.damage)
                    p.alive = False
                    break
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Fire rate timer
        self.timer -= dt
        if self.timer > 0:
            return

        # Aim direction (fallback to right if zero)
        dir_vec = Vector2(aim_dir)
        if dir_vec.length_squared() > 1e-6:
            dir_vec = dir_vec.normalize()
        else:
            dir_vec = Vector2(1, 0)

        # Fire a spread if multiple projectiles
        n = max(1, int(self.projectile_count))
        spread = 0.20  # radians total-ish feel
        for i in range(n):
            if n == 1:
                ang = 0.0
            else:
                t = (i / (n - 1)) * 2 - 1  # -1..1
                ang = t * spread

            # rotate dir_vec by ang
            c = math.cos(ang)
            s = math.sin(ang)
            d = Vector2(dir_vec.x * c - dir_vec.y * s, dir_vec.x * s + dir_vec.y * c)

            vel = d * self.projectile_speed
            self.projectiles.append(
                Projectile(player_pos, vel, self.damage, self.projectile_lifetime)
            )

        # 🔊 Play shoot sound
        if self.sound_manager:
            self.sound_manager.play("shoot", volume_override=0.3)

        self.timer = self.cooldown

    def draw(self, surf: pygame.Surface, camera: Vector2, player_pos: Vector2, aim_dir: Vector2):
        # draw weapon "barrel" indicator
        p = player_pos - camera
        dir_vec = Vector2(aim_dir)
        if dir_vec.length_squared() > 1e-6:
            dir_vec = dir_vec.normalize()
        else:
            dir_vec = Vector2(1, 0)

        tip = p + dir_vec * 22
        pygame.draw.line(surf, S.YELLOW, (int(p.x), int(p.y)), (int(tip.x), int(tip.y)), 3)

        for proj in self.projectiles:
            proj.draw(surf, camera)


class WeaponSystem:
    """
    Projectile-only weapon system (no blades/swords, no lightning).
    """
    def __init__(self, sound_manager=None):
        self.projectile = ProjectileWeapon(sound_manager)

    def update(self, dt: float, player, aim_dir: Vector2, mouse_world: Vector2, enemies: list):
        # Only shooting
        self.projectile.update(dt, player.pos, aim_dir, enemies)

    def draw(self, surf: pygame.Surface, camera: Vector2, player, aim_dir: Vector2):
        # Only draw projectile weapon + bullets
        self.projectile.draw(surf, camera, player.pos, aim_dir)

    # Upgrade hooks (only affect projectile now)
    def apply_damage_multiplier(self, mult: float):
        self.projectile.damage *= mult

    def apply_attack_speed_multiplier(self, mult: float):
        # lower cooldown => faster shooting
        self.projectile.cooldown = max(0.07, self.projectile.cooldown / mult)