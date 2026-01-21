# ingest_question_folder_gui_free.py
import json
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Optional, List, Tuple

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
RENAME_FILES = True
RENAME_PREFIX = "Q"                    # Q001.png
RENAME_PAD = 3
RENAME_ONLY_ON_SUCCESS = True

# --- OCR logging ---
QUIET_PADDLE = True

# --- Robustness ---
ALLOW_INCOMPLETE_CHOICES = True        # if OCR misses an option, don't crash
MISSING_CHOICE_PLACEHOLDER = "[UNREADABLE]"
# =========================

LEADING_QNUM_RE = re.compile(r"^\s*(?:Q\s*)?\d{1,4}\s*[.)]\s*")
FILENAME_QID_RE = re.compile(r"(?:^|[^0-9])(?:Q)?(\d{1,6})(?:[^0-9]|$)", re.IGNORECASE)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Match option markers anywhere in a line: (2) or [2] or 2)
OPT_ANY_RE = re.compile(r"(\(\s*[1-4]\s*\)|\[\s*[1-4]\s*\]|(?:^|\s)([1-4])\))")

# Global OCR instance
_OCR = None


class _NullWriter:
    def write(self, *_args, **_kwargs): pass
    def flush(self): pass


def _silence_paddle_logs(enable: bool):
    if not enable:
        return
    os.environ.setdefault("GLOG_minloglevel", "3")
    warnings.filterwarnings("ignore")
    try:
        import logging
        logging.getLogger("ppocr").setLevel(logging.ERROR)
        logging.getLogger("paddleocr").setLevel(logging.ERROR)
        logging.getLogger().setLevel(logging.ERROR)
    except Exception:
        pass


def _make_ocr():
    from paddleocr import PaddleOCR
    try:
        return PaddleOCR(lang="en", use_textline_orientation=True)
    except TypeError:
        return PaddleOCR(lang="en", use_angle_cls=True)


def ocr_image_lines(img_path: str) -> List[str]:
    """
    OCR the image and return ordered lines.
    (Using text-only lines here; if you want blank-detection from gaps, we can re-add it later.)
    """
    global _OCR
    import cv2

    if _OCR is None:
        _silence_paddle_logs(QUIET_PADDLE)
        if QUIET_PADDLE:
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = _NullWriter(), _NullWriter()
            try:
                _OCR = _make_ocr()
            finally:
                sys.stdout, sys.stderr = old_out, old_err
        else:
            _OCR = _make_ocr()

    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError(f"Could not read image: {img_path}")

    try:
        result = _OCR.ocr(img)
    except Exception:
        result = _OCR.ocr(img_path)

    lines: List[str] = []
    if result and isinstance(result, list):
        blocks = result[0] if (len(result) == 1 and isinstance(result[0], list)) else result
        for block in blocks:
            try:
                text = block[1][0]
                if text and str(text).strip():
                    lines.append(str(text).strip())
            except Exception:
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


def _clean_stem_line(ln: str) -> str:
    ln = LEADING_QNUM_RE.sub("", ln).strip()
    ln = re.sub(r"\s+", " ", ln).strip()
    return ln


