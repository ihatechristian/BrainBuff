# ingest_question_folder_gui_free.py
# ---------------------------------
# Ingest a folder of question images -> questions.json
# ✅ Preserves blanks like "____" by:
#   1) Keeping OCR underscore tokens (many OCRs drop them, but if present we keep)
#   2) Detecting drawn underline blanks in the image (OpenCV) and inserting "_____"
#      into the closest OCR text line at the correct x-position.
#
# Requirements: paddleocr, paddlepaddle, opencv-python
#
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Optional, List, Tuple, Dict

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

# --- Blank (underline) detection tuning ---
# If your blanks are NOT detected, lower WIDTH_RATIO and ASPECT slightly.
# If too many false positives, raise them.
MIN_UNDERLINE_WIDTH_RATIO = 0.05       # underline must be >= 5% of image width
MIN_UNDERLINE_WIDTH_PX = 25            # also must be at least this many pixels
MIN_UNDERLINE_ASPECT = 3.0             # width/height (thin horizontal)
MAX_UNDERLINE_HEIGHT_PX = 18           # ignore thick rectangles
MAX_GAP_TO_MERGE_PX = 40               # merge broken underline segments if gap <= this
MAX_Y_DIFF_TO_MERGE_PX = 10            # merge segments if vertical centers close
BLANK_TOKEN = "_____"                  # what to insert into question text
# =========================

# ✅ FIX: also removes "10 " (no dot), "10-" etc.
LEADING_QNUM_RE = re.compile(r"^\s*(?:Q\s*)?\d{1,4}\s*(?:[.)\-:]|\s+)\s*")

FILENAME_QID_RE = re.compile(r"(?:^|[^0-9])(?:Q)?(\d{1,6})(?:[^0-9]|$)", re.IGNORECASE)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Detect option markers in text lines
OPT_LINE_RE = re.compile(r"^\s*[\(\[]?\s*([1-4])\s*[\)\]]\s*(.*)$")

# Global OCR instance
_OCR = None


class _NullWriter:
    def write(self, *_args, **_kwargs): ...
    def flush(self): ...


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


def qid_from_filename(stem: str) -> Optional[int]:
    m = FILENAME_QID_RE.search(stem)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


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


