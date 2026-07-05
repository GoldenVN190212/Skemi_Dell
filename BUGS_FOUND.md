# Bugs found out of scope (Skemi `/goal` 2026-05-27)

These came up during verification but are outside the 15-test scope. Recorded here so they don't get forgotten; not fixed.

## 1. uiautomation SendKeys character repetition

**Where:** `phantom_core.py:ai_type_text` via `uiautomation`.

**Symptom:** Typing `"Hello from Skemi Phantom AI agent - this is Jarvis mode working live!"` produced `"Hello kkkkkkkemi mmmmm aaaagent ssssss ddddde iiiing !!!!!"` in Notepad. 70 chars at Col 71 confirms text entry happened, but per-char SendKeys repeats letters.

**Likely cause:** SendKeys hold-time + multi-byte / IME interference.

**Suggested fix:** Switch to `control.GetValuePattern().SetValue(text)` for edit controls (atomic write, bypasses keyboard layer entirely). Fall back to SendKeys only if no ValuePattern available.

## 2. Notepad UWP launch race window

**Where:** `phantom_core.py:open_app_on_desktop` for Win11 Notepad.

**Symptom:** Notepad sometimes opens but `_find_windows_by_pid` misses the new window within the 10 s deadline because the UWP packaging adds ~4–8 s before the first top-level window appears.

**Workaround:** Deadline already extended to 10 s. For consistently slow systems, increase to 15 s or poll by class name `Notepad` plus PID hierarchy (UWP wrappers spawn the actual notepad as a child PID).

## 3. qwen2.5:3b brackets/placeholders on hi & it

**Where:** Server-side translate batch using `qwen2.5:3b` for Hindi and Italian.

**Symptom:** Translations occasionally return `[BRACKETED_OUTPUT]` or `[PLACEHOLDER_LIKE]` instead of the actual translation for these languages.

**Workaround:** `_normalize_ui_translation_text` strips bracket wrappers when shaped like `["text"]`. Quality could still be better — a larger model (qwen2.5:7b/14b) or the user's `gemini-3-flash:cloud` (once auth is configured) handles these cleanly.

## 4. Ollama Cloud auth missing in sandbox

**Where:** Translation pipeline preference chain.

**Symptom:** `gemini-3-flash-preview:cloud`, `minimax-m2:cloud`, `devstral-2:123b-cloud` all returned `unauthorized` in this verification sandbox. Fallback chain steps through to `qwen2.5:3b` which works locally.

**Action needed on user side:** Configure Ollama Cloud auth (likely an API token via `ollama auth login` or `OLLAMA_CLOUD_TOKEN` env var). Once configured, the cloud model will be picked first per `/goal` and translation quality will jump.

## 5. ES module browser cache during debugging

**Where:** Preview server browser session, ES modules.

**Symptom:** After editing `LanguageManager.js`, the in-tab module remained cached even with URL `?v=timestamp`. Hard reload (`location.replace`) or preview restart required.

**Action needed:** None for normal users (cold loads). Only affects iterative debugging in same tab.
