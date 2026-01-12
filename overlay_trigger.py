# overlay_trigger.py
import json
import os
import random
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Deque, Optional, Set

from PySide6 import QtCore, QtGui, QtWidgets
from pynput import keyboard, mouse

from overlay_ui import OverlayWindow
from question_engine import QuestionEngine
import ctypes



# -------------------- Settings --------------------

@dataclass
class Settings:
    # Activity monitoring
    activity_window_sec: int = 8               # rolling window size (seconds)
    low_activity_threshold: int = 6            # show quiz when count <= this
    high_activity_spike_threshold: int = 14    # hide overlay when count >= this

    # Rate limiting
    cooldown_sec: int = 45                     # minimum time between popups
    snooze_minutes: int = 10                   # F9 snooze duration
    max_popups_per_hour: int = 20              # hard cap per hour

    # AI mode (token-safe)
    # off   -> local only
    # cache -> cached AI only (NO tokens)
    # live  -> cached first, else API (tokens)
    ai_mode: str = "off"
    ai_grade_level: str = "Primary 3–6"
    ai_difficulty: str = "easy"
    ai_model: str = "gpt-4.1-mini"

    # Overlay placement
    overlay_position: str = "center"           # center | top_right
    overlay_margin_px: int = 40
    monitor_index: int = 0

    # Feedback / UX
    auto_dismiss_after_answer_ms: int = 1200

    # Mouse activity sampling (prevents huge counts)
    mouse_move_throttle_sec: float = 0.12      # ~8 moves/sec


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


def ensure_settings_file(path: str = "settings.json") -> Settings:
    """
    Loads settings.json if present, otherwise writes defaults and returns them.
    """
    s = load_settings(path)
    if not os.path.exists(path):
        save_settings(s, path)
    return s


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
        self.overlay_shown_at: float = 0.0  # grace period start time

        # Input filters
        self._last_move_time = 0.0
        self._keys_down: Set[object] = set()  # to ignore key-repeat

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

        # Initial placement
        self._place_overlay()

    def _force_topmost_no_activate(self):
        """Force overlay above borderless game windows on Windows (no focus steal)."""
        if not sys.platform.startswith("win"):
            return
        try:
            hwnd = int(self.overlay.winId())
            user32 = ctypes.windll.user32

            HWND_TOPMOST = -1
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040

            user32.SetWindowPos(
                hwnd, HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
        except Exception:
            pass

    # ---------- Global input ----------
    def _start_global_listeners(self):
        # Keyboard: include on_release so we can ignore auto-repeat
        self.k_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.k_listener.daemon = True
        self.k_listener.start()

        # Mouse
        self.m_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self.m_listener.daemon = True
        self.m_listener.start()

    def _record_input(self):
        # Keep recording even while overlay is visible (spike-hide depends on it)
        self.input_times.append(time.time())

    def _on_mouse_move(self, x, y):
        if self._point_over_overlay():
            return

        now = time.time()
        if (now - self._last_move_time) < float(self.settings.mouse_move_throttle_sec):
            return
        self._last_move_time = now
        self.sig_activity.emit()

    def _on_mouse_click(self, x, y, button, pressed):
        if self._point_over_overlay():
            return
        self.sig_activity.emit()

    def _on_mouse_scroll(self, x, y, dx, dy):
        if self._point_over_overlay():
            return
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

        # Ignore key-repeat: only count first press until release
        if key in self._keys_down:
            return
        self._keys_down.add(key)

        self.sig_activity.emit()

    def _on_key_release(self, key):
        self._keys_down.discard(key)

    # ---------- Rules ----------
    def _cleanup_old_inputs(self, now: float):
        window = float(self.settings.activity_window_sec)
        while self.input_times and (now - self.input_times[0]) > window:
            self.input_times.popleft()

    def _inputs_in_window(self) -> int:
        return len(self.input_times)

    def _cooldown_ok(self, now: float) -> bool:
        if self.last_popup_time <= 0:
            return True
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

        # If visible: hide only on spikes (after grace), BUT never hide if cursor is over overlay
        if self.overlay_visible:
            if self._point_over_overlay():
                return

            if (now - self.overlay_shown_at) >= 2.0:
                if count >= int(self.settings.high_activity_spike_threshold):
                    self.hide_overlay()
            return

        # Not visible: show on low activity + rate limits
        low_activity = count <= int(self.settings.low_activity_threshold)
        if low_activity and self._cooldown_ok(now) and self._snooze_ok(now) and self._max_per_hour_ok(now):
            self.show_question()

        # Debug print (every ~2s)
        if now % 2 < 0.2:
            dt = now - self.last_popup_time
            print(
                "count=", count,
                "low=", low_activity,
                "cooldown=", self._cooldown_ok(now),
                "dt=", round(dt, 3),
                "snooze=", self._snooze_ok(now),
                "max=", self._max_per_hour_ok(now),
                "visible=", self.overlay_visible
            )

    def _point_over_overlay(self) -> bool:
        # DPI-safe: use Qt cursor global coordinates
        if not self.overlay_visible or not self.overlay.isVisible():
            return False
        return self.overlay.frameGeometry().contains(QtGui.QCursor.pos())

    def _place_overlay(self):
        screens = QtGui.QGuiApplication.screens()
        if not screens:
            return

        mi = int(self.settings.monitor_index)
        if mi < 0 or mi >= len(screens):
            mi = 0

        screen = screens[mi]
        geo = screen.availableGeometry()

        # DO NOT force size here; overlay_ui may auto-resize for images.
        w = self.overlay.width()
        h = self.overlay.height()

        if self.settings.overlay_position == "top_right":
            x = geo.x() + geo.width() - w - int(self.settings.overlay_margin_px)
            y = geo.y() + int(self.settings.overlay_margin_px)
        else:
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2

        self.overlay.move(x, y)

    # ---------- Actions ----------
    def show_question(self):
        print("SHOW QUESTION", time.time())

        self.engine.set_ai_mode(self.settings.ai_mode, self.settings.ai_model)

        topics = ["Mathematics", "Decimals", "Fractions", "Geometry"]
        topic = random.choice(topics)

        q = self.engine.get_question(
            topic=topic,
            grade_level=self.settings.ai_grade_level,
            difficulty=self.settings.ai_difficulty,
        )
        source = getattr(self.engine, "last_source", "local")

        # Set question FIRST (overlay_ui may auto-resize for images)
        self.overlay.set_question(
            q=q,
            source=source,
            ai_mode=self.settings.ai_mode,
            snooze_minutes=int(self.settings.snooze_minutes),
        )

        # Place AFTER Qt has applied layout / resize changes
        QtCore.QTimer.singleShot(0, self._place_overlay)

        now = time.time()
        self.last_popup_time = now
        self.popups_history.append(now)

        # Show overlay and force TOPMOST (helps over borderless pygame windows)
        self.overlay.show()
        self.overlay.raise_()

        # Force above borderless game without stealing focus
        if hasattr(self, "_force_topmost_no_activate"):
            self._force_topmost_no_activate()
            QtCore.QTimer.singleShot(50, self._force_topmost_no_activate)

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
        print("HIDE OVERLAY", time.time())
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
            # Quick toast-like overlay message
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
    settings = ensure_settings_file("settings.json")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("BrainBuff")

    _controller = BrainBuffApp(settings)

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
