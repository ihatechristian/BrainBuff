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


# =====================================================
# Mini Calculator (usable: C, backspace, equals, + - × ÷)
# =====================================================
class MiniCalculator(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Ensure it's clickable/usable even with an overlay that doesn't accept focus
        self.setWindowFlags(
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus, False)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setObjectName("calculator")

        self._expr = ""

        self.display = QtWidgets.QLineEdit()
        self.display.setReadOnly(True)
        self.display.setAlignment(QtCore.Qt.AlignRight)
        self.display.setFixedHeight(36)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)

        buttons = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2), ("÷", 0, 3),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2), ("×", 1, 3),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2), ("−", 2, 3),
            ("0", 3, 0), (".", 3, 1), ("⌫", 3, 2), ("+", 3, 3),
            ("C", 4, 0), ("=", 4, 1),
        ]

        for text, r, c in buttons:
            btn = QtWidgets.QPushButton(text)
            btn.setFocusPolicy(QtCore.Qt.NoFocus)  # keep overlay feel
            btn.setFixedSize(44, 44)
            btn.clicked.connect(lambda _, t=text: self._press(t))

            if text == "=":
                grid.addWidget(btn, r, c, 1, 3)  # span 3 columns
            else:
                grid.addWidget(btn, r, c)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.display)
        layout.addLayout(grid)

        # Styling (self-contained)
        self.setStyleSheet("""
            #calculator {
                background: #111827;
                border: 2px solid rgba(255,255,255,0.35);
                border-radius: 16px;
            }
            QLineEdit {
                background: rgba(255,255,255,0.08);
                color: white;
                border-radius: 10px;
                padding: 8px;
                border: 1px solid rgba(255,255,255,0.18);
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton {
                background: rgba(255,255,255,0.10);
                color: white;
                border-radius: 12px;
                font-weight: 800;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.20);
            }
            QPushButton:pressed {
                background: rgba(59,130,246,0.25);
            }
        """)

        self._update_display()

    def _update_display(self):
        self.display.setText(self._expr if self._expr else "0")

    def _to_eval_expr(self) -> str:
        return (
            self._expr
            .replace("×", "*")
            .replace("÷", "/")
            .replace("−", "-")
        )

    def _safe_eval(self, expr: str) -> float:
        allowed = set("0123456789+-*/(). ")
        if any(ch not in allowed for ch in expr):
            raise ValueError("Invalid characters")
        return eval(expr, {"__builtins__": {}}, {})

    def _press(self, t: str):
        if t == "C":
            self._expr = ""
            self._update_display()
            return

        if t == "⌫":
            self._expr = self._expr[:-1]
            self._update_display()
            return

        if t == "=":
            try:
                expr = self._to_eval_expr()
                if not expr.strip():
                    return
                result = self._safe_eval(expr)
                if abs(result - int(result)) < 1e-10:
                    self._expr = str(int(result))
                else:
                    self._expr = str(round(result, 10)).rstrip("0").rstrip(".")
            except Exception:
                self._expr = "Error"
            self._update_display()
            return

        if self._expr == "Error":
            self._expr = ""

        ops = {"+", "−", "×", "÷"}
        if t in ops and (not self._expr or self._expr[-1] in ops):
            return

        self._expr += t
        self._update_display()


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

        # Debug confirm
        print("🔥 NEW OverlayWindow with calculator LOADED")

        # Store the original pixmap for clean rescaling on resize
        self._diagram_pixmap: Optional[QtGui.QPixmap] = None

        # Track current feedback state for button styling
        self._feedback_active = False
        self._correct_index: Optional[int] = None

        # ---- Theme tokens (education overlay) ----
        self.CARD_BG = "rgba(17, 24, 39, 235)"
        self.CARD_BORDER = "rgba(255, 255, 255, 36)"
        self.DIAGRAM_BG = "rgba(255, 255, 255, 10)"
        self.DIAGRAM_BORDER = "rgba(255, 255, 255, 22)"

        self.TEXT_MAIN = "#F9FAFB"
        self.TEXT_SUB = "rgba(156, 163, 175, 220)"
        self.TEXT_HINT = "rgba(156, 163, 175, 200)"

        self.ACCENT = "#3B82F6"
        self.BUTTON_BG = "rgba(31, 41, 55, 210)"
        self.BUTTON_HOVER = "rgba(55, 65, 81, 220)"
        self.BUTTON_BORDER = "rgba(255, 255, 255, 18)"

        self.GOOD = "#22C55E"
        self.BAD = "#F87171"
        self.WARN = "#FBBF24"

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

        # 🧮 Calculator icon/button (always available)
        self.calc_btn = QtWidgets.QToolButton()
        self.calc_btn.setText("🧮")
        self.calc_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.calc_btn.setFixedSize(28, 28)
        self.calc_btn.setToolTip("Calculator")
        self.calc_btn.setStyleSheet("""
            QToolButton {
                background: rgba(255,255,255,0.12);
                border-radius: 8px;
                font-size: 16px;
            }
            QToolButton:hover {
                background: rgba(255,255,255,0.25);
            }
        """)

        self.meta = QtWidgets.QLabel("")
        self.meta.setObjectName("meta")

        self.question_label = QtWidgets.QLabel("")
        self.question_label.setWordWrap(True)
        self.question_label.setObjectName("question")

        # Diagram/image area (NO scroll)
        self.image_label = QtWidgets.QLabel("")
        self.image_label.setObjectName("diagram")
        self.image_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
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

        # Header row: title + calc icon on the right
        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.calc_btn)

        layout.addLayout(header)
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

        # Calculator window
        self.calculator = MiniCalculator(self)
        self.calculator.hide()
        self.calc_btn.clicked.connect(self._toggle_calculator)

        self._apply_styles()

        # Default size (controller can override)
        self.resize(720, 520)

    def _toggle_calculator(self):
        if self.calculator.isVisible():
            self.calculator.hide()
            return

        # place near top-right of overlay
        pos = self.mapToGlobal(QtCore.QPoint(self.width() - 260, 60))
        self.calculator.move(pos)
        self.calculator.show()
        self.calculator.raise_()
        self.calculator.activateWindow()

    def _apply_styles(self):
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
        return os.path.join(os.getcwd(), img_path)

    def _diagram_max_size(self) -> QtCore.QSize:
        screen = QtWidgets.QApplication.primaryScreen()
        if not screen:
            return QtCore.QSize(900, 500)
        geo = screen.availableGeometry()
        max_w = int(geo.width() * 0.80)
        max_h = int(geo.height() * 0.42)
        return QtCore.QSize(max_w, max_h)

    def _available_diagram_box(self) -> QtCore.QSize:
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
        if not self._diagram_pixmap or self._diagram_pixmap.isNull():
            return

        box = self._available_diagram_box()
        cap = self._diagram_max_size()

        target_w = min(box.width(), cap.width())
        target_h = min(box.height(), cap.height())

        scaled = self._diagram_pixmap.scaled(
            target_w,
            target_h,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def _auto_resize_for_diagram(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        max_w = int(geo.width() * 0.90)
        max_h = int(geo.height() * 0.90)

        target_w = min(max_w, max(720, self.width()))
        target_h = min(max_h, max(520, self.height()))

        if self._diagram_pixmap and not self._diagram_pixmap.isNull():
            target_h = min(max_h, max(target_h, int(geo.height() * 0.68)))
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
        self.image_label.setStyleSheet("")
        self.image_label.setVisible(True)

        self._auto_resize_for_diagram()
        QtCore.QTimer.singleShot(0, self._render_diagram)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self.image_label.isVisible():
            self._render_diagram()

    def _set_buttons_enabled(self, enabled: bool):
        for b in self.choice_buttons:
            b.setEnabled(enabled)

    def _reset_choice_styles(self):
        for b in self.choice_buttons:
            b.setStyleSheet("")
        self._feedback_active = False
        self._correct_index = None
        self.hint.setStyleSheet("")

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

        # Calculator ALWAYS available
        self.calc_btn.setVisible(True)

        QtCore.QTimer.singleShot(0, self._render_diagram)

    def show_feedback(self, correct: bool, explanation: str = ""):
        if correct:
            self.hint.setText("✅ Correct! " + (explanation or ""))
            self.hint.setStyleSheet(f"color: {self.GOOD}; font-size: 12px;")
        else:
            self.hint.setText("❌ Not quite. " + (explanation or ""))
            self.hint.setStyleSheet(f"color: {self.BAD}; font-size: 12px;")

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

        self._set_buttons_enabled(False)
        self._feedback_active = True


# -------------------- Standalone demo --------------------
def demo_main():
    app = QtWidgets.QApplication([])

    overlay = OverlayWindow()

    sample = Question(
        topic="Geometry",
        difficulty="medium",
        question="Demo: What is 48 ÷ 6?",
        choices=["6", "7", "8", "9"],
        answer_index=2,
        explanation="48 divided by 6 is 8."
    )

    def on_answer(idx: int):
        overlay.show_feedback(idx == sample.answer_index, sample.explanation)

    overlay.set_answer_handler(on_answer)
    overlay.set_question(sample, source="local", ai_mode="off", snooze_minutes=10)
    overlay.show()

    app.exec()


if __name__ == "__main__":
    demo_main()
