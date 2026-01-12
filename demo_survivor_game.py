# demo_survivor_game.py
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from overlay_ui import OverlayWindow
from question_engine import QuestionEngine, Question


# -------------------- Simple math helpers --------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def length(x: float, y: float) -> float:
    return math.hypot(x, y)

def norm(x: float, y: float) -> Tuple[float, float]:
    l = math.hypot(x, y)
    if l <= 1e-9:
        return 0.0, 0.0
    return x / l, y / l

def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


# -------------------- Game entities --------------------

@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    r: float = 4.0
    life: float = 1.2  # seconds

@dataclass
class Enemy:
    x: float
    y: float
    r: float = 16.0
    speed: float = 85.0
    hp: int = 1


# -------------------- Game widget --------------------

class SurvivorGame(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainBuff Demo Game (Survivor-like)")
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        # Game state
        self.w = 1000
        self.h = 640
        self.resize(self.w, self.h)

        self.player_x = self.w * 0.5
        self.player_y = self.h * 0.5
        self.player_r = 18.0
        self.player_speed = 220.0
        self.player_hp = 5
        self.max_hp = 5

        self.aim_x = self.player_x + 1
        self.aim_y = self.player_y

        self.bullets: List[Bullet] = []
        self.enemies: List[Enemy] = []

        self.score = 0
        self.xp = 0

        # Timing
        self._last_time = time.time()
        self._accum_shoot = 0.0
        self._accum_spawn = 0.0

        # Controls
        self.keys = set()
        self.game_over = False

        # Quiz integration
        self.engine = QuestionEngine(
            local_bank_path="questions.json",
            ai_cache_path="ai_cache.jsonl",
            ai_mode="off",        # keep OFF for demo (no tokens)
            ai_model="gpt-4.1-mini",
        )
        self.overlay = OverlayWindow(on_answer=self._on_overlay_answer)
        self.overlay_visible = False
        self.paused_for_quiz = False

        # Idle-based quiz triggering
        self.last_input_time = time.time()
        self.idle_seconds_to_quiz = 3.0   # show quiz if idle for 3s
        self.quiz_cooldown = 8.0          # minimum seconds between quizzes
        self.last_quiz_time = 0.0

        # Game loop
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)  # ~60 FPS
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        # Put overlay near top-right of the same screen
        self._place_overlay()

    # -------------------- Overlay helpers --------------------

    def _place_overlay(self):
        screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        # Use overlay's current size (it may auto-resize for diagrams)
        w = self.overlay.width()
        h = self.overlay.height()

        margin = 20
        x = geo.x() + geo.width() - w - margin
        y = geo.y() + margin
        self.overlay.move(x, y)

    def _show_quiz(self):
        if self.overlay_visible:
            return
        now = time.time()
        if now - self.last_quiz_time < self.quiz_cooldown:
            return

        # Pick topic; for PSLE math demo keep it mostly math
        topic = random.choice(["Mathematics", "Decimals", "Fractions", "Geometry"])
        q = self.engine.get_question(
            topic=topic,
            grade_level="PSLE",
            difficulty="easy",
        )
        source = getattr(self.engine, "last_source", "local")

        self.overlay.set_question(
            q=q,
            source=source,
            ai_mode=getattr(self.engine, "ai_mode", "off"),
            snooze_minutes=10,
        )

        # Place after Qt has applied layout/sizing (esp. for images)
        QtCore.QTimer.singleShot(0, self._place_overlay)

        self.overlay.show()
        self.overlay.raise_()
        self.overlay_visible = True
        self.paused_for_quiz = True
        self.last_quiz_time = now

    def _hide_quiz(self):
        if not self.overlay_visible:
            return
        self.overlay.hide()
        self.overlay_visible = False
        self.paused_for_quiz = False

    def _on_overlay_answer(self, idx: int):
        """Called when user clicks a choice button on the overlay."""
        self._answer_quiz(idx)

    def _answer_quiz(self, idx: int):
        if not self.overlay_visible or not self.overlay.current_question:
            return

        q = self.overlay.current_question
        correct = (idx == q.answer_index)
        self.overlay.show_feedback(correct, q.explanation or "")

        if correct:
            self._grant_reward()

        # Hide after a short delay
        QtCore.QTimer.singleShot(900, self._hide_quiz)

    def _grant_reward(self):
        # Reward examples: XP + optional heal
        self.xp += 10
        if self.player_hp < self.max_hp and (self.xp % 30 == 0):
            self.player_hp += 1

    # -------------------- Input events --------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        key = event.key()

        # Force quiz for demo (boss-friendly)
        if key == QtCore.Qt.Key_F8 and not self.game_over:
            self._show_quiz()
            return

        # Hide quiz
        if key == QtCore.Qt.Key_Escape and self.overlay_visible:
            self._hide_quiz()
            return

        # When quiz is visible, let 1-4 answer (overlay doesn't take focus)
        if self.overlay_visible:
            if key in (QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3, QtCore.Qt.Key_4):
                idx = int(chr(key)) - 1  # Key_1 -> '1'
                self._answer_quiz(idx)
                return

        # Normal movement keys
        if key == QtCore.Qt.Key_W:
            self.keys.add("w")
        elif key == QtCore.Qt.Key_A:
            self.keys.add("a")
        elif key == QtCore.Qt.Key_S:
            self.keys.add("s")
        elif key == QtCore.Qt.Key_D:
            self.keys.add("d")

        self.last_input_time = time.time()

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        if key == QtCore.Qt.Key_W:
            self.keys.discard("w")
        elif key == QtCore.Qt.Key_A:
            self.keys.discard("a")
        elif key == QtCore.Qt.Key_S:
            self.keys.discard("s")
        elif key == QtCore.Qt.Key_D:
            self.keys.discard("d")

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        pos = event.position()
        self.aim_x = float(pos.x())
        self.aim_y = float(pos.y())
        self.last_input_time = time.time()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        # You can extend: left click could fire a burst, etc.
        self.last_input_time = time.time()

    # -------------------- Game loop --------------------

    def _tick(self):
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        dt = clamp(dt, 0.0, 0.05)

        if not self.game_over:
            # Idle trigger: if player is idle and quiz not visible, show quiz
            if not self.overlay_visible and (now - self.last_input_time) >= self.idle_seconds_to_quiz:
                self._show_quiz()

        if self.game_over or self.paused_for_quiz:
            self.update()
            return

        self._update_player(dt)
        self._update_shooting(dt)
        self._update_enemies(dt)
        self._handle_collisions()
        self.update()

    def _update_player(self, dt: float):
        dx = 0.0
        dy = 0.0
        if "w" in self.keys:
            dy -= 1
        if "s" in self.keys:
            dy += 1
        if "a" in self.keys:
            dx -= 1
        if "d" in self.keys:
            dx += 1

        nx, ny = norm(dx, dy)
        self.player_x += nx * self.player_speed * dt
        self.player_y += ny * self.player_speed * dt

        # keep inside window bounds
        self.player_x = clamp(self.player_x, self.player_r, self.width() - self.player_r)
        self.player_y = clamp(self.player_y, self.player_r, self.height() - self.player_r)

    def _update_shooting(self, dt: float):
        # Auto-shoot
        fire_rate = 6.5  # bullets per second
        self._accum_shoot += dt
        interval = 1.0 / fire_rate

        while self._accum_shoot >= interval:
            self._accum_shoot -= interval
            ax = self.aim_x - self.player_x
            ay = self.aim_y - self.player_y
            nx, ny = norm(ax, ay)
            if nx == 0.0 and ny == 0.0:
                continue

            speed = 520.0
            self.bullets.append(Bullet(
                x=self.player_x,
                y=self.player_y,
                vx=nx * speed,
                vy=ny * speed,
            ))

        # Update bullets
        for b in self.bullets:
            b.x += b.vx * dt
            b.y += b.vy * dt
            b.life -= dt

        self.bullets = [
            b for b in self.bullets
            if b.life > 0
            and -50 < b.x < self.width() + 50
            and -50 < b.y < self.height() + 50
        ]

    def _spawn_enemy(self):
        # Spawn at edges
        side = random.choice(["top", "bottom", "left", "right"])
        if side == "top":
            x = random.uniform(0, self.width())
            y = -30
        elif side == "bottom":
            x = random.uniform(0, self.width())
            y = self.height() + 30
        elif side == "left":
            x = -30
            y = random.uniform(0, self.height())
        else:
            x = self.width() + 30
            y = random.uniform(0, self.height())

        e = Enemy(x=x, y=y)
        # Slight difficulty scaling
        e.speed = 80 + min(120, self.score * 0.6)
        e.hp = 1 if self.score < 20 else (2 if self.score < 60 else 3)
        self.enemies.append(e)

    def _update_enemies(self, dt: float):
        # Spawn over time
        self._accum_spawn += dt
        spawn_interval = max(0.25, 1.0 - self.score * 0.01)  # faster spawns as score grows

        while self._accum_spawn >= spawn_interval:
            self._accum_spawn -= spawn_interval
            self._spawn_enemy()

        # Move toward player
        for e in self.enemies:
            dx = self.player_x - e.x
            dy = self.player_y - e.y
            nx, ny = norm(dx, dy)
            e.x += nx * e.speed * dt
            e.y += ny * e.speed * dt

    def _handle_collisions(self):
        # Bullet vs Enemy
        remaining_bullets = []
        for b in self.bullets:
            hit = False
            for e in self.enemies:
                if dist(b.x, b.y, e.x, e.y) <= (b.r + e.r):
                    e.hp -= 1
                    hit = True
                    break
            if not hit:
                remaining_bullets.append(b)
        self.bullets = remaining_bullets

        # Remove dead enemies + score
        alive_enemies = []
        for e in self.enemies:
            if e.hp <= 0:
                self.score += 1
            else:
                alive_enemies.append(e)
        self.enemies = alive_enemies

        # Enemy vs Player
        for e in self.enemies:
            if dist(self.player_x, self.player_y, e.x, e.y) <= (self.player_r + e.r):
                self.player_hp -= 1
                # knock enemy away a bit
                dx = e.x - self.player_x
                dy = e.y - self.player_y
                nx, ny = norm(dx, dy)
                e.x += nx * 30
                e.y += ny * 30

                if self.player_hp <= 0:
                    self.game_over = True
                    self._hide_quiz()
                    break

    # -------------------- Rendering --------------------

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Background
        painter.fillRect(self.rect(), QtGui.QColor(20, 20, 24))

        # Arena boundary
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 35))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 18, 18)

        # Aim line
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 40))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(int(self.player_x), int(self.player_y), int(self.aim_x), int(self.aim_y))

        # Player
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(80, 190, 255))
        painter.drawEllipse(QtCore.QPointF(self.player_x, self.player_y), self.player_r, self.player_r)

        # Enemies
        painter.setBrush(QtGui.QColor(255, 80, 80))
        for e in self.enemies:
            painter.drawEllipse(QtCore.QPointF(e.x, e.y), e.r, e.r)

        # Bullets
        painter.setBrush(QtGui.QColor(250, 240, 180))
        for b in self.bullets:
            painter.drawEllipse(QtCore.QPointF(b.x, b.y), b.r, b.r)

        # HUD
        painter.setPen(QtGui.QColor(255, 255, 255, 220))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)

        hud = f"HP: {self.player_hp}/{self.max_hp}   Score: {self.score}   XP: {self.xp}   (F8 force quiz)"
        painter.drawText(14, 26, hud)

        if self.paused_for_quiz:
            painter.setPen(QtGui.QColor(255, 255, 255, 170))
            font2 = painter.font()
            font2.setPointSize(14)
            font2.setBold(True)
            painter.setFont(font2)
            painter.drawText(14, 54, "Paused for quiz… (Answer 1–4 or click)")

        if self.game_over:
            painter.setPen(QtGui.QColor(255, 255, 255, 230))
            font3 = painter.font()
            font3.setPointSize(28)
            font3.setBold(True)
            painter.setFont(font3)
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "GAME OVER")

        painter.end()


# -------------------- Main --------------------

def main():
    # Ensure working directory is project root so images/ paths resolve
    # (Optional) set cwd to script dir:
    # os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = QtWidgets.QApplication(sys.argv)

    game = SurvivorGame()
    game.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
