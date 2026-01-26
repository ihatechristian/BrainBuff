from __future__ import annotations

import json
import sys
import subprocess
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

from PySide6 import QtWidgets, QtCore


# -----------------------------
# Paths (project-relative)
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
QUESTIONS_PATH = PROJECT_ROOT / "questions.json"
CROPPED_DIR = PROJECT_ROOT / "cropped_questions"
IMAGES_DIR = PROJECT_ROOT / "images"

GAME_MAIN = PROJECT_ROOT / "demo_game" / "main.py"
OVERLAY_MAIN = PROJECT_ROOT / "overlay_trigger.py"


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
# Question bank helpers
# -----------------------------
def load_question_bank() -> List[Dict[str, Any]]:
    if not QUESTIONS_PATH.exists():
        return []
    try:
        data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_question_bank(bank: List[Dict[str, Any]]) -> None:
    QUESTIONS_PATH.write_text(json.dumps(bank, indent=2, ensure_ascii=False), encoding="utf-8")


def next_qid(bank: List[Dict[str, Any]]) -> int:
    mx = 0
    for q in bank:
        try:
            mx = max(mx, int(q.get("qid", 0)))
        except Exception:
            pass
    return mx + 1 if mx > 0 else 1


def normalize_question_obj(obj: Dict[str, Any], qid: Optional[int] = None) -> Dict[str, Any]:
    """
    Ensure a question dict has all required keys.
    Minimal schema used by your engine:
      qid, topic, difficulty, question, choices[4], answer_index, explanation, image
    """
    topic = str(obj.get("topic", "")).strip() or "PSLE"
    difficulty = str(obj.get("difficulty", "")).strip() or "easy"
    question = str(obj.get("question", "")).strip()
    choices = obj.get("choices", [])
    if not isinstance(choices, list):
        choices = []
    choices = [str(c).strip() for c in choices][:4]
    while len(choices) < 4:
        choices.append("")

    ans = obj.get("answer_index", -1)
    try:
        ans = int(ans)
    except Exception:
        ans = -1
    if ans not in (-1, 0, 1, 2, 3):
        ans = -1

    explanation = str(obj.get("explanation", "") or "").strip()
    image = obj.get("image", None)
    image = None if (image is None or str(image).strip() == "") else str(image).strip()

    out = {
        "qid": int(qid) if qid is not None else int(obj.get("qid", -1) or -1),
        "topic": topic,
        "difficulty": difficulty,
        "question": question,
        "choices": choices,
        "answer_index": ans,
        "explanation": explanation,
        "image": image,
    }

    # keep optional fields if present
    if "source_image" in obj:
        out["source_image"] = obj.get("source_image")
    if "needs_review" in obj:
        out["needs_review"] = bool(obj.get("needs_review"))

    # basic validation
    if not out["question"]:
        raise ValueError("Question text is empty.")
    if len(out["choices"]) != 4 or any(not c for c in out["choices"]):
        raise ValueError("Choices must be 4 non-empty strings.")
    if out["answer_index"] not in (-1, 0, 1, 2, 3):
        raise ValueError("answer_index must be -1 or 0..3.")

    return out


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

        self.setStyleSheet(DIALOG_QSS)

    def save(self):
        for key, widget in self.spin_inputs.items():
            self.settings[key] = int(widget.value())
        self.settings["ai_mode"] = self.combo_ai.currentText().strip().lower()
        self.settings["cluster_mode"] = self.combo_cluster.currentText().strip().lower()
        save_settings(self.settings)
        self.accept()


