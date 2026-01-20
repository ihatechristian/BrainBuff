from __future__ import annotations

import json
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6 import QtWidgets, QtCore


# -----------------------------
# Paths (saves the settings into settings.json)
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
GAME_MAIN = PROJECT_ROOT / "demo_game" / "main.py"
OVERLAY_MAIN = PROJECT_ROOT / "overlay_trigger.py"

EDITABLE_KEYS = [
    "activity_window_sec",
    "low_activity_threshold",
    "high_activity_spike_threshold",
    "cooldown_sec",
    "snooze_minutes",
    "max_popups_per_hour",
]


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
            return  # already exited

        proc.terminate()

        # wait up to 1s
        t0 = time.time()
        while time.time() - t0 < 1.0:
            if proc.poll() is not None:
                return
            time.sleep(0.05)

        # force kill if needed
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
        self.setMinimumWidth(520)

        self.settings = load_settings()

        title = QtWidgets.QLabel("Overlay Settings")
        title.setObjectName("dlgTitle")

        subtitle = QtWidgets.QLabel("Edits settings.json for BrainBuff overlay behaviour.")
        subtitle.setObjectName("dlgSub")

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.inputs: Dict[str, QtWidgets.QSpinBox] = {}

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
        }

        for key in EDITABLE_KEYS:
            spin = QtWidgets.QSpinBox()
            lo, hi = ranges[key]
            spin.setRange(lo, hi)
            spin.setValue(int(self.settings.get(key, 0)))
            spin.setObjectName("spin")
            self.inputs[key] = spin
            form.addRow(QtWidgets.QLabel(labels[key]), spin)

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
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addLayout(form)
        layout.addSpacing(10)
        layout.addLayout(btn_row)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        self.setStyleSheet(DIALOG_QSS)

    def save(self):
        for key, widget in self.inputs.items():
            self.settings[key] = int(widget.value())
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

        # Track child processes so Quit can stop them
        self.game_proc: Optional[subprocess.Popen] = None
        self.overlay_proc: Optional[subprocess.Popen] = None

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
        btn_settings = QtWidgets.QPushButton("Settings")
        btn_quit = QtWidgets.QPushButton("Quit")

        btn_start_game.setObjectName("btnPrimary")
        btn_start_overlay.setObjectName("btnPrimaryAlt")
        btn_settings.setObjectName("btnSecondary")
        btn_quit.setObjectName("btnGhost")

        for b in (btn_start_game, btn_start_overlay, btn_settings):
            b.setMinimumHeight(52)
        btn_quit.setMinimumHeight(44)

        btn_start_game.clicked.connect(self.start_game)
        btn_start_overlay.clicked.connect(self.start_overlay)
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
        card_layout.addWidget(btn_settings)
        card_layout.addSpacing(6)
        card_layout.addWidget(btn_quit)

        hint = QtWidgets.QLabel(f"Using {SETTINGS_PATH.name}")
        hint.setObjectName("hint")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        card_layout.addWidget(hint)

        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.addStretch()
        root_layout.addWidget(card, alignment=QtCore.Qt.AlignCenter)
        root_layout.addStretch()

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        self.setStyleSheet(LAUNCHER_QSS)

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def start_game(self):
        if not GAME_MAIN.exists():
            QtWidgets.QMessageBox.critical(self, "Error", "Game not found.")
            return

        # If already running, don’t start another
        if self.game_proc is not None and self.game_proc.poll() is None:
            QtWidgets.QMessageBox.information(self, "Game Running", "Game is already running.")
            return

        self.game_proc = subprocess.Popen(
            [sys.executable, str(GAME_MAIN)],
            cwd=str(PROJECT_ROOT),
        )

    def start_overlay(self):
        if not OVERLAY_MAIN.exists():
            QtWidgets.QMessageBox.critical(self, "Error", "overlay_trigger.py not found.")
            return

        # If already running, don’t start another
        if self.overlay_proc is not None and self.overlay_proc.poll() is None:
            QtWidgets.QMessageBox.information(self, "Overlay Running", "Overlay is already running.")
            return

        self.overlay_proc = subprocess.Popen(
            [sys.executable, str(OVERLAY_MAIN)],
            cwd=str(PROJECT_ROOT),
        )

    def quit_everything(self):
        # Stop overlay + game, then close launcher
        terminate_process(self.overlay_proc, "overlay")
        terminate_process(self.game_proc, "game")
        self.overlay_proc = None
        self.game_proc = None
        QtWidgets.QApplication.quit()

    def closeEvent(self, event):
        # If user clicks the window X, also stop everything
        self.quit_everything()
        event.accept()


# -----------------------------
# Styles
# -----------------------------
LAUNCHER_QSS = """
#root {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0B1220,
        stop:1 #111827
    );
}

#card {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 22px;
    min-width: 440px;
}

#title {
    color: #E5E7EB;
    font-size: 36px;
    font-weight: 900;
}

#subtitle {
    color: rgba(229, 231, 235, 0.70);
    font-size: 14px;
}

#hint {
    color: rgba(229, 231, 235, 0.55);
    font-size: 12px;
}

QPushButton {
    border-radius: 14px;
    font-size: 14px;
    font-weight: 800;
    padding: 12px;
}

#btnPrimary {
    background: #3B82F6;
    color: #0B1220;
}

#btnPrimaryAlt {
    background: #22C55E;
    color: #052e16;
}

#btnSecondary {
    background: rgba(255, 255, 255, 0.12);
    color: #E5E7EB;
}

#btnGhost {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(229, 231, 235, 0.85);
}
"""

DIALOG_QSS = """
#dlgCard {
    background: rgba(17, 24, 39, 235);
    border-radius: 16px;
}

#dlgTitle {
    color: #E5E7EB;
    font-size: 18px;
    font-weight: 900;
}

#dlgSub {
    color: rgba(229, 231, 235, 0.70);
    font-size: 12px;
}
"""


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
