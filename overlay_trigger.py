# overlay_trigger.py
import json
import os
import random
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Deque

from PySide6 import QtCore, QtGui, QtWidgets
from pynput import keyboard, mouse

from overlay_ui import OverlayWindow
from question_engine import QuestionEngine


# -------------------- Settings --------------------

@dataclass
class Settings:
    activity_window_sec: int = 8
    low_activity_threshold: int = 6
    high_activity_spike_threshold: int = 14

    cooldown_sec: int = 45
    snooze_minutes: int = 10
    max_popups_per_hour: int = 20

    # AI mode:
    # off   -> local only
    # cache -> cached AI only (NO tokens)
    # live  -> cached first, else API (tokens)
    ai_mode: str = "off"
    ai_grade_level: str = "Primary 3–6"
    ai_difficulty: str = "easy"
    ai_model: str = "gpt-4.1-mini"

    overlay_position: str = "center"  # center | top_right
    overlay_margin_px: int = 40
    monitor_index: int = 0

    auto_dismiss_after_answer_ms: int = 1200


def load_settings(path: str = "settings.json") -> Settings:
    s = Settings()
    if not os.path.exists(path):
        return s
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
    except Exception:
        pass
    return s


def save_settings(settings: Settings, path: str = "settings.json") -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# -------------------- App Controller --------------------