# -------------------------
# Underline (blank) detection
# -------------------------
def detect_underlines(img_bgr) -> List[Tuple[int, int, int]]:
    import cv2

    h, w = img_bgr.shape[:2]
    min_w = max(MIN_UNDERLINE_WIDTH_PX, int(w * float(MIN_UNDERLINE_WIDTH_RATIO)))

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    thr = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        35, 12
    )

    thr = cv2.medianBlur(thr, 3)

    kernel_w = max(20, int(w * 0.06))
    horiz = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
    lines = cv2.morphologyEx(thr, cv2.MORPH_OPEN, horiz, iterations=1)

    lines = cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)), iterations=1)

    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: List[Tuple[int, int, int, int]] = []
    for c in contours:
        x, y, ww, hh = cv2.boundingRect(c)
        if ww < min_w:
            continue
        if hh > MAX_UNDERLINE_HEIGHT_PX:
            continue
        aspect = ww / max(1, hh)
        if aspect < MIN_UNDERLINE_ASPECT:
            continue
        candidates.append((x, y, ww, hh))

    candidates.sort(key=lambda t: (t[1] + t[3] // 2, t[0]))
    merged: List[Tuple[int, int, int, int]] = []

    for x, y, ww, hh in candidates:
        yc = y + hh // 2
        if not merged:
            merged.append((x, y, ww, hh))
            continue

        mx, my, mww, mhh = merged[-1]
        myc = my + mhh // 2
        gap = x - (mx + mww)

        if abs(yc - myc) <= MAX_Y_DIFF_TO_MERGE_PX and gap <= MAX_GAP_TO_MERGE_PX:
            nx = mx
            ny = min(my, y)
            nx2 = max(mx + mww, x + ww)
            ny2 = max(my + mhh, y + hh)
            merged[-1] = (nx, ny, nx2 - nx, ny2 - ny)
        else:
            merged.append((x, y, ww, hh))

    out: List[Tuple[int, int, int]] = []
    for x, y, ww, hh in merged:
        out.append((x, x + ww, y + hh // 2))
    return out


def ocr_tokens_with_boxes(img_path: str) -> Tuple[List[Tuple[str, float, float, float, float]], Tuple[int, int]]:
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

    h, w = img.shape[:2]

    try:
        result = _OCR.ocr(img)
    except Exception:
        result = _OCR.ocr(img_path)

    tokens: List[Tuple[str, float, float, float, float]] = []
    if result and isinstance(result, list):
        blocks = result[0] if (len(result) == 1 and isinstance(result[0], list)) else result
        for block in blocks:
            try:
                box = block[0]
                text = str(block[1][0])
                if not text:
                    continue
                text = text.strip()
                if not text:
                    continue

                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                x1, x2 = float(min(xs)), float(max(xs))
                y1, y2 = float(min(ys)), float(max(ys))
                tokens.append((text, x1, x2, y1, y2))
            except Exception:
                continue

    return tokens, (w, h)


def rebuild_lines_and_insert_blanks(img_path: str) -> List[str]:
    import cv2

    tokens, (w, h) = ocr_tokens_with_boxes(img_path)
    img = cv2.imread(img_path)

    underlines = detect_underlines(img) if img is not None else []

    if not tokens:
        return [BLANK_TOKEN] if underlines else []

    line_tol = max(10, int(h * 0.018))

    lines: List[Dict[str, object]] = []
    for text, x1, x2, y1, y2 in sorted(tokens, key=lambda t: ((t[3] + t[4]) / 2, t[1])):
        yc = (y1 + y2) / 2.0
        xc = (x1 + x2) / 2.0

        placed = False
        for L in lines:
            if abs(yc - float(L["yc"])) <= line_tol:
                L["yc"] = (float(L["yc"]) * 0.85) + (yc * 0.15)
                cast = L["tokens"]  # type: ignore
                cast.append((text, xc, x1, x2))  # type: ignore
                placed = True
                break

        if not placed:
            lines.append({"yc": yc, "tokens": [(text, xc, x1, x2)]})

    for L in lines:
        L["tokens"] = sorted(L["tokens"], key=lambda t: t[1])  # type: ignore

    for x1, x2, yc in underlines:
        best_i = None
        best_d = 1e18
        for i, L in enumerate(lines):
            d = abs(yc - float(L["yc"]))
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            continue

        L = lines[best_i]
        toks = list(L["tokens"])  # type: ignore

        joined = " ".join([t[0] for t in toks])
        if "__" in joined:
            continue

        blank_xc = (x1 + x2) / 2.0

        ins = 0
        while ins < len(toks) and toks[ins][1] < blank_xc:
            ins += 1

        if ins > 0 and toks[ins - 1][0] == BLANK_TOKEN:
            continue
        if ins < len(toks) and toks[ins][0] == BLANK_TOKEN:
            continue

        toks.insert(ins, (BLANK_TOKEN, blank_xc, float(x1), float(x2)))
        L["tokens"] = toks  # type: ignore

    out_lines: List[str] = []
    for L in sorted(lines, key=lambda d: float(d["yc"])):  # type: ignore
        toks = L["tokens"]  # type: ignore
        parts = []
        for t in toks:
            s = t[0]
            if re.search(r"_{2,}", s):
                s = BLANK_TOKEN
            parts.append(s)
        line = " ".join(parts).strip()
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out_lines.append(line)

    return out_lines


def _clean_stem_line(ln: str) -> str:
    ln = LEADING_QNUM_RE.sub("", ln).strip()
    ln = re.sub(r"\s+", " ", ln).strip()
    return ln


def _clean_choice_text(txt: str) -> str:
    t = (txt or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\(\s*$", "", t).strip()
    return t


def parse_question(lines: List[str]) -> Tuple[str, List[str], bool]:
    stem_parts: List[str] = []
    choices = ["", "", "", ""]
    needs_review = False

    opt_started = False
    last_opt: Optional[int] = None

    for ln in lines:
        raw = (ln or "").strip()
        if not raw:
            continue

        m = OPT_LINE_RE.match(raw)
        if m:
            opt_num = int(m.group(1))
            idx = opt_num - 1
            txt = _clean_choice_text(m.group(2) or "")
            choices[idx] = txt
            opt_started = True
            last_opt = idx
            continue

        if not opt_started:
            cleaned = _clean_stem_line(raw)
            if cleaned:
                stem_parts.append(cleaned)
        else:
            if last_opt is None:
                last_opt = 0
            extra = _clean_choice_text(raw)
            if extra:
                if choices[last_opt]:
                    choices[last_opt] = (choices[last_opt] + " " + extra).strip()
                else:
                    choices[last_opt] = extra

    stem = " ".join(stem_parts).strip()
    stem = re.sub(r"\s+", " ", stem).strip()

    if not stem:
        raise ValueError("Could not parse question stem from OCR.")

    stem = stem.replace(" _ ", f" {BLANK_TOKEN} ")
    stem = re.sub(r"\s+", " ", stem).strip()

    if any(not c.strip() for c in choices):
        if not ALLOW_INCOMPLETE_CHOICES:
            raise ValueError(f"Could not parse all 4 choices. Got: {choices}")
        needs_review = True
        choices = [c.strip() if c.strip() else MISSING_CHOICE_PLACEHOLDER for c in choices]

    return stem, choices, needs_review


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

            lines = rebuild_lines_and_insert_blanks(str(img_file))
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
            if BLANK_TOKEN in stem:
                print("     stem:", stem)

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
