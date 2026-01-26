from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from PySide6 import QtWidgets, QtCore

from bb_paths import PROJECT_ROOT, QUESTIONS_PATH, CROPPED_DIR, IMAGES_DIR


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

                if dest.exists() and dest.resolve() != src.resolve():
                    dest = CROPPED_DIR / f"{dest.stem}_{int(time.time())}{dest.suffix}"

                shutil.copy2(str(src), str(dest))
                copied += 1

            self.status.setText(
                f"✅ Copied {copied} image(s) into {CROPPED_DIR.name}/. Now run your ingest script."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Copy failed", str(e))