class BrainBuffApp(QtCore.QObject):
    # Thread-safe signals (pynput thread -> Qt UI thread)
    sig_activity = QtCore.Signal()
    sig_answer = QtCore.Signal(int)
    sig_snooze = QtCore.Signal()
    sig_toggle_mode = QtCore.Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        self.engine = QuestionEngine(
            local_bank_path="questions.json",
            ai_cache_path="ai_cache.jsonl",
            ai_mode=settings.ai_mode,
            ai_model=settings.ai_model,
        )

        self.overlay = OverlayWindow(on_answer=self.answer)

        # Rolling window of input timestamps
        self.input_times: Deque[float] = deque()

        self.last_popup_time: float = 0.0
        self.snoozed_until: float = 0.0
        self.popups_history: Deque[float] = deque()

        self.overlay_visible = False
        self.overlay_shown_at: float = 0.0  # grace period

        # Connect signals
        self.sig_activity.connect(self._record_input)
        self.sig_answer.connect(self.answer)
        self.sig_snooze.connect(self.snooze)
        self.sig_toggle_mode.connect(self.toggle_ai_mode_safe)

        # Logic tick
        self.tick = QtCore.QTimer()
        self.tick.setInterval(200)
        self.tick.timeout.connect(self._update_logic)
        self.tick.start()

        # Global listeners
        self._start_global_listeners()

        self._place_overlay()

        self._last_move_time = 0.0
        self._move_throttle_sec = 0.12  # ~8 moves/sec

    # ---------- Global input ----------
    def _start_global_listeners(self):
        self.k_listener = keyboard.Listener(on_press=self._on_key_press)
        self.k_listener.daemon = True
        self.k_listener.start()

        self.m_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self.m_listener.daemon = True
        self.m_listener.start()

    def _record_input(self):
        # Keep recording even while overlay is visible (so spike-hide works)
        self.input_times.append(time.time())

    def _on_mouse_move(self, x, y):
        if self._point_over_overlay(x, y):
            return
        now = time.time()
        if now - self._last_move_time < self._move_throttle_sec:
            return
        self._last_move_time = now
        self.sig_activity.emit()

    def _on_mouse_click(self, x, y, button, pressed):
        # Ignore clicks meant for answering
        if self._point_over_overlay(x, y):
            return
        self.sig_activity.emit()

    def _on_mouse_scroll(self, x, y, dx, dy):
        self.sig_activity.emit()

    def _on_key_press(self, key):
        # Hotkeys first (don’t count as activity)
        try:
            if key == keyboard.Key.f9:
                self.sig_snooze.emit()
                return
            if key == keyboard.Key.f10:
                self.sig_toggle_mode.emit()
                return
            if hasattr(key, "char") and key.char in ["1", "2", "3", "4"]:
                self.sig_answer.emit(int(key.char) - 1)
                return
        except Exception:
            pass

        self.sig_activity.emit()

    # ---------- Rules ----------
    def _cleanup_old_inputs(self, now: float):
        window = float(self.settings.activity_window_sec)
        while self.input_times and (now - self.input_times[0]) > window:
            self.input_times.popleft()

    def _inputs_in_window(self) -> int:
        return len(self.input_times)

    def _cooldown_ok(self, now: float) -> bool:
        return (now - self.last_popup_time) >= float(self.settings.cooldown_sec)

    def _snooze_ok(self, now: float) -> bool:
        return now >= self.snoozed_until

    def _max_per_hour_ok(self, now: float) -> bool:
        one_hour = 3600.0
        while self.popups_history and (now - self.popups_history[0]) > one_hour:
            self.popups_history.popleft()
        return len(self.popups_history) < int(self.settings.max_popups_per_hour)

    def _update_logic(self):
        now = time.time()
        self._cleanup_old_inputs(now)
        count = self._inputs_in_window()

        # If visible and user resumes heavy activity, hide (after grace period)
        if self.overlay_visible:
            if (now - self.overlay_shown_at) >= 2.0:
                if count >= int(self.settings.high_activity_spike_threshold):
                    self.hide_overlay()
            return

        low_activity = count <= int(self.settings.low_activity_threshold)
        if low_activity and self._cooldown_ok(now) and self._snooze_ok(now) and self._max_per_hour_ok(now):
            self.show_question()

    def _point_over_overlay(self, x: int, y: int) -> bool:
        if not self.overlay_visible or not self.overlay.isVisible():
            return False
        geo = self.overlay.frameGeometry()  # screen coords
        return geo.contains(QtCore.QPoint(int(x), int(y)))

    def _place_overlay(self):
        screens = QtGui.QGuiApplication.screens()
        if not screens:
            return
        mi = int(self.settings.monitor_index)
        if mi < 0 or mi >= len(screens):
            mi = 0

        screen = screens[mi]
        geo = screen.availableGeometry()

        w, h = 700, 400
        self.overlay.setFixedSize(w, h)

        if self.settings.overlay_position == "top_right":
            x = geo.x() + geo.width() - w - int(self.settings.overlay_margin_px)
            y = geo.y() + int(self.settings.overlay_margin_px)
        else:
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2

        self.overlay.move(x, y)

    # ---------- Actions ----------
    def show_question(self):
        self.engine.set_ai_mode(self.settings.ai_mode, self.settings.ai_model)

        topics = ["Mathematics", "Science", "English", "History", "Geography", "General Knowledge"]
        topic = random.choice(topics)

        q = self.engine.get_question(
            topic=topic,
            grade_level=self.settings.ai_grade_level,
            difficulty=self.settings.ai_difficulty,
        )
        source = getattr(self.engine, "last_source", "local")

        self.overlay.set_question(
            q=q,
            source=source,
            ai_mode=self.settings.ai_mode,
            snooze_minutes=int(self.settings.snooze_minutes),
        )
        self._place_overlay()

        now = time.time()
        self.last_popup_time = now
        self.popups_history.append(now)

        self.overlay.show()
        self.overlay.raise_()
        self.overlay_visible = True
        self.overlay_shown_at = now

    def answer(self, idx: int):
        if not self.overlay_visible or not self.overlay.current_question:
            return

        q = self.overlay.current_question
        correct = (idx == q.answer_index)
        self.overlay.show_feedback(correct, q.explanation or "")

        QtCore.QTimer.singleShot(int(self.settings.auto_dismiss_after_answer_ms), self.hide_overlay)

    def hide_overlay(self):
        if self.overlay_visible:
            self.overlay.hide()
            self.overlay_visible = False

    def snooze(self):
        self.hide_overlay()
        self.snoozed_until = time.time() + float(self.settings.snooze_minutes) * 60.0

    def toggle_ai_mode_safe(self):
        """
        SAFE toggle (NO tokens):
          OFF <-> CACHE
        (To use LIVE, set ai_mode="live" manually in settings.json.)
        """
        mode = (self.settings.ai_mode or "off").strip().lower()
        self.settings.ai_mode = "cache" if mode == "off" else "off"

        self.engine.set_ai_mode(self.settings.ai_mode, self.settings.ai_model)
        save_settings(self.settings, "settings.json")

        msg = f"Mode: {self.settings.ai_mode.upper()} (OFF↔CACHE)."
        if self.overlay_visible:
            self.overlay.hint.setText(msg)
        else:
            self._place_overlay()
            self.overlay.title.setText("BrainBuff")
            self.overlay.meta.setText("")
            self.overlay.question_label.setText("")
            for b in self.overlay.choice_buttons:
                b.setText("")
            self.overlay.hint.setText(msg)
            self.overlay.show()
            self.overlay.raise_()
            self.overlay_visible = True
            self.overlay_shown_at = time.time()
            QtCore.QTimer.singleShot(900, self.hide_overlay)


def main():
    settings = load_settings("settings.json")
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("BrainBuff")

    _controller = BrainBuffApp(settings)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
