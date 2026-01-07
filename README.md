# BrainBuff
# BrainBuff (MVP)

BrainBuff is a **non-intrusive educational overlay** for **any PC game** that runs in **Windowed** or **Borderless Windowed** mode.

## What it does
- Monitors **global keyboard + mouse activity** (game-agnostic) using `pynput`
- If the player is in a **low-activity** moment (e.g., waiting, calm segment), it shows a small overlay question
- The overlay:
  - is a **separate window** (no injection, no hooking, no memory reads)
  - is **transparent & borderless**
  - stays **always-on-top**
  - **does not steal focus** (answers via global hotkeys)

> Note: Some games/GPU configurations may block overlays in **Exclusive Fullscreen**. Use **Borderless Windowed** for best results.

---

## Controls (Global Hotkeys)
- `1` `2` `3` `4` : answer choices
- `Esc` : hide overlay
- `F9` : snooze for 10 minutes (configurable)

---

## How it decides when to show
- Tracks input events in the last `activity_window_sec` seconds (default 8s)
- **LOW ACTIVITY** if count <= `low_activity_threshold`
- **Cooldown** prevents frequent popups
- If activity spikes (combat), overlay hides immediately (`high_activity_spike_threshold`)
- Limits popups to `max_popups_per_hour`

All settings are in `settings.json`.

---

## Questions
### Offline (Local Bank)
- Reads from `questions.json`:
  - `question`, `choices[4]`, `answer_index`, `explanation`, `topic`, `difficulty`

### Online (Optional AI)
- If `ai_questions_enabled=true` AND `OPENAI_API_KEY` is set:
  - Generates questions with OpenAI and requires STRICT JSON
  - Caches generated questions to `ai_cache.jsonl` to reduce calls
- Falls back to local bank if:
  - no key
  - request fails / rate limit
  - offline

---

## Setup (VS Code / Windows)

### 1) Create venv
```bash
cd brainbuff
python -m venv .venv
.venv\Scripts\activate