def _clean_choice_text(txt: str) -> str:
    t = (txt or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    # remove stray "(" at end (common OCR artifact)
    t = re.sub(r"\(\s*$", "", t).strip()
    return t


def _opt_num_from_token(tok: str) -> Optional[int]:
    # tok could be "(2)" or "[2]" or "2)"
    digits = re.findall(r"[1-4]", tok)
    if not digits:
        return None
    try:
        return int(digits[0])
    except Exception:
        return None


def _split_multiple_options_in_line(raw: str) -> List[Tuple[int, str]]:
    """
    Handles cases like:
      "1 ... (2) 12"  -> [(1, "..."), (2, "12")]
      "(1) 1 (2) 12"  -> [(1,"1"), (2,"12")]
      "1) 7 2) 9"     -> [(1,"7"), (2,"9")] (rare)
    """
    s = (raw or "").strip()
    if not s:
        return []

    # Find any option markers (including ones in middle)
    matches = list(re.finditer(r"\(\s*[1-4]\s*\)|\[\s*[1-4]\s*\]|\b[1-4]\)", s))
    if not matches:
        return []

    chunks: List[Tuple[int, str]] = []
    for i, m in enumerate(matches):
        tok = m.group(0)
        n = _opt_num_from_token(tok)
        if n is None:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        txt = s[start:end].strip()
        chunks.append((n, txt))

    # Special case: OCR sometimes drops "(" so line begins with "1 ... (2) 12"
    # If the line starts with a bare digit 1-4 AND we also found later markers,
    # treat the first digit as option 1 marker.
    if chunks and re.match(r"^\s*[1-4]\b", s) and not re.match(r"^\s*\(\s*[1-4]\s*\)|^\s*\[\s*[1-4]\s*\]|^\s*[1-4]\)", s):
        first_num = int(re.match(r"^\s*([1-4])\b", s).group(1))
        # text from after that digit up to first matched token
        prefix_end = matches[0].start()
        prefix_txt = s[1:prefix_end].strip()
        chunks = [(first_num, prefix_txt)] + chunks

    return chunks


def parse_question(lines: List[str]) -> Tuple[str, List[str], bool]:
    """
    Returns (stem, choices[4], needs_review)
    """
    stem_parts: List[str] = []
    choices = ["", "", "", ""]
    needs_review = False

    opt_started = False
    last_touched_opt: Optional[int] = None

    for ln in lines:
        raw = (ln or "").strip()
        if not raw:
            continue

        # Multi-option split if present
        multi = _split_multiple_options_in_line(raw)
        if multi:
            opt_started = True
            for opt_num, txt in multi:
                idx = opt_num - 1
                txt = _clean_choice_text(txt)
                if txt:
                    choices[idx] = txt
                else:
                    # leave blank for now; we'll fill later if allowed
                    pass
                last_touched_opt = idx
            continue

        # Single option at start: (1) ..., [1] ..., 1) ...
        m = re.match(r"^\s*[\(\[]?\s*([1-4])\s*[\)\]]\s*(.*)$", raw)
        if m and (raw.strip().startswith("(") or raw.strip().startswith("[") or raw.strip().startswith(("1)", "2)", "3)", "4)"))):
            opt_started = True
            opt_num = int(m.group(1))
            idx = opt_num - 1
            txt = _clean_choice_text(m.group(2) or "")
            if txt:
                choices[idx] = txt
            last_touched_opt = idx
            continue

        if not opt_started:
            cleaned = _clean_stem_line(raw)
            if cleaned:
                stem_parts.append(cleaned)
        else:
            # wrap lines continuing the last option
            if last_touched_opt is None:
                last_touched_opt = 0
            extra = _clean_choice_text(raw)
            if extra:
                if choices[last_touched_opt]:
                    choices[last_touched_opt] = (choices[last_touched_opt] + " " + extra).strip()
                else:
                    choices[last_touched_opt] = extra

    stem = " ".join(stem_parts).strip()
    stem = re.sub(r"\s+", " ", stem).strip()

    if not stem:
        raise ValueError("Could not parse question stem from OCR.")

    # If any choices missing, either fail or mark review
    if any(not c.strip() for c in choices):
        if not ALLOW_INCOMPLETE_CHOICES:
            raise ValueError(f"Could not parse all 4 choices. Got: {choices}")
        needs_review = True
        choices = [c.strip() if c.strip() else MISSING_CHOICE_PLACEHOLDER for c in choices]

    return stem, choices, needs_review


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

    out: dict[str, int] = {}
    for k, v in obj.items():
        try:
            out[str(int(k))] = int(v)
        except Exception:
            continue
    return out


def _target_name_for_qid(qid: int, suffix: str) -> str:
    return f"{RENAME_PREFIX}{qid:0{RENAME_PAD}d}{suffix.lower()}"


def rename_image_file(img_file: Path, qid: int) -> Path:
    target_name = _target_name_for_qid(qid, img_file.suffix)
    target_path = img_file.with_name(target_name)

    if img_file.name == target_name:
        return img_file

    if target_path.exists() and target_path.resolve() != img_file.resolve():
        print(f"[WARN] Rename collision: {img_file.name} -> {target_name} exists. Keeping original.")
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
    existing_by_qid: dict[int, int] = {}
    for i, q in enumerate(bank):
        if isinstance(q, dict) and isinstance(q.get("qid"), int):
            existing_by_qid[q["qid"]] = i

    files = sorted([p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS])

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
            stem, choices, needs_review = parse_question(lines)

            answer_index = -1
            if str(qid) in answers_map:
                v = int(answers_map[str(qid)])
                if 1 <= v <= 4:
                    answer_index = v - 1

            final_img = img_file
            if RENAME_FILES and (not RENAME_ONLY_ON_SUCCESS or True):
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
                "source_image": os.path.relpath(str(final_img), start=str(out_path.parent)),
                "needs_review": bool(needs_review),
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

            flag = " ⚠️" if needs_review else ""
            print(f"[OK] {final_img.name} -> qid={qid}{flag}")

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