# -----------------------------
# Add Questions Page
# -----------------------------
class AddQuestionsPage(QtWidgets.QWidget):
    def __init__(self, on_back, parent=None):
        super().__init__(parent)
        self.on_back = on_back

        root = QtWidgets.QFrame()
        root.setObjectName("root")

        card = QtWidgets.QFrame()
        card.setObjectName("cardWide")

        title = QtWidgets.QLabel("Add Questions")
        title.setObjectName("title")
        title.setAlignment(QtCore.Qt.AlignCenter)

        subtitle = QtWidgets.QLabel("Add via form, paste JSON, or import images into cropped_questions/")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)

        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName("tabs")

        tabs.addTab(self._build_manual_tab(), "Manual Form")
        tabs.addTab(self._build_json_tab(), "Paste JSON")
        tabs.addTab(self._build_images_tab(), "Import Images")

        btn_back = QtWidgets.QPushButton("Back")
        btn_back.setObjectName("btnGhost")
        btn_back.clicked.connect(self.on_back)

        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("hint")
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        self.status.setWordWrap(True)

        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(28, 28, 28, 24)
        v.setSpacing(14)
        v.addWidget(title)
        v.addWidget(subtitle)
        v.addWidget(tabs)
        v.addWidget(self.status)
        v.addWidget(btn_back, alignment=QtCore.Qt.AlignCenter)

        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.addStretch()
        root_layout.addWidget(card, alignment=QtCore.Qt.AlignCenter)
        root_layout.addStretch()

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

    # -------- Manual Form --------
    def _build_manual_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.m_topic = QtWidgets.QLineEdit()
        self.m_topic.setPlaceholderText("e.g. Decimals, Geometry, PSLE")
        self.m_topic.setText("PSLE")

        self.m_diff = QtWidgets.QComboBox()
        self.m_diff.addItems(["easy", "medium", "hard"])
        self.m_diff.setCurrentText("easy")

        self.m_question = QtWidgets.QPlainTextEdit()
        self.m_question.setPlaceholderText("Enter the question text (use _____ for blanks if needed)")

        self.m_choices = []
        for i in range(4):
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(f"Choice {i+1}")
            self.m_choices.append(le)

        self.m_answer = QtWidgets.QComboBox()
        self.m_answer.addItems(["-1 (unknown)", "0", "1", "2", "3"])

        self.m_expl = QtWidgets.QPlainTextEdit()
        self.m_expl.setPlaceholderText("Optional explanation")

        # Optional diagram image (goes into /images and sets `image`)
        img_row = QtWidgets.QHBoxLayout()
        self.m_image_path = QtWidgets.QLineEdit()
        self.m_image_path.setReadOnly(True)
        btn_browse = QtWidgets.QPushButton("Browse Image…")
        btn_browse.setObjectName("btnSecondary")
        btn_browse.clicked.connect(self._browse_manual_image)
        img_row.addWidget(self.m_image_path)
        img_row.addWidget(btn_browse)

        form.addRow("Topic", self.m_topic)
        form.addRow("Difficulty", self.m_diff)
        form.addRow("Question", self.m_question)
        form.addRow("Choice 1", self.m_choices[0])
        form.addRow("Choice 2", self.m_choices[1])
        form.addRow("Choice 3", self.m_choices[2])
        form.addRow("Choice 4", self.m_choices[3])
        form.addRow("Answer index", self.m_answer)
        form.addRow("Explanation", self.m_expl)
        form.addRow("Diagram (optional)", img_row)

        btn_add = QtWidgets.QPushButton("Add to questions.json")
        btn_add.setObjectName("btnPrimary")
        btn_add.clicked.connect(self._manual_add_clicked)

        layout.addLayout(form)
        layout.addWidget(btn_add, alignment=QtCore.Qt.AlignRight)
        return w

    def _browse_manual_image(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select diagram image",
            str(PROJECT_ROOT),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if fn:
            self.m_image_path.setText(fn)

    def _manual_add_clicked(self):
        try:
            bank = load_question_bank()
            qid = next_qid(bank)

            img_rel = None
            img_src = self.m_image_path.text().strip()
            if img_src:
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                src = Path(img_src)
                dest = IMAGES_DIR / src.name
                # avoid overwriting with different file
                if dest.exists() and dest.resolve() != src.resolve():
                    dest = IMAGES_DIR / f"{qid}_{src.name}"
                shutil.copy2(str(src), str(dest))
                img_rel = str(dest.relative_to(PROJECT_ROOT)).replace("\\", "/")

            obj = {
                "qid": qid,
                "topic": self.m_topic.text().strip() or "PSLE",
                "difficulty": self.m_diff.currentText().strip(),
                "question": self.m_question.toPlainText().strip(),
                "choices": [c.text().strip() for c in self.m_choices],
                "answer_index": int(self.m_answer.currentText().split()[0]),
                "explanation": self.m_expl.toPlainText().strip(),
                "image": img_rel,
            }

            q = normalize_question_obj(obj, qid=qid)
            bank.append(q)
            save_question_bank(bank)

            self.status.setText(f"✅ Added qid={qid} to {QUESTIONS_PATH.name}")
            # clear
            self.m_question.setPlainText("")
            for c in self.m_choices:
                c.setText("")
            self.m_expl.setPlainText("")
            self.m_image_path.setText("")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Add failed", str(e))

    # -------- Paste JSON --------
    def _build_json_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        info = QtWidgets.QLabel(
            "Paste a single question object OR a list of objects.\n"
            "Required: topic, difficulty, question, choices (4), answer_index (-1 or 0..3)."
        )
        info.setObjectName("hint")
        info.setWordWrap(True)

        self.json_text = QtWidgets.QPlainTextEdit()
        self.json_text.setPlaceholderText(
            '{\n'
            '  "topic": "Decimals",\n'
            '  "difficulty": "easy",\n'
            '  "question": "Calculate 3 + 3/100 + 30/1000.",\n'
            '  "choices": ["3.033", "3.06", "3.33", "3.6"],\n'
            '  "answer_index": 0,\n'
            '  "explanation": "..." ,\n'
            '  "image": null\n'
            '}\n'
        )

        btn_add = QtWidgets.QPushButton("Add JSON to questions.json")
        btn_add.setObjectName("btnPrimary")
        btn_add.clicked.connect(self._add_json_clicked)

        layout.addWidget(info)
        layout.addWidget(self.json_text)
        layout.addWidget(btn_add, alignment=QtCore.Qt.AlignRight)
        return w

    def _add_json_clicked(self):
        try:
            raw = self.json_text.toPlainText().strip()
            if not raw:
                raise ValueError("Paste JSON first.")

            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            if not all(isinstance(x, dict) for x in items):
                raise ValueError("JSON must be an object or list of objects.")

            bank = load_question_bank()
            qid = next_qid(bank)
            added = 0

            for obj in items:
                q = normalize_question_obj(obj, qid=qid)
                bank.append(q)
                qid += 1
                added += 1

            save_question_bank(bank)
            self.status.setText(f"✅ Added {added} question(s) to {QUESTIONS_PATH.name}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Add failed", str(e))

    # -------- Import Images --------
    def _build_images_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        info = QtWidgets.QLabel(
            "This copies images into cropped_questions/ for your OCR ingest script.\n"
            "Optional: auto-rename to Q001.png, Q002.png… based on the next qid in questions.json."
        )
        info.setObjectName("hint")
        info.setWordWrap(True)

        row = QtWidgets.QHBoxLayout()
        btn_pick = QtWidgets.QPushButton("Choose Image Files…")
        btn_pick.setObjectName("btnSecondary")
        btn_pick.clicked.connect(self._pick_images)

        self.chk_rename = QtWidgets.QCheckBox("Auto-rename to Q###.ext")
        self.chk_rename.setChecked(True)

        row.addWidget(btn_pick)
        row.addWidget(self.chk_rename)
        row.addStretch()

        self.img_list = QtWidgets.QListWidget()
        self.img_list.setMinimumHeight(220)

        btn_copy = QtWidgets.QPushButton("Copy into cropped_questions/")
        btn_copy.setObjectName("btnPrimaryAlt")
        btn_copy.clicked.connect(self._copy_images)

        layout.addWidget(info)
        layout.addLayout(row)
        layout.addWidget(self.img_list)
        layout.addWidget(btn_copy, alignment=QtCore.Qt.AlignRight)
        return w

    def _pick_images(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select question images",
            str(PROJECT_ROOT),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not files:
            return
        self.img_list.clear()
        for f in files:
            self.img_list.addItem(f)

    def _copy_images(self):
        try:
            if self.img_list.count() == 0:
                raise ValueError("Pick some images first.")

            CROPPED_DIR.mkdir(parents=True, exist_ok=True)

            bank = load_question_bank()
            qid = next_qid(bank)

            copied = 0
            for i in range(self.img_list.count()):
                src = Path(self.img_list.item(i).text())
                if not src.exists():
                    continue

                suffix = src.suffix.lower()
                if self.chk_rename.isChecked():
                    dest = CROPPED_DIR / f"Q{qid:03d}{suffix}"
                    qid += 1
                else:
                    dest = CROPPED_DIR / src.name

                # avoid overwriting
                if dest.exists() and dest.resolve() != src.resolve():
                    dest = CROPPED_DIR / f"{dest.stem}_{int(time.time())}{dest.suffix}"

                shutil.copy2(str(src), str(dest))
                copied += 1

            self.status.setText(f"✅ Copied {copied} image(s) into {CROPPED_DIR.name}/. Now run your ingest script.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Copy failed", str(e))


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

        self.setStyleSheet(LAUNCHER_QSS)

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

#cardWide {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 22px;
    min-width: 700px;
    max-width: 900px;
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

QTabWidget#tabs::pane {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    top: -1px;
}

QTabBar::tab {
    background: rgba(255,255,255,0.06);
    padding: 10px 14px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    color: rgba(229,231,235,0.85);
    margin-right: 6px;
}

QTabBar::tab:selected {
    background: rgba(255,255,255,0.12);
    color: #E5E7EB;
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

#dlgHint {
    color: rgba(229, 231, 235, 0.55);
    font-size: 11px;
    margin-top: 6px;
}

QComboBox#combo {
    padding: 6px 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.10);
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

QComboBox#combo::drop-down {
    border: none;
}

QComboBox#combo QAbstractItemView {
    background: #111827;
    color: #E5E7EB;
    selection-background-color: rgba(59, 130, 246, 0.35);
}
"""


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
