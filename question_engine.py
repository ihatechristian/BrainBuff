# question_engine.py
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Question:
    topic: str
    difficulty: str  # easy|medium|hard (for AI); local can be any string
    question: str
    choices: List[str]  # exactly 4
    answer_index: int  # 0..3
    explanation: str = ""
    image: Optional[str] = None

    # --- NEW: cluster metadata loaded from questions.json ---
    cluster_id: Optional[int] = None
    question_cluster: Optional[str] = None  # human-readable label

    def is_valid(self) -> Tuple[bool, str]:
        if not isinstance(self.question, str) or not self.question.strip():
            return False, "question empty"
        if not isinstance(self.choices, list) or len(self.choices) != 4:
            return False, "choices must be list of exactly 4"
        if any((not isinstance(c, str) or not c.strip()) for c in self.choices):
            return False, "all choices must be non-empty strings"
        if not isinstance(self.answer_index, int) or not (0 <= self.answer_index <= 3):
            return False, "answer_index must be int 0..3"
        if not isinstance(self.topic, str) or not self.topic.strip():
            return False, "topic empty"
        if not isinstance(self.difficulty, str) or not self.difficulty.strip():
            return False, "difficulty empty"
        if self.explanation is None:
            self.explanation = ""
        if not isinstance(self.explanation, str):
            return False, "explanation must be string"

        # image is optional but if provided must be a non-empty string
        if self.image is not None:
            if not isinstance(self.image, str):
                return False, "image must be string or null"
            if not self.image.strip():
                self.image = None

        # cluster fields optional; validate types if provided
        if self.cluster_id is not None and not isinstance(self.cluster_id, int):
            try:
                self.cluster_id = int(self.cluster_id)
            except Exception:
                self.cluster_id = None
        if self.question_cluster is not None and not isinstance(self.question_cluster, str):
            self.question_cluster = str(self.question_cluster)

        return True, "ok"


