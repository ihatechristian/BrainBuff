# overlay_ui.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets


# Reuse Question if available; fallback so this file can run standalone.
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
        image: Optional[str] = None


class OverlayWindow(QtWidgets.QWidget):
    """
    UI-only overlay window that supports an optional image path:
      q.image == "images/Q5.png"

    No scroll. The image is always scaled to fit (KeepAspectRatio) so the full diagram is visible.
    The window also auto-resizes (within screen limits) when an image is present.

    Theme: Calm education overlay palette (dark slate + blue accent)
    """

    def __init__(self, on_answer: Optional[Callable[[int], None]] = None):
        super().__init__()
        self.on_answer = on_answer
        self.current_question: Optional[Question] = None

        # Store the original pixmap for clean rescaling on resize
        self._diagram_pixmap: Optional[QtGui.QPixmap] = None

        # Track current feedback state for button styling
        self._feedback_active = False
        self._correct_index: Optional[int] = None

        # ---- Theme tokens (education overlay) ----
        # Background
        self.CARD_BG = "rgba(17, 24, 39, 235)"         # #111827 with alpha
        self.CARD_BORDER = "rgba(255, 255, 255, 36)"
        self.DIAGRAM_BG = "rgba(255, 255, 255, 10)"
        self.DIAGRAM_BORDER = "rgba(255, 255, 255, 22)"

        # Text
        self.TEXT_MAIN = "#F9FAFB"                     # soft white
        self.TEXT_SUB = "rgba(156, 163, 175, 220)"     # #9CA3AF
        self.TEXT_HINT = "rgba(156, 163, 175, 200)"

        # Accents
        self.ACCENT = "#3B82F6"                        # blue
        self.BUTTON_BG = "rgba(31, 41, 55, 210)"       # #1F2937-ish
        self.BUTTON_HOVER = "rgba(55, 65, 81, 220)"    # #374151-ish
        self.BUTTON_BORDER = "rgba(255, 255, 255, 18)"

        # Feedback colors
        self.GOOD = "#22C55E"                          # green
        self.BAD = "#F87171"                           # soft red
        self.WARN = "#FBBF24"                          # amber

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

        # Diagram/image area (NO scroll)
        self.image_label = QtWidgets.QLabel("")
        self.image_label.setObjectName("diagram")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setVisible(False)
        self.image_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )

        # Choices
        self.choice_buttons: list[QtWidgets.QPushButton] = []
        for i in range(4):
            btn = QtWidgets.QPushButton("")
            btn.setObjectName("choice")
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
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

        # Put the image between the question and answers
        layout.addWidget(self.image_label, stretch=1)

        for btn in self.choice_buttons:
            layout.addWidget(btn)

        layout.addSpacing(4)
        layout.addWidget(self.hint)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self._apply_styles()

        # Default size (controller can override)
        self.resize(720, 520)

    def _apply_styles(self):
        # Global stylesheet uses theme tokens above
        self.setStyleSheet(f"""
            #card {{
                background: {self.CARD_BG};
                border: 1px solid {self.CARD_BORDER};
                border-radius: 16px;
            }}
            #title {{
                color: {self.ACCENT};
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 0.3px;
            }}
            #meta {{
                color: {self.TEXT_SUB};
                font-size: 12px;
            }}
            #question {{
                color: {self.TEXT_MAIN};
                font-size: 14px;
                font-weight: 700;
                padding-top: 4px;
                padding-bottom: 4px;
            }}
            #diagram {{
                background: {self.DIAGRAM_BG};
                border: 1px solid {self.DIAGRAM_BORDER};
                border-radius: 12px;
                padding: 10px;
            }}
            #choice {{
                color: {self.TEXT_MAIN};
                font-size: 13px;
                padding: 10px 12px;
                border-radius: 12px;
                background: {self.BUTTON_BG};
                border: 1px solid {self.BUTTON_BORDER};
                text-align: left;
            }}
            #choice:hover {{
                background: {self.BUTTON_HOVER};
                border: 1px solid rgba(255, 255, 255, 32);
            }}
            #choice:pressed {{
                background: rgba(59, 130, 246, 40);
                border: 1px solid rgba(59, 130, 246, 120);
            }}
            #hint {{
                color: {self.TEXT_HINT};
                font-size: 12px;
            }}
        """)

    def set_answer_handler(self, handler: Optional[Callable[[int], None]]):
        self.on_answer = handler

    def _choice_clicked(self, idx: int):
        if self.on_answer:
            self.on_answer(idx)

    def _resolve_image_path(self, img_path: str) -> str:
        if os.path.isabs(img_path):
            return img_path
        # relative to where you run the script (project root)
        return os.path.join(os.getcwd(), img_path)

    def _available_diagram_box(self) -> QtCore.QSize:
        """
        Compute the box we can use for the diagram inside the current window,
        accounting for margins and other widgets.
        """
        box_w = max(120, self.card.width() - 40)

        fixed_h = 0
        fixed_h += self.title.sizeHint().height()
        fixed_h += self.meta.sizeHint().height()
        fixed_h += self.question_label.sizeHint().height()
        fixed_h += self.hint.sizeHint().height()

        for b in self.choice_buttons:
            fixed_h += b.sizeHint().height()

        fixed_h += 16 + 14 + 16
        fixed_h += 10 * 8

        box_h = max(120, int(self.height() - fixed_h))
        return QtCore.QSize(box_w, box_h)

    def _render_diagram(self):
        """Scale the original pixmap into the available box (KeepAspectRatio)."""
        if not self._diagram_pixmap or self._diagram_pixmap.isNull():
            return

        box = self._available_diagram_box()
        scaled = self._diagram_pixmap.scaled(
            box,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def _auto_resize_for_diagram(self):
        """
        Increase window size (within screen limits) so the diagram has room.
        This helps avoid tiny diagrams.
        """
        screen = QtWidgets.QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        max_w = int(geo.width() * 0.90)
        max_h = int(geo.height() * 0.90)

        target_w = min(max_w, max(720, self.width()))
        target_h = min(max_h, max(520, self.height()))

        if self._diagram_pixmap and not self._diagram_pixmap.isNull():
            target_h = min(max_h, max(target_h, 680))
            if self._diagram_pixmap.width() > 900:
                target_w = min(max_w, max(target_w, 900))

        self.resize(target_w, target_h)

        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def _set_image(self, img_path: Optional[str]):
        if not img_path:
            self._diagram_pixmap = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            return

        path = self._resolve_image_path(img_path)
        if not os.path.exists(path):
            self._diagram_pixmap = None
            self.image_label.setText(f"(Image not found: {img_path})")
            self.image_label.setStyleSheet(f"color: {self.WARN};")
            self.image_label.setVisible(True)
            return

        pix = QtGui.QPixmap(path)
        if pix.isNull():
            self._diagram_pixmap = None
            self.image_label.setText(f"(Could not load image: {img_path})")
            self.image_label.setStyleSheet(f"color: {self.WARN};")
            self.image_label.setVisible(True)
            return

        self._diagram_pixmap = pix
        self.image_label.setStyleSheet("")  # reset any warning style
        self.image_label.setVisible(True)

        self._auto_resize_for_diagram()
        self._render_diagram()

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self.image_label.isVisible():
            self._render_diagram()

    def _set_buttons_enabled(self, enabled: bool):
        for b in self.choice_buttons:
            b.setEnabled(enabled)

    def _reset_choice_styles(self):
        # Restore baseline style sheet by clearing per-widget style overrides
        for b in self.choice_buttons:
            b.setStyleSheet("")
        self._feedback_active = False
        self._correct_index = None

    def set_question(self, q: Question, source: str = "local", ai_mode: str = "off", snooze_minutes: int = 10):
        self.current_question = q
        self._reset_choice_styles()
        self._set_buttons_enabled(True)

        self.title.setText("BrainBuff")
        self.meta.setText(f"Topic: {q.topic} • Difficulty: {q.difficulty} • Source: {source.upper()}")
        self.question_label.setText(q.question)

        img_path = getattr(q, "image", None)
        self._set_image(img_path)

        for i, choice in enumerate(q.choices[:4]):
            self.choice_buttons[i].setText(f"{i+1}) {choice}")

        self.hint.setText(
            f"Click choices • (Full app: 1–4 answer, F9 snooze {snooze_minutes}m, F10 mode {ai_mode.upper()})"
        )

        QtCore.QTimer.singleShot(0, self._render_diagram)

    def show_feedback(self, correct: bool, explanation: str = ""):
        """
        Update hint styling + lock choices briefly.
        If possible, highlight correct answer (and user's wrong if available).
        """
        # hint text
        if correct:
            self.hint.setText("✅ Correct! " + (explanation or ""))
            self.hint.setStyleSheet(f"color: {self.GOOD}; font-size: 12px;")
        else:
            self.hint.setText("❌ Not quite. " + (explanation or ""))
            self.hint.setStyleSheet(f"color: {self.BAD}; font-size: 12px;")

        # Highlight correct answer if known
        if self.current_question is not None:
            self._correct_index = int(self.current_question.answer_index)

            for i, b in enumerate(self.choice_buttons):
                if i == self._correct_index:
                    b.setStyleSheet(f"""
                        background: rgba(34, 197, 94, 55);
                        border: 1px solid rgba(34, 197, 94, 180);
                        color: {self.TEXT_MAIN};
                        border-radius: 12px;
                        padding: 10px 12px;
                        text-align: left;
                    """)
        # Prevent double-click spam after answer
        self._set_buttons_enabled(False)
        self._feedback_active = True


# -------------------- Standalone demo --------------------

def demo_main():
    app = QtWidgets.QApplication([])

    overlay = OverlayWindow()

    sample = Question(
        topic="Geometry",
        difficulty="medium",
        question="Demo: The figure is made up of two squares and one quarter circle...",
        image="images/Q5.png",
        choices=["19.5 cm", "25 cm", "25.5 cm", "31 cm"],
        answer_index=2,
        explanation="Perimeter includes straight edges and the quarter-circle arc."
    )

    def on_answer(idx: int):
        overlay.show_feedback(idx == sample.answer_index, sample.explanation)

    overlay.set_answer_handler(on_answer)
    overlay.set_question(sample, source="local", ai_mode="off", snooze_minutes=10)
    overlay.show()

    app.exec()


if __name__ == "__main__":
    demo_main()
