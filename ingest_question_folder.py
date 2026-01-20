# ingest_question_folder_gui_free.py
import json
import os
import re
from pathlib import Path
from typing import Optional

# =========================
# CONFIG (edit these)
# =========================
INPUT_FOLDER = "cropped_questions"     # folder of images
OUTPUT_JSON = "questions.json"         # output bank
ANSWERS_JSON = None                    # e.g. "answers_map.json" or None

DEFAULT_TOPIC = "PSLE"
DEFAULT_DIFFICULTY = "easy"

QID_MODE = "sequence"                  # "sequence" or "filename"
START_QID = 1
OVERWRITE_EXISTING = False

# --- Renaming ---
RENAME_FILES = True                    # rename images while ingesting
RENAME_PREFIX = "Q"                    # Q001.png
RENAME_PAD = 3                         # 3 -> Q001, 4 -> Q0001
RENAME_ONLY_ON_SUCCESS = True          # rename only if OCR+parse succeeded
# =========================

OPT_RE = re.compile(r"^\s*[\(\[]?\s*([1-4])\s*[\)\]]\s*(.*)$")
LEADING_QNUM_RE = re.compile(r"^\s*(?:Q\s*)?\d{1,4}\s*[.)]\s*")
FILENAME_QID_RE = re.compile(r"(?:^|[^0-9])(?:Q)?(\d{1,4})(?:[^0-9]|$)", re.IGNORECASE)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Global OCR instance (reuse = faster + fewer weird issues)
_OCR = None


def _make_ocr():
    from paddleocr import PaddleOCR
    try:
        # Newer versions
        return PaddleOCR(lang="en", use_textline_orientation=True)
    except TypeError:
        # Older versions
        return PaddleOCR(lang="en", use_angle_cls=True)


def ocr_image_lines(img_path: str) -> list[str]:
    """
    OCR the image and return ordered lines (top->bottom).

    NOTE:
    - New PaddleOCR: use_textline_orientation replaces use_angle_cls
    - DO NOT pass cls=True (deprecated / incompatible)
    """
    global _OCR
    import cv2

    if _OCR is None:
        _OCR = _make_ocr()

    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError(f"Could not read image: {img_path}")

    # Most compatible call:
    # Some PaddleOCR versions accept image array, some accept path.
    try:
        result = _OCR.ocr(img)
    except Exception:
        result = _OCR.ocr(img_path)

    # Common format: [ [ [box, (text, conf)], ... ] ]
    lines = []
    if result and isinstance(result, list):
        # Some versions wrap once more
        blocks = result[0] if (len(result) == 1 and isinstance(result[0], list)) else result
        for block in blocks:
            try:
                # v2: [box, (text, conf)]
                text = block[1][0]
                if text and str(text).strip():
                    lines.append(str(text).strip())
            except Exception:
                # v3 could be dict-like or different shapes; ignore silently
                continue

    return lines


def qid_from_filename(stem: str) -> Optional[int]:
    m = FILENAME_QID_RE.search(stem)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def parse_question(lines: list[str]) -> tuple[str, list[str]]:
    stem_parts: list[str] = []
    choices = ["", "", "", ""]
    opt_started = False
    last_touched_opt = None  # last option index we saw (0..3)

    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue

        mopt = OPT_RE.match(ln)
        if mopt:
            opt_started = True
            opt_num = int(mopt.group(1))  # 1..4
            opt_text = mopt.group(2).strip()
            idx = opt_num - 1
            choices[idx] = opt_text
            last_touched_opt = idx
            continue

        if not opt_started:
            ln = LEADING_QNUM_RE.sub("", ln).strip()
            if ln:
                stem_parts.append(ln)
        else:
            # Append wrapped text to last touched option
            if last_touched_opt is None:
                last_touched_opt = 0
            choices[last_touched_opt] = (choices[last_touched_opt] + " " + ln).strip()

    stem = " ".join(stem_parts).strip()
    if not stem:
        raise ValueError("Could not parse question stem from OCR.")
    if any(not c.strip() for c in choices):
        raise ValueError(f"Could not parse all 4 choices. Got: {choices}")

    return stem, choices


