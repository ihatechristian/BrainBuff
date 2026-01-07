import json
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from pynput import keyboard, mouse

from question_engine import QuestionEngine, Question

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env vars


# -------------------- Settings --------------------

@dataclass
class Settings:
    activity_window_sec: int = 8
    low_activity_threshold: int = 6
    high_activity_spike_threshold: int = 14

    cooldown_sec: int = 45
    snooze_minutes: int = 10
    max_popups_per_hour: int = 20

    ai_questions_enabled: bool = True
    ai_topic: str = "Vocabulary"
    ai_grade_level: str = "Primary 3–6"
    ai_difficulty: str = "easy"
    ai_model: str = "gpt-4.1-mini"

    overlay_position: str = "top_right"  # center | top_right
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
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
    except Exception:
        pass
    return s


# -------------------- Overlay UI --------------------

class OverlayWindow(QtWidgets.QWidget):
    """
    A top-most, frameless overlay that does NOT accept focus.
    We listen for answers via global pynput hotkeys instead.
    """
    def __init__(self, app_controller=None):
        super().__init__()
        self.app_controller = app_controller

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
            | QtCore.Qt.BypassWindowManagerHint
        )

        # Transparent window background:
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Do not steal focus:
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus, True)

        # Allow mouse clicks on overlay for answering questions
        # self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        # UI
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")

        self.title = QtWidgets.QLabel("BrainBuff")
        self.title.setObjectName("title")

        self.meta = QtWidgets.QLabel("")
        self.meta.setObjectName("meta")

        self.question_label = QtWidgets.QLabel("")
        self.question_label.setWordWrap(True)
        self.question_label.setObjectName("question")

        self.choice_labels = []
        for i in range(4):
            lbl = QtWidgets.QPushButton("")
            lbl.setObjectName("choice")
            lbl.clicked.connect(lambda checked, idx=i: self.app_controller.answer(idx) if self.app_controller else None)
            self.choice_labels.append(lbl)

        self.hint = QtWidgets.QLabel("Answer with 1–4 • Esc hide • F9 snooze 10 min")
        self.hint.setObjectName("hint")

        layout = QtWidgets.QVBoxLayout(self.card)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.question_label)
        for lbl in self.choice_labels:
            layout.addWidget(lbl)
        layout.addSpacing(4)
        layout.addWidget(self.hint)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self._apply_styles()

        self.current_question: Optional[Question] = None
        self._answer_feedback_timer = QtCore.QTimer(self)
        self._answer_feedback_timer.setSingleShot(True)
        self._answer_feedback_timer.timeout.connect(self.hide)

    def _apply_styles(self):
        self.setStyleSheet("""
            #card {
                background: rgba(18, 18, 18, 220);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 14px;
            }
            #title {
                color: white;
                font-size: 16px;
                font-weight: 700;
            }
            #meta {
                color: rgba(255, 255, 255, 170);
                font-size: 12px;
            }
            #question {
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding-top: 4px;
                padding-bottom: 4px;
            }
            #choice {
                color: rgba(255, 255, 255, 210);
                font-size: 13px;
                padding: 6px 8px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 18);
                border: none;
                text-align: left;
            }
            #choice:hover {
                background: rgba(255, 255, 255, 35);
            }
            #hint {
                color: rgba(255, 255, 255, 140);
                font-size: 12px;
            }
        """)

    def set_question(self, q: Question):
        self.current_question = q
        self.title.setText("BrainBuff")
        self.meta.setText(f"Topic: {q.topic}   •   Difficulty: {q.difficulty}")
        self.question_label.setText(q.question)

        for i, choice in enumerate(q.choices):
            self.choice_labels[i].setText(f"{i+1}) {choice}")

        self.hint.setText("Answer with 1–4 or click choices • F9 snooze 5 min")

    def show_feedback(self, correct: bool, explanation: str, dismiss_ms: int):
        if correct:
            self.hint.setText("✅ Correct! " + (explanation or ""))
        else:
            self.hint.setText("❌ Not quite. " + (explanation or ""))

        self._answer_feedback_timer.start(max(400, dismiss_ms))


# -------------------- Activity & App Controller --------------------

