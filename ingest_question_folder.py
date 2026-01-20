# ingest_question_folder_gui_free.py
import json
import os
import re
from pathlib import Path

# =========================
# CONFIG (edit these) hi
# =========================
INPUT_FOLDER = "cropped_questions"     # folder of images
OUTPUT_JSON = "questions.json"         # output bank
ANSWERS_JSON = None                    # e.g. "answers_map.json" or None
DEFAULT_TOPIC = "PSLE"
DEFAULT_DIFFICULTY = "easy"
QID_MODE = "sequence"                  # "sequence" or "filename"
START_QID = 1
OVERWRITE_EXISTING = False
# =========================

OPT_RE = re.compile(r"^\s*[\(\[]?\s*([1-4])\s*[\)\]]\s*(.*)$")
LEADING_QNUM_RE = re.compile(r"^\s*(?:Q\s*)?\d{1,4}\s*[.)]\s*")
FILENAME_QID_RE = re.compile(r"(?:^|[^0-9])(?:Q)?(\d{1,4})(?:[^0-9]|$)", re.IGNORECASE)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def ocr_image_lines(img_path: str) -> list[str]:
    """
    OCR the image and return ordered lines (top->bottom).

    New PaddleOCR API:
    - use_textline_orientation replaces use_angle_cls
    - do NOT pass cls=True to ocr()
    """
    from paddleocr import PaddleOCR
    import cv2

    ocr = PaddleOCR(
        lang="en",
        use_textline_orientation=True,   # replaces use_angle_cls
    )

    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError(f"Could not read image: {img_path}")

    # IMPORTANT: no cls=True here
    result = ocr.ocr(img)

    # result format (common): [ [ [box, (text, conf)], ... ] ]
    lines = []
    if result and isinstance(result, list) and result[0]:
        for block in result[0]:
            try:
                text = block[1][0]
                if text and str(text).strip():
                    lines.append(str(text).strip())
            except Exception:
                continue

    return lines


def qid_from_filename(stem: str) -> int | None:
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


def load_answers_map(path: str | None) -> dict[str, int]:
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
        if isinstance(q.get("qid"), int):
            existing_by_qid[q["qid"]] = i

    files = sorted([p for p in in_dir.iterdir() if p.suffix.lower() in IMG_EXTS])

    added = updated = skipped = errors = 0
    next_qid = START_QID

    for img_file in files:
        try:
            if QID_MODE == "filename":
                qid = qid_from_filename(img_file.stem)
                if qid is None:
                    raise ValueError(f"No qid in filename: {img_file.name}")
            else:
                qid = next_qid
                next_qid += 1

            lines = ocr_image_lines(str(img_file))
            stem, choices = parse_question(lines)

            answer_index = -1
            if str(qid) in answers_map:
                v = int(answers_map[str(qid)])
                if 1 <= v <= 4:
                    answer_index = v - 1

            item = {
                "qid": qid,
                "topic": DEFAULT_TOPIC,
                "difficulty": DEFAULT_DIFFICULTY,
                "question": stem,
                "choices": choices,
                "answer_index": answer_index,
                "explanation": "",
                "image": None,
                "source_image": os.path.relpath(str(img_file), start=str(out_path.parent)),
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

            print(f"[OK] {img_file.name} -> qid={qid}")

        except Exception as e:
            errors += 1
            print(f"[ERR] {img_file.name}: {e}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print("\n===== Summary =====")
    print("files:", len(files))
    print("added:", added, "updated:", updated, "skipped:", skipped, "errors:", errors)
    print("output:", out_path)


if __name__ == "__main__":
    main()
