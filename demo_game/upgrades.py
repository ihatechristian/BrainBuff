# upgrades.py
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class UpgradeDef:
    key: str
    name: str
    desc: str
    max_level: int
    apply: Callable  # (game_state) -> None


class UpgradeManager:
    """
    Tracks upgrade levels and produces 3-choice selections (no duplicates).
    Projectile-only version (no blades, no lightning).
    """
    def __init__(self, game):
        self.game = game
        self.levels: dict[str, int] = {}
        self.defs: list[UpgradeDef] = self._build_defs()

    def level_of(self, key: str) -> int:
        return self.levels.get(key, 0)

    def can_take(self, u: UpgradeDef) -> bool:
        return self.level_of(u.key) < u.max_level

    def take(self, u: UpgradeDef):
        if not self.can_take(u):
            return
        self.levels[u.key] = self.level_of(u.key) + 1
        u.apply(self.game)

    def _build_defs(self) -> list[UpgradeDef]:
        g = self.game

        # -------------------------
        # Projectile-only upgrades
        # -------------------------
        def proj_damage():
            # +12% each level (stacks)
            g.weapons.projectile.damage *= 1.12

        def proj_fire_rate():
            # faster => reduce cooldown
            g.weapons.projectile.cooldown = max(0.07, g.weapons.projectile.cooldown * 0.88)

        def proj_count():
            # keep if you want multi-shot; otherwise delete this upgrade too
            g.weapons.projectile.projectile_count += 1

        # -------------------------
        # Player stat upgrades
        # -------------------------
        def move_speed():
            g.player.move_speed_mult *= 1.08

        def max_hp():
            g.player.max_hp *= 1.12
            g.player.hp = min(g.player.max_hp, g.player.hp + 8)

        def heal():
            g.player.heal(28)

        # -------------------------
        # Global modifiers (projectile-only now)
        # -------------------------
        def global_damage():
            g.player.damage_mult *= 1.08
            g.weapons.apply_damage_multiplier(1.08)

        def attack_speed():
            g.player.attack_speed_mult *= 1.08
            g.weapons.apply_attack_speed_multiplier(1.08)

        return [
            UpgradeDef("proj_dmg", "Projectile Damage", "+12% projectile damage", 8, lambda game=g: proj_damage()),
            UpgradeDef("proj_rate", "Projectile Fire Rate", "Shoot faster (cooldown -12%)", 8, lambda game=g: proj_fire_rate()),
            UpgradeDef("proj_count", "Projectile Count", "+1 projectile per shot", 6, lambda game=g: proj_count()),

            UpgradeDef("move_speed", "Move Speed", "+8% movement speed", 10, lambda game=g: move_speed()),
            UpgradeDef("max_hp", "Max HP", "+12% max HP (small heal)", 8, lambda game=g: max_hp()),
            UpgradeDef("heal", "Heal", "Heal 28 HP instantly", 99, lambda game=g: heal()),

            UpgradeDef("global_dmg", "All Damage", "+8% damage (projectiles)", 10, lambda game=g: global_damage()),
            UpgradeDef("atk_speed", "Attack Speed", "+8% attack speed (projectiles)", 10, lambda game=g: attack_speed()),
        ]

    def roll_choices(self, k: int = 3) -> list[UpgradeDef]:
        pool = [u for u in self.defs if self.can_take(u)]
        if not pool:
            return []
        random.shuffle(pool)
        return pool[:min(k, len(pool))]
