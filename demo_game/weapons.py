# weapons.py
from __future__ import annotations
import math
import random
import pygame
from pygame import Vector2
import settings as S


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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
    Auto-shoots toward mouse direction (world-space) by default.
    Can optionally snap toward nearest enemy if aim vector is tiny.
    """
    def __init__(self):
        self.level = 1
        self.damage = S.PROJ_BASE_DAMAGE
        self.cooldown = S.PROJ_BASE_COOLDOWN
        self.projectile_speed = S.PROJ_BASE_SPEED
        self.projectile_count = 1
        self.projectile_lifetime = S.PROJ_BASE_LIFETIME

        self.timer = 0.0
        self.projectiles: list[Projectile] = []

    def update(self, dt: float, player_pos: Vector2, aim_dir: Vector2, enemies: list):
        # Update projectiles
        for p in self.projectiles:
            p.update(dt)
        self.projectiles = [p for p in self.projectiles if p.alive]

        self.timer -= dt
        if self.timer > 0:
            return

        # Determine aim direction
        dir_vec = Vector2(aim_dir)
        if dir_vec.length_squared() < 1e-6:
            # fallback: nearest enemy
            nearest = None
            best = 1e18
            for e in enemies:
                d2 = (e.pos - player_pos).length_squared()
                if d2 < best:
                    best = d2
                    nearest = e
            if nearest is not None and best > 0:
                dir_vec = (nearest.pos - player_pos).normalize()
            else:
                dir_vec = Vector2(1, 0)
        else:
            dir_vec = dir_vec.normalize()

        # Fire a spread if multiple projectiles
        n = self.projectile_count
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
            self.projectiles.append(Projectile(player_pos, vel, self.damage, self.projectile_lifetime))

        self.timer = self.cooldown

    def draw(self, surf: pygame.Surface, camera: Vector2, player_pos: Vector2, aim_dir: Vector2):
        # draw weapon "barrel" indicator
        p = player_pos - camera
        dir_vec = Vector2(aim_dir)
        if dir_vec.length_squared() > 0:
            dir_vec = dir_vec.normalize()
        else:
            dir_vec = Vector2(1, 0)
        tip = p + dir_vec * 22
        pygame.draw.line(surf, S.YELLOW, (int(p.x), int(p.y)), (int(tip.x), int(tip.y)), 3)

        for proj in self.projectiles:
            proj.draw(surf, camera)


class BladeWeapon:
    """
    Rotating blades orbiting the player; damages nearby enemies.
    """
    def __init__(self):
        self.level = 1
        self.damage = S.BLADE_BASE_DAMAGE
        self.radius = S.BLADE_BASE_RADIUS
        self.rot_speed = S.BLADE_BASE_ROT_SPEED
        self.count = S.BLADE_BASE_COUNT

        self.angle = 0.0

        # per-enemy hit cooldown tracking
        self._hit_cd: dict[int, float] = {}

    def update(self, dt: float, player_pos: Vector2, enemies: list):
        self.angle = (self.angle + self.rot_speed * dt) % (math.tau)

        # decay hit cooldown
        to_del = []
        for k in self._hit_cd:
            self._hit_cd[k] -= dt
            if self._hit_cd[k] <= 0:
                to_del.append(k)
        for k in to_del:
            del self._hit_cd[k]

        # compute blade positions and apply damage
        for i in range(self.count):
            a = self.angle + (i / self.count) * math.tau
            blade_pos = player_pos + Vector2(math.cos(a), math.sin(a)) * self.radius

            for e in enemies:
                # use id(e) as key
                key = id(e)
                if key in self._hit_cd:
                    continue
                if circle_hit(blade_pos, S.BLADE_SIZE, e.pos, e.radius):
                    e.take_damage(self.damage)
                    self._hit_cd[key] = S.BLADE_HIT_INTERVAL

    def draw(self, surf: pygame.Surface, camera: Vector2, player_pos: Vector2):
        center = player_pos - camera
        # orbit circle hint
        pygame.draw.circle(surf, (70, 70, 90), (int(center.x), int(center.y)), int(self.radius), 1)

        for i in range(self.count):
            a = self.angle + (i / self.count) * math.tau
            blade_pos = player_pos + Vector2(math.cos(a), math.sin(a)) * self.radius
            p = blade_pos - camera
            pygame.draw.circle(surf, S.PURPLE, (int(p.x), int(p.y)), S.BLADE_SIZE)


class LightningStrike:
    def __init__(self, pos: Vector2, radius: float, life: float = 0.18):
        self.pos = Vector2(pos)
        self.radius = radius
        self.life = life
        self.alive = True

    def update(self, dt: float):
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf: pygame.Surface, camera: Vector2):
        p = self.pos - camera
        # simple flash ring
        pygame.draw.circle(surf, S.BLUE, (int(p.x), int(p.y)), int(self.radius), 3)
        pygame.draw.circle(surf, S.WHITE, (int(p.x), int(p.y)), int(self.radius * 0.35), 2)


class LightningWeapon:
    """
    Periodic AoE strike near mouse (world pos) OR random enemy if none in range.
    """
    def __init__(self):
        self.level = 1
        self.damage = S.LIGHTNING_BASE_DAMAGE
        self.cooldown = S.LIGHTNING_BASE_COOLDOWN
        self.radius = S.LIGHTNING_BASE_RADIUS
        self.strike_count = S.LIGHTNING_STRIKE_COUNT

        self.timer = 0.0
        self.strikes: list[LightningStrike] = []

    def _pick_targets(self, player_pos: Vector2, mouse_world: Vector2, enemies: list) -> list[Vector2]:
        targets: list[Vector2] = []
        if not enemies:
            return targets

        # prefer enemies near mouse, within a target range around player
        in_range = [e for e in enemies if (e.pos - player_pos).length() <= S.LIGHTNING_TARGET_RANGE]
        if not in_range:
            in_range = enemies[:]

        # sort by distance to mouse_world (closest to mouse)
        in_range.sort(key=lambda e: (e.pos - mouse_world).length_squared())

        # choose top candidates, but add some randomness for variety
        pool = in_range[:min(10, len(in_range))]
        for _ in range(self.strike_count):
            e = random.choice(pool)
            # small jitter to not always be identical
            jitter = Vector2(random.uniform(-12, 12), random.uniform(-12, 12))
            targets.append(e.pos + jitter)
        return targets

    def update(self, dt: float, player_pos: Vector2, mouse_world: Vector2, enemies: list):
        for s in self.strikes:
            s.update(dt)
        self.strikes = [s for s in self.strikes if s.alive]

        self.timer -= dt
        if self.timer > 0:
            return

        targets = self._pick_targets(player_pos, mouse_world, enemies)
        if not targets:
            self.timer = self.cooldown
            return

        # apply damage to enemies in AoE
        for t in targets:
            self.strikes.append(LightningStrike(t, self.radius))
            for e in enemies:
                if (e.pos - t).length_squared() <= (self.radius + e.radius) ** 2:
                    e.take_damage(self.damage)

        self.timer = self.cooldown

    def draw(self, surf: pygame.Surface, camera: Vector2):
        for s in self.strikes:
            s.draw(surf, camera)


class WeaponSystem:
    """
    Holds all required weapons and draws/updates them.
    """
    def __init__(self):
        self.projectile = ProjectileWeapon()
        self.blades = BladeWeapon()
        self.lightning = LightningWeapon()

    def update(self, dt: float, player, aim_dir: Vector2, mouse_world: Vector2, enemies: list):
        self.projectile.update(dt, player.pos, aim_dir, enemies)
        self.blades.update(dt, player.pos, enemies)
        self.lightning.update(dt, player.pos, mouse_world, enemies)

    def draw(self, surf: pygame.Surface, camera: Vector2, player, aim_dir: Vector2):
        self.blades.draw(surf, camera, player.pos)
        self.projectile.draw(surf, camera, player.pos, aim_dir)
        self.lightning.draw(surf, camera)

    # Upgrade hooks
    def apply_damage_multiplier(self, mult: float):
        self.projectile.damage *= mult
        self.blades.damage *= mult
        self.lightning.damage *= mult

    def apply_attack_speed_multiplier(self, mult: float):
        # lower cooldown => faster
        self.projectile.cooldown = max(0.07, self.projectile.cooldown / mult)
        self.lightning.cooldown = max(0.45, self.lightning.cooldown / mult)
        self.blades.rot_speed *= mult