def load_json_list(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_answers_map(path: Optional[str]) -> dict[str, int]:
    if not path:
        return {}
    if not os.path.exists(path):
        raise FileNotFoundError(f"answers map not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("answers map must be a JSON object/dict")

    out = {}
    for k, v in obj.items():
        try:
            out[str(int(k))] = int(v)
        except Exception:
            continue
    return out


def _target_name_for_qid(qid: int, suffix: str) -> str:
    return f"{RENAME_PREFIX}{qid:0{RENAME_PAD}d}{suffix.lower()}"


def rename_image_file(img_file: Path, qid: int) -> Path:
    """
    Rename img_file to Q###.ext in the same folder.
    Collision-safe: if target exists and isn't the same file, we skip renaming.
    Returns the final path (renamed or original).
    """
    target_name = _target_name_for_qid(qid, img_file.suffix)
    target_path = img_file.with_name(target_name)

    # Already correct name
    if img_file.name == target_name:
        return img_file

    # Collision safety
    if target_path.exists():
        # If it points to same file (rare), ok; otherwise warn and keep original.
        if target_path.resolve() != img_file.resolve():
            print(f"[WARN] Rename collision: {img_file.name} -> {target_name} already exists. Keeping original.")
            return img_file

    try:
        img_file.rename(target_path)
        print(f"[RENAME] {img_file.name} -> {target_path.name}")
        return target_path
    except Exception as e:
        print(f"[WARN] Failed to rename {img_file.name} -> {target_name}: {e}")
        return img_file


def main():
    base = Path(__file__).resolve().parent
    in_dir = (base / INPUT_FOLDER).resolve()
    out_path = (base / OUTPUT_JSON).resolve()
    ans_path = (base / ANSWERS_JSON).resolve() if ANSWERS_JSON else None

    if not in_dir.exists() or not in_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {in_dir}")

    answers_map = load_answers_map(str(ans_path)) if ans_path else {}

    bank = load_json_list(str(out_path))
    existing_by_qid = {}
    for i, q in enumerate(bank):
        if isinstance(q, dict) and isinstance(q.get("qid"), int):
            existing_by_qid[q["qid"]] = i

    files = sorted([p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS])

    added = updated = skipped = errors = 0
    next_qid = START_QID

    for img_file in files:
        try:
            # Assign qid
            if QID_MODE == "filename":
                qid = qid_from_filename(img_file.stem)
                if qid is None:
                    raise ValueError(f"No qid in filename: {img_file.name}")
            else:
                qid = next_qid
                next_qid += 1

            # OCR + parse
            lines = ocr_image_lines(str(img_file))
            stem, choices = parse_question(lines)

            # Resolve answer if answer map given (1-4 -> 0-3)
            answer_index = -1
            if str(qid) in answers_map:
                v = int(answers_map[str(qid)])
                if 1 <= v <= 4:
                    answer_index = v - 1

            # Rename (optional)
            final_img = img_file
            if RENAME_FILES and (not RENAME_ONLY_ON_SUCCESS or True):
                # only rename after OCR+parse success
                final_img = rename_image_file(img_file, qid)

            item = {
                "qid": qid,
                "topic": DEFAULT_TOPIC,
                "difficulty": DEFAULT_DIFFICULTY,
                "question": stem,
                "choices": choices,
                "answer_index": answer_index,
                "explanation": "",
                "image": None,
                # store the relative path of the (possibly renamed) file
                "source_image": os.path.relpath(str(final_img), start=str(out_path.parent)),
            }

            if qid in existing_by_qid:
                if OVERWRITE_EXISTING:
                    bank[existing_by_qid[qid]] = item
                    updated += 1
                else:
                    skipped += 1
            else:
                bank.append(item)
                existing_by_qid[qid] = len(bank) - 1
                added += 1

            print(f"[OK] {final_img.name} -> qid={qid}")

        except Exception as e:
            errors += 1
            # If you want rename even on error, set RENAME_ONLY_ON_SUCCESS=False and move rename earlier.
            print(f"[ERR] {img_file.name}: {e}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print("\n===== Summary =====")
    print("files:", len(files))
    print("added:", added, "updated:", updated, "skipped:", skipped, "errors:", errors)
    print("output:", out_path)


if __name__ == "__main__":
    main()