class QuestionEngine:
    """
    Provides questions from:
      A) local questions.json
      B) optional OpenAI generation with jsonl cache fallback

    ai_mode:
      - "off"   -> local only
      - "cache" -> cached AI only (NO API calls ever)
      - "live"  -> cached AI first, else generate via API and cache (uses tokens)

    cluster_mode (NEW):
      - "off"        -> ignore clusters (random local selection)
      - "adaptive"   -> if last answer was wrong, prefer same-cluster next;
                        if last answer was correct, prefer different-cluster next
    """

    def __init__(
        self,
        local_bank_path: str = "questions_with_clusters.json",
        ai_cache_path: str = "ai_cache.jsonl",
        ai_mode: str = "off",
        ai_model: str = "gpt-4.1-mini",
        cluster_mode: str = "off",  # off | adaptive
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        self.local_bank_path = (
            local_bank_path
            if os.path.isabs(local_bank_path)
            else os.path.join(base_dir, local_bank_path)
        )
        self.ai_cache_path = (
            ai_cache_path
            if os.path.isabs(ai_cache_path)
            else os.path.join(base_dir, ai_cache_path)
        )

        self.ai_mode = (ai_mode or "off").strip().lower()
        self.ai_model = ai_model

        self.cluster_mode = (cluster_mode or "off").strip().lower()
        if self.cluster_mode not in ("off", "adaptive"):
            self.cluster_mode = "off"

        self._local_questions: List[Question] = []
        self._ai_cache: List[Question] = []
        self._ai_cache_index: Dict[str, List[int]] = {}  # key -> indices

        # NEW: local cluster index
        self._cluster_index: Dict[str, List[int]] = {}   # cluster_key -> indices in _local_questions
        self._has_clusters: bool = False

        # NEW: adaptive routing state
        self._last_cluster_key: Optional[str] = None
        self._prefer_same_cluster_next: Optional[bool] = None  # True/False set after answering

        # Debug/info for UI
        self.last_source: str = "local"  # cache|live|local|fallback
        self.last_pick_reason: str = "random"  # random|same_cluster|different_cluster|no_cluster|fallback

        self.load_local_bank()
        self.load_ai_cache()

    # -------------------- Public controls --------------------

    def set_ai_mode(self, mode: str, model: Optional[str] = None):
        mode = (mode or "off").strip().lower()
        if mode not in ("off", "cache", "live"):
            mode = "off"
        self.ai_mode = mode
        if model:
            self.ai_model = model

    def set_cluster_mode(self, mode: str):
        mode = (mode or "off").strip().lower()
        if mode not in ("off", "adaptive"):
            mode = "off"
        self.cluster_mode = mode

    def record_answer(self, question: Question, correct: bool) -> None:
        """
        Call this after a user answers a question so the engine can adapt next selection.
        If correct -> prefer different cluster next.
        If wrong   -> prefer same cluster next.
        """
        ck = self._cluster_key_from_question(question)
        self._last_cluster_key = ck
        self._prefer_same_cluster_next = (not correct)

    # -------------------- Local bank --------------------

    def _resolve_image_path(self, img: Optional[str]) -> Optional[str]:
        if img is None:
            return None
        if not isinstance(img, str):
            img = str(img)
        img = img.strip()
        if not img:
            return None
        if os.path.isabs(img):
            return img
        bank_dir = os.path.dirname(os.path.abspath(self.local_bank_path))
        return os.path.abspath(os.path.join(bank_dir, img))

    def _cluster_key_from_question(self, q: Question) -> Optional[str]:
        """
        Prefer cluster_id if present; else use question_cluster; else None.
        """
        if q.cluster_id is not None:
            return f"id:{int(q.cluster_id)}"
        if q.question_cluster:
            return f"label:{q.question_cluster.strip().lower()}"
        return None

    def _rebuild_cluster_index(self):
        self._cluster_index = {}
        self._has_clusters = False
        for i, q in enumerate(self._local_questions):
            ck = self._cluster_key_from_question(q)
            if ck:
                self._cluster_index.setdefault(ck, []).append(i)
                self._has_clusters = True

    def load_local_bank(self) -> None:
        self._local_questions = []
        if not os.path.exists(self.local_bank_path):
            self._rebuild_cluster_index()
            return

        try:
            with open(self.local_bank_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                self._rebuild_cluster_index()
                return

            for item in data:
                q = self._question_from_dict(item)
                if q:
                    ok, _ = q.is_valid()
                    if ok:
                        self._local_questions.append(q)

        except Exception:
            self._local_questions = []

        self._rebuild_cluster_index()

    def _choose_local_question_adaptive(self) -> Optional[Question]:
        """
        Adaptive rule:
          - If last answer wrong -> same cluster preferred
          - If last answer correct -> different cluster preferred
        Falls back to random if no clusters / no last cluster / not enough variety.
        """
        if not self._local_questions:
            return None

        if self.cluster_mode != "adaptive" or not self._has_clusters:
            self.last_pick_reason = "no_cluster" if not self._has_clusters else "random"
            return random.choice(self._local_questions)

        # No previous cluster info yet => random
        if not self._last_cluster_key or self._prefer_same_cluster_next is None:
            self.last_pick_reason = "random"
            return random.choice(self._local_questions)

        want_same = bool(self._prefer_same_cluster_next)
        last_ck = self._last_cluster_key

        if want_same:
            inds = self._cluster_index.get(last_ck, [])
            if inds:
                self.last_pick_reason = "same_cluster"
                return self._local_questions[random.choice(inds)]
            # If cluster missing, fall back
            self.last_pick_reason = "fallback"
            return random.choice(self._local_questions)

        # want different
        # Choose a different cluster key (if possible)
        keys = list(self._cluster_index.keys())
        if len(keys) <= 1:
            self.last_pick_reason = "fallback"
            return random.choice(self._local_questions)

        other_keys = [k for k in keys if k != last_ck]
        if not other_keys:
            self.last_pick_reason = "fallback"
            return random.choice(self._local_questions)

        pick_ck = random.choice(other_keys)
        inds = self._cluster_index.get(pick_ck, [])
        if inds:
            self.last_pick_reason = "different_cluster"
            return self._local_questions[random.choice(inds)]

        self.last_pick_reason = "fallback"
        return random.choice(self._local_questions)

    def get_local_question(self) -> Optional[Question]:
        return self._choose_local_question_adaptive()

    # -------------------- AI cache --------------------

    def load_ai_cache(self) -> None:
        self._ai_cache = []
        self._ai_cache_index = {}
        if not os.path.exists(self.ai_cache_path):
            return
        try:
            with open(self.ai_cache_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        q = self._question_from_dict(obj)
                        if q:
                            ok, _ = q.is_valid()
                            if ok:
                                idx = len(self._ai_cache)
                                self._ai_cache.append(q)
                                key = self._cache_key(q.topic, q.difficulty)
                                self._ai_cache_index.setdefault(key, []).append(idx)
                    except Exception:
                        continue
        except Exception:
            self._ai_cache = []
            self._ai_cache_index = {}

    def _append_ai_cache(self, q: Question) -> None:
        try:
            with open(self.ai_cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(q.__dict__, ensure_ascii=False) + "\n")
        except Exception:
            pass

        idx = len(self._ai_cache)
        self._ai_cache.append(q)
        key = self._cache_key(q.topic, q.difficulty)
        self._ai_cache_index.setdefault(key, []).append(idx)

    def get_cached_ai_question(self, topic: str, difficulty: str) -> Optional[Question]:
        key = self._cache_key(topic, difficulty)
        indices = self._ai_cache_index.get(key, [])
        if not indices:
            return None
        return self._ai_cache[random.choice(indices)]

    # -------------------- Public API --------------------

    def get_question(self, topic: str, grade_level: str, difficulty: str) -> Question:
        """
        AI selection:
          cache/live -> AI cached/live
          else -> local

        Cluster mode currently applies to LOCAL selection only (safe + predictable).
        (You can extend to AI cache later.)
        """
        mode = (self.ai_mode or "off").strip().lower()

        # 1) AI Cache (NO TOKENS)
        if mode in ("cache", "live"):
            cached = self.get_cached_ai_question(topic, difficulty)
            if cached:
                self.last_source = "cache"
                return cached

        # 2) AI Live (TOKENS) only if allowed
        if mode == "live" and os.getenv("OPENAI_API_KEY"):
            generated = self._generate_ai_question(topic, grade_level, difficulty)
            if generated:
                self._append_ai_cache(generated)
                self.last_source = "live"
                return generated

        # 3) Local (cluster-aware if enabled)
        local = self.get_local_question()
        if local:
            self.last_source = "local"
            return local

        # 4) Built-in fallback
        self.last_source = "fallback"
        return Question(
            topic="General",
            difficulty="easy",
            question="Which number is the largest?",
            choices=["2", "9", "5", "1"],
            answer_index=1,
            explanation="9 is the largest among the options.",
            image=None,
            cluster_id=None,
            question_cluster=None,
        )

    # -------------------- OpenAI (live mode only) --------------------

    def _generate_ai_question(self, topic: str, grade_level: str, difficulty: str) -> Optional[Question]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        try:
            import requests
        except Exception:
            return None

        system = (
            "You are a question generator. Return STRICT JSON ONLY. "
            "No markdown. No commentary. No extra keys. "
            "Ensure there are exactly 4 choices. answer_index must be 0-3 and match the correct choice. "
            "Explanation must be 1-2 short sentences. "
            "If an image is required, set image to a string file path; otherwise set image to null."
        )

        user = {
            "topic": topic,
            "grade_level": grade_level,
            "difficulty": difficulty,
            "required_schema": {
                "topic": "string",
                "difficulty": "easy|medium|hard",
                "question": "string",
                "choices": ["A", "B", "C", "D"],
                "answer_index": "0-3",
                "explanation": "string",
                "image": "string|null",
            },
        }

        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.ai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 220,
                },
                timeout=10,
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            if "choices" not in data or not data["choices"]:
                return None

            text = data["choices"][0]["message"]["content"].strip()
            obj = json.loads(text)

            q = self._question_from_dict(obj)
            if not q:
                return None

            if len(q.choices) != 4:
                return None
            if not (0 <= q.answer_index <= 3):
                return None
            if q.difficulty not in ["easy", "medium", "hard"]:
                q.difficulty = difficulty if difficulty in ["easy", "medium", "hard"] else "easy"
            if len((q.explanation or "").split()) > 35:
                q.explanation = " ".join((q.explanation or "").split()[:35])

            ok, _ = q.is_valid()
            return q if ok else None
        except Exception:
            return None

    # -------------------- Helpers --------------------

    def _question_from_dict(self, item: Dict[str, Any]) -> Optional[Question]:
        if not isinstance(item, dict):
            return None
        try:
            choices = item.get("choices", [])
            if not isinstance(choices, list):
                choices = []

            img = self._resolve_image_path(item.get("image", None))

            # cluster fields (optional)
            cid = item.get("cluster_id", None)
            if cid is not None:
                try:
                    cid = int(cid)
                except Exception:
                    cid = None

            clabel = item.get("question_cluster", None)
            if clabel is not None:
                clabel = str(clabel).strip() or None

            return Question(
                topic=str(item.get("topic", "")).strip(),
                difficulty=str(item.get("difficulty", "")).strip(),
                question=str(item.get("question", "")).strip(),
                choices=list(choices),
                answer_index=int(item.get("answer_index", -1)),
                explanation=str(item.get("explanation", "") or "").strip(),
                image=img,
                cluster_id=cid,
                question_cluster=clabel,
            )
        except Exception:
            return None

    def _cache_key(self, topic: str, difficulty: str) -> str:
        return f"{(topic or '').strip().lower()}::{(difficulty or '').strip().lower()}"
