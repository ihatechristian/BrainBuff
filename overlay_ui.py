# overlay_ui.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6 import QtCore, QtWidgets


# If you already have Question in question_engine.py, we can reuse it.
# Otherwise this fallback dataclass lets overlay_ui.py run standalone.
try:
    from question_engine import Question  # type: ignore
except Exception:
    @dataclass
    class Question:
        topic: str
        difficulty: str
        question: str
        choices: List[str]
        answer_index: int
        explanation: str = ""


class OverlayWindow(QtWidgets.QWidget):
    """
    UI-only overlay window.
    - Accepts an optional on_answer callback (idx: 0..3).
    - Can be run standalone (see __main__ demo at bottom).
    """
    def __init__(self, on_answer: Optional[Callable[[int], None]] = None):
        super().__init__()
        self.on_answer = on_answer
        self.current_question: Optional[Question] = None

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
            | QtCore.Qt.BypassWindowManagerHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Do not steal focus (still clickable)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus, True)

        # ---------- UI ----------
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")

        self.title = QtWidgets.QLabel("BrainBuff")
        self.title.setObjectName("title")

        self.meta = QtWidgets.QLabel("")
        self.meta.setObjectName("meta")

        self.question_label = QtWidgets.QLabel("")
        self.question_label.setWordWrap(True)
        self.question_label.setObjectName("question")

        self.choice_buttons: list[QtWidgets.QPushButton] = []
        for i in range(4):
            btn = QtWidgets.QPushButton("")
            btn.setObjectName("choice")
            btn.clicked.connect(lambda checked=False, idx=i: self._choice_clicked(idx))
            self.choice_buttons.append(btn)

        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("hint")

        layout = QtWidgets.QVBoxLayout(self.card)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.question_label)
        for btn in self.choice_buttons:
            layout.addWidget(btn)
        layout.addSpacing(4)
        layout.addWidget(self.hint)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self._apply_styles()

        # Default size (controller can override)
        self.setFixedSize(700, 400)

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
                padding: 8px 10px;
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

    def set_answer_handler(self, handler: Optional[Callable[[int], None]]):
        self.on_answer = handler

    def _choice_clicked(self, idx: int):
        if self.on_answer:
            self.on_answer(idx)

    def set_question(self, q: Question, source: str = "local", ai_mode: str = "off", snooze_minutes: int = 10):
        self.current_question = q
        self.title.setText("BrainBuff")
        self.meta.setText(f"Topic: {q.topic} • Difficulty: {q.difficulty} • Source: {source.upper()}")
        self.question_label.setText(q.question)

        for i, choice in enumerate(q.choices[:4]):
            self.choice_buttons[i].setText(f"{i+1}) {choice}")

        self.hint.setText(
            f"Click choices • (Full app: 1–4 answer, F9 snooze {snooze_minutes}m, F10 mode {ai_mode.upper()})"
        )

    def show_feedback(self, correct: bool, explanation: str = ""):
        if correct:
            self.hint.setText("✅ Correct! " + (explanation or ""))
        else:
            self.hint.setText("❌ Not quite. " + (explanation or ""))


# -------------------- Standalone demo --------------------

def _demo_center(win: QtWidgets.QWidget):
    screen = QtWidgets.QApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    x = geo.x() + (geo.width() - win.width()) // 2
    y = geo.y() + (geo.height() - win.height()) // 2
    win.move(x, y)


def demo_main():
    app = QtWidgets.QApplication([])
    overlay = OverlayWindow()

    sample = Question(
        topic="Demo",
        difficulty="easy",
        question="Overlay UI test — what is 2 + 2?",
        choices=["3", "4", "5", "22"],
        answer_index=1,
        explanation="2 + 2 = 4.",
    )

    def on_answer(idx: int):
        overlay.show_feedback(idx == sample.answer_index, sample.explanation)

    overlay.set_answer_handler(on_answer)
    overlay.set_question(sample, source="local", ai_mode="off", snooze_minutes=10)
    _demo_center(overlay)
    overlay.show()

    app.exec()


if __name__ == "__main__":
    demo_main()
