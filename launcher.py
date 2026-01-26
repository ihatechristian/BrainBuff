from __future__ import annotations

import json
import sys
import subprocess
import time
from typing import Dict, Any, Optional

from PySide6 import QtWidgets, QtCore

from styles import APP_QSS
from bb_paths import (
    PROJECT_ROOT,
    SETTINGS_PATH,
    QUESTIONS_PATH,
    GAME_MAIN,
    OVERLAY_MAIN,
)

from add_questions_page import AddQuestionsPage


EDITABLE_KEYS_NUMERIC = [
    "activity_window_sec",
    "low_activity_threshold",
    "high_activity_spike_threshold",
    "cooldown_sec",
    "snooze_minutes",
    "max_popups_per_hour",
]


# -----------------------------
# Settings helpers
# -----------------------------
def load_settings() -> Dict[str, Any]:
    if not SETTINGS_PATH.exists():
        raise FileNotFoundError(f"settings.json not found at: {SETTINGS_PATH}")
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("settings.json is not a JSON object")
    return data


def save_settings(data: Dict[str, Any]) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def terminate_process(proc: Optional[subprocess.Popen], name: str = "process") -> None:
    """Try graceful terminate, then force kill if still alive."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        t0 = time.time()
        while time.time() - t0 < 1.0:
            if proc.poll() is not None:
                return
            time.sleep(0.05)
        proc.kill()
    except Exception as e:
        print(f"Failed to stop {name}: {e}")


# -----------------------------
# Settings Dialog
# -----------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay Settings")
        self.setModal(True)
        self.setMinimumWidth(560)

        self.settings = load_settings()

        title = QtWidgets.QLabel("Overlay Settings")
        title.setObjectName("dlgTitle")

        subtitle = QtWidgets.QLabel("Edits settings.json for BrainBuff overlay behaviour.")
        subtitle.setObjectName("dlgSub")

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.spin_inputs: Dict[str, QtWidgets.QSpinBox] = {}
        self.combo_ai: QtWidgets.QComboBox
        self.combo_cluster: QtWidgets.QComboBox

        ranges = {
            "activity_window_sec": (1, 60),
            "low_activity_threshold": (0, 9999),
            "high_activity_spike_threshold": (0, 9999),
            "cooldown_sec": (0, 3600),
            "snooze_minutes": (0, 180),
            "max_popups_per_hour": (0, 999999),
        }

        labels = {
            "activity_window_sec": "Activity window (sec)",
            "low_activity_threshold": "Low activity threshold",
            "high_activity_spike_threshold": "High activity spike threshold",
            "cooldown_sec": "Cooldown (sec)",
            "snooze_minutes": "Snooze (minutes)",
            "max_popups_per_hour": "Max popups per hour",
            "ai_mode": "AI mode",
            "cluster_mode": "Cluster mode",
        }

        for key in EDITABLE_KEYS_NUMERIC:
            spin = QtWidgets.QSpinBox()
            lo, hi = ranges[key]
            spin.setRange(lo, hi)
            spin.setValue(int(self.settings.get(key, 0)))
            spin.setObjectName("spin")
            self.spin_inputs[key] = spin
            form.addRow(QtWidgets.QLabel(labels[key]), spin)

        self.combo_ai = QtWidgets.QComboBox()
        self.combo_ai.setObjectName("combo")
        self.combo_ai.addItems(["off", "on"])
        ai_cur = str(self.settings.get("ai_mode", "off")).strip().lower()
        ai_cur = "on" if ai_cur not in ("off", "on") else ai_cur
        ai_idx = self.combo_ai.findText(ai_cur)
        self.combo_ai.setCurrentIndex(ai_idx if ai_idx >= 0 else 0)
        form.addRow(QtWidgets.QLabel(labels["ai_mode"]), self.combo_ai)

        self.combo_cluster = QtWidgets.QComboBox()
        self.combo_cluster.setObjectName("combo")
        self.combo_cluster.addItems(["off", "adaptive"])
        cl_cur = str(self.settings.get("cluster_mode", "off")).strip().lower()
        cl_cur = "adaptive" if cl_cur not in ("off", "adaptive") else cl_cur
        cl_idx = self.combo_cluster.findText(cl_cur)
        self.combo_cluster.setCurrentIndex(cl_idx if cl_idx >= 0 else 0)
        form.addRow(QtWidgets.QLabel(labels["cluster_mode"]), self.combo_cluster)

        hint = QtWidgets.QLabel(
            "Note: AI mode 'on' just enables the AI feature flag. "
            "Your QuestionEngine decides whether it uses cache/live based on your implementation."
        )
        hint.setObjectName("dlgHint")
        hint.setWordWrap(True)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_save = QtWidgets.QPushButton("Save")
        btn_cancel.setObjectName("btnSecondary")
        btn_save.setObjectName("btnPrimary")

        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self.save)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)

        card = QtWidgets.QFrame()
        card.setObjectName("dlgCard")

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(6)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addSpacing(6)
        layout.addLayout(btn_row)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)


    def save(self):
        for key, widget in self.spin_inputs.items():
            self.settings[key] = int(widget.value())
        self.settings["ai_mode"] = self.combo_ai.currentText().strip().lower()
        self.settings["cluster_mode"] = self.combo_cluster.currentText().strip().lower()
        save_settings(self.settings)
        self.accept()


# -----------------------------
# Launcher
# -----------------------------
class Launcher(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainBuff Launcher")
        self.setMinimumSize(820, 560)

        self.game_proc: Optional[subprocess.Popen] = None
        self.overlay_proc: Optional[subprocess.Popen] = None

        self.stack = QtWidgets.QStackedWidget()
        self.home_page = self._build_home_page()
        self.add_page = AddQuestionsPage(on_back=self.show_home)

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.add_page)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)


    def _build_home_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()

        root = QtWidgets.QFrame()
        root.setObjectName("root")

        card = QtWidgets.QFrame()
        card.setObjectName("card")

        title = QtWidgets.QLabel("BrainBuff")
        title.setObjectName("title")
        title.setAlignment(QtCore.Qt.AlignCenter)

        subtitle = QtWidgets.QLabel("Education overlay + survivor-style demo")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)

        btn_start_game = QtWidgets.QPushButton("Start Game")
        btn_start_overlay = QtWidgets.QPushButton("Start Overlay Only")
        btn_add_questions = QtWidgets.QPushButton("Add Questions")
        btn_settings = QtWidgets.QPushButton("Settings")
        btn_quit = QtWidgets.QPushButton("Quit")

        btn_start_game.setObjectName("btnPrimary")
        btn_start_overlay.setObjectName("btnPrimaryAlt")
        btn_add_questions.setObjectName("btnSecondary")
        btn_settings.setObjectName("btnSecondary")
        btn_quit.setObjectName("btnGhost")

        for b in (btn_start_game, btn_start_overlay, btn_add_questions, btn_settings):
            b.setMinimumHeight(52)
        btn_quit.setMinimumHeight(44)

        btn_start_game.clicked.connect(self.start_game)
        btn_start_overlay.clicked.connect(self.start_overlay)
        btn_add_questions.clicked.connect(self.show_add_questions)
        btn_settings.clicked.connect(self.open_settings)
        btn_quit.clicked.connect(self.quit_everything)

        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 24)
        card_layout.setSpacing(14)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(10)

        card_layout.addWidget(btn_start_game)
        card_layout.addWidget(btn_start_overlay)
        card_layout.addWidget(btn_add_questions)
        card_layout.addWidget(btn_settings)
        card_layout.addSpacing(6)
        card_layout.addWidget(btn_quit)

        hint = QtWidgets.QLabel(f"Using {SETTINGS_PATH.name} • Bank: {QUESTIONS_PATH.name}")
        hint.setObjectName("hint")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.addStretch()
        root_layout.addWidget(card, alignment=QtCore.Qt.AlignCenter)
        root_layout.addStretch()

        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        return page

    def show_home(self):
        self.stack.setCurrentIndex(0)

    def show_add_questions(self):
        self.stack.setCurrentIndex(1)

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def start_game(self):
        if not GAME_MAIN.exists():
            QtWidgets.QMessageBox.critical(self, "Error", "Game not found.")
            return
        if self.game_proc is not None and self.game_proc.poll() is None:
            QtWidgets.QMessageBox.information(self, "Game Running", "Game is already running.")
            return
        self.game_proc = subprocess.Popen([sys.executable, str(GAME_MAIN)], cwd=str(PROJECT_ROOT))

    def start_overlay(self):
        if not OVERLAY_MAIN.exists():
            QtWidgets.QMessageBox.critical(self, "Error", "overlay_trigger.py not found.")
            return
        if self.overlay_proc is not None and self.overlay_proc.poll() is None:
            QtWidgets.QMessageBox.information(self, "Overlay Running", "Overlay is already running.")
            return
        self.overlay_proc = subprocess.Popen([sys.executable, str(OVERLAY_MAIN)], cwd=str(PROJECT_ROOT))

    def quit_everything(self):
        terminate_process(self.overlay_proc, "overlay")
        terminate_process(self.game_proc, "game")
        self.overlay_proc = None
        self.game_proc = None
        QtWidgets.QApplication.quit()

    def closeEvent(self, event):
        self.quit_everything()
        event.accept()





def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)   # ✅ applies to ALL windows/dialogs/pages

    win = Launcher()
    win.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