class BrainBuffApp(QtCore.QObject):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        self.overlay = OverlayWindow(self)
        self.engine = QuestionEngine(
            local_bank_path="questions.json",
            ai_cache_path="ai_cache.jsonl",
            ai_enabled=settings.ai_questions_enabled,
            ai_model=settings.ai_model,
        )

        # Rolling window of input timestamps (seconds)
        self.input_times: Deque[float] = deque()

        self.last_popup_time: float = 0.0
        self.snoozed_until: float = 0.0
        self.popups_history: Deque[float] = deque()

        # State
        self.overlay_visible = False

        # Timers
        self.tick = QtCore.QTimer()
        self.tick.setInterval(200)
        self.tick.timeout.connect(self._update_logic)
        self.tick.start()

        # Start global listeners
        self._start_global_listeners()

        # Initial placement
        self._place_overlay()

       

    # ---------- Global input ----------
    def _start_global_listeners(self):
        # keyboard
        self.k_listener = keyboard.Listener(on_press=self._on_key_press)
        self.k_listener.daemon = True
        self.k_listener.start()

        # mouse
        self.m_listener = mouse.Listener(on_move=self._on_mouse_move, on_click=self._on_mouse_click, on_scroll=self._on_mouse_scroll)
        self.m_listener.daemon = True
        self.m_listener.start()

    def _record_input(self):
        # Don't record input when overlay is visible (waiting for answer)
        if self.overlay_visible:
            return
        now = time.time()
        self.input_times.append(now)

    def _on_mouse_move(self, x, y):
        self._record_input()

    def _on_mouse_click(self, x, y, button, pressed):
        self._record_input()

    def _on_mouse_scroll(self, x, y, dx, dy):
        self._record_input()

    def _on_key_press(self, key):
        # Record activity only if overlay not visible
        self._record_input()

        # Global hotkeys (do NOT require overlay focus)
        try:
            if key == keyboard.Key.f9:
                self.snooze()
                return

            # 1-4 answer
            if hasattr(key, "char") and key.char in ["1", "2", "3", "4"]:
                idx = int(key.char) - 1
                self.answer(idx)
                return
        except Exception:
            pass

    # ---------- Overlay rules ----------
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

        # If activity spikes (combat), hide immediately
        if self.overlay_visible and count >= int(self.settings.high_activity_spike_threshold):
            self.hide_overlay()
            return

        # If already visible, do nothing further
        if self.overlay_visible:
            return

        # Only show if low activity + cooldown + not snoozed + max/hour
        low_activity = count <= int(self.settings.low_activity_threshold)
        if low_activity and self._cooldown_ok(now) and self._snooze_ok(now) and self._max_per_hour_ok(now):
            self.show_question()

    def _place_overlay(self):
        screens = QtGui.QGuiApplication.screens()
        if not screens:
            return

        mi = int(self.settings.monitor_index)
        if mi < 0 or mi >= len(screens):
            mi = 0

        screen = screens[mi]
        geo = screen.availableGeometry()

        self.overlay.adjustSize()
        w = 700  # Larger width
        h = 400  # Larger height
        self.overlay.setFixedSize(w, h)

        # Always center the overlay
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + (geo.height() - h) // 2

        self.overlay.move(x, y)

    def show_question(self):
        # Refresh AI toggle/model (in case settings.json edited live)
        self.engine.set_ai(self.settings.ai_questions_enabled, self.settings.ai_model)

        # Random topics for variety
        topics = ["Mathematics", "Science", "English", "History", "Geography", "General Knowledge"]
        random_topic = random.choice(topics)
        
        q = self.engine.get_question(
            topic=random_topic,
            grade_level=self.settings.ai_grade_level,
            difficulty=self.settings.ai_difficulty,
        )

        self.overlay.set_question(q)
        self._place_overlay()

        # Track popup constraints
        now = time.time()
        self.last_popup_time = now
        self.popups_history.append(now)

        # Show without focus
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_visible = True

    def answer(self, idx: int):
        if not self.overlay_visible or not self.overlay.current_question:
            return

        q = self.overlay.current_question
        correct = (idx == q.answer_index)

        # Show feedback then hide after timer
        explanation = q.explanation or ""
        self.overlay.show_feedback(correct, explanation, int(self.settings.auto_dismiss_after_answer_ms))
        
        # Hide overlay after feedback timer
        QtCore.QTimer.singleShot(int(self.settings.auto_dismiss_after_answer_ms), self.hide_overlay)

    def hide_overlay(self):
        if self.overlay_visible:
            self.overlay.hide()
            self.overlay_visible = False

    def snooze(self):
        self.hide_overlay()
        self.snoozed_until = time.time() + 5.0 * 60.0  # 5 minutes


# -------------------- main --------------------

def main():
    settings = load_settings("settings.json")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("BrainBuff")

    controller = BrainBuffApp(settings)

    # Small tray icon optional later; for MVP keep minimal.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
