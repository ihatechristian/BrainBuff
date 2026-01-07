import json
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

import requests


@dataclass
class Question:
    topic: str
    difficulty: str  # easy|medium|hard (for AI); local can be any string
    question: str
    choices: List[str]  # exactly 4
    answer_index: int  # 0..3
    explanation: str = ""

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
        return True, "ok"


class QuestionEngine:
    """
    Provides questions from:
      A) local questions.json
      B) optional OpenAI generation (STRICT JSON) with jsonl cache fallback
    """

    def __init__(
        self,
        local_bank_path: str = "questions.json",
        ai_cache_path: str = "ai_cache.jsonl",
        ai_enabled: bool = False,
        ai_model: str = "gpt-4.1-mini",
    ):
        self.local_bank_path = local_bank_path
        self.ai_cache_path = ai_cache_path
        self.ai_enabled = ai_enabled
        self.ai_model = ai_model

        self._local_questions: List[Question] = []
        self._ai_cache: List[Question] = []
        self._ai_cache_index: Dict[str, List[int]] = {}  # key -> indices

        self.load_local_bank()
        self.load_ai_cache()

    def set_ai(self, enabled: bool, model: str):
        self.ai_enabled = enabled
        self.ai_model = model

    # ---------- Local bank ----------
    def load_local_bank(self) -> None:
        self._local_questions = []
        if not os.path.exists(self.local_bank_path):
            return
        try:
            with open(self.local_bank_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            for item in data:
                q = self._question_from_dict(item)
                if q:
                    ok, _ = q.is_valid()
                    if ok:
                        self._local_questions.append(q)
        except Exception:
            # Keep running even if file is malformed
            self._local_questions = []

    def get_local_question(self) -> Optional[Question]:
        if not self._local_questions:
            return None
        return random.choice(self._local_questions)

    # ---------- AI cache ----------
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

    # ---------- Public API ----------
    def get_question(
        self,
        topic: str,
        grade_level: str,
        difficulty: str,
    ) -> Question:
        """
        Priority:
          1) If AI enabled and key exists:
              - Use cached AI question if available
              - Otherwise generate via OpenAI and cache it
          2) Fallback to local bank
          3) Last resort: a built-in safe question
        """
        if self.ai_enabled and os.getenv("OPENAI_API_KEY"):
            cached = self.get_cached_ai_question(topic, difficulty)
            if cached:
                return cached

            generated = self._generate_ai_question(topic, grade_level, difficulty)
            if generated:
                self._append_ai_cache(generated)
                return generated

        local = self.get_local_question()
        if local:
            return local

        return Question(
            topic="General",
            difficulty="easy",
            question="Which number is the largest?",
            choices=["2", "9", "5", "1"],
            answer_index=1,
            explanation="9 is the largest among the options.",
        )

    # ---------- OpenAI ----------
    def _generate_ai_question(self, topic: str, grade_level: str, difficulty: str) -> Optional[Question]:
        """
        Uses OpenAI Responses API via requests.
        Returns STRICT JSON (no markdown). Validates schema + guardrails.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        # Strong instruction: JSON only, exact schema, 4 choices.
        system = (
            "You are a question generator. Return STRICT JSON ONLY. "
            "No markdown. No commentary. No extra keys. "
            "Ensure there are exactly 4 choices. answer_index must be 0-3 and match the correct choice. "
            "Explanation must be 1-2 short sentences."
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
                "explanation": "string"
            }
        }

        try:
            # Chat Completions API
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
            
            # Extract content from chat completion
            if "choices" in data and len(data["choices"]) > 0:
                text = data["choices"][0]["message"]["content"].strip()
            else:
                return None

            # Must be JSON only:
            obj = json.loads(text)

            q = self._question_from_dict(obj)
            if not q:
                return None

            # Guardrails:
            if len(q.choices) != 4:
                return None
            if not (0 <= q.answer_index <= 3):
                return None
            if q.difficulty not in ["easy", "medium", "hard"]:
                # normalize if model slightly deviates
                q.difficulty = difficulty if difficulty in ["easy", "medium", "hard"] else "easy"
            if len((q.explanation or "").split()) > 35:
                # Keep it short
                q.explanation = " ".join((q.explanation or "").split()[:35])

            ok, _ = q.is_valid()
            return q if ok else None

        except Exception:
            return None

    def _extract_text_from_responses(self, data: Dict[str, Any]) -> str:
        """
        Handles common Responses API shapes.
        """
        # Preferred: output_text
        if isinstance(data, dict) and isinstance(data.get("output_text"), str):
            return data["output_text"].strip()

        # Fallback: parse output array
        out = data.get("output")
        if isinstance(out, list):
            chunks = []
            for item in out:
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                            chunks.append(c["text"])
                        elif c.get("type") == "text" and isinstance(c.get("text"), str):
                            chunks.append(c["text"])
            joined = "".join(chunks).strip()
            return joined

        return ""

    # ---------- Helpers ----------
    def _question_from_dict(self, item: Dict[str, Any]) -> Optional[Question]:
        if not isinstance(item, dict):
            return None
        try:
            return Question(
                topic=str(item.get("topic", "")).strip(),
                difficulty=str(item.get("difficulty", "")).strip(),
                question=str(item.get("question", "")).strip(),
                choices=list(item.get("choices", [])),
                answer_index=int(item.get("answer_index", -1)),
                explanation=str(item.get("explanation", "") or "").strip(),
            )
        except Exception:
            return None

    def _cache_key(self, topic: str, difficulty: str) -> str:
        return f"{(topic or '').strip().lower()}::{(difficulty or '').strip().lower()}"
