from __future__ import annotations
from pathlib import Path

# Project root = folder containing these files
PROJECT_ROOT = Path(__file__).resolve().parent

SETTINGS_PATH = PROJECT_ROOT / "settings.json"
QUESTIONS_PATH = PROJECT_ROOT / "questions.json"
CROPPED_DIR = PROJECT_ROOT / "cropped_questions"
IMAGES_DIR = PROJECT_ROOT / "images"

GAME_MAIN = PROJECT_ROOT / "demo_game" / "main.py"
OVERLAY_MAIN = PROJECT_ROOT / "overlay_trigger.py"
ANSWERS_MAP_PATH = PROJECT_ROOT / "answers_map.json"
