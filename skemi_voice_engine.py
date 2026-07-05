import os
import re
import json
import time
import queue
import logging
import asyncio
import tempfile
import threading
import hashlib
import shutil
import unicodedata
import numpy as np
import httpx
# Use mirror for faster downloads in Vietnam
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from faster_whisper import WhisperModel
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from pathlib import Path
from typing import Callable, Optional

# Async TTS support
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

# Constants
VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-vn-0.4.zip"
MODEL_DIR = Path("data/vosk-model-vn")
WAKE_WORDS = ["skemi", "skemi oi", "skemi ơi", "skema", "skemma", "ê skemi", "này skemi", "này skemi ơi"]
ENERGY_THRESHOLD = 0.35
WAKE_WORDS.extend(["e skemi", "nay skemi", "ơi skemi", "này skemi", "skemi ơi", "skemi oi", "alo", "alo alo"])
SPEECH_RMS_THRESHOLD = 0.018
COMMAND_SILENCE_SECONDS = 1.5
COMMAND_MAX_SECONDS = 15.0
HALLUCINATIONS = [
    "ghiền mì gõ", "subscribe", "đăng ký kênh", "cảm ơn các bạn", 
    "theo dõi", "video hấp dẫn", "tạm biệt lắm", "hãy subscribe",
    "la la school", "phim hay", "tập tiếp theo", "mình xin chào",
    "chào mừng các bạn", "kênh của mình", "like và share",
    "mặc yếu tật", "dễ chói", "hai cố", "hai, cố", "thank you", "watching"
]
WAKE_WORDS = ["skemi", "skemi ơi", "alo", "alo skemi", "chào skemi", "hey skemi"]

# Global instance for singleton access
_voice_engine_instance = None

def get_voice_engine():
    global _voice_engine_instance
    return _voice_engine_instance

try:
    import vosk
    import sounddevice as sd
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

class SkemiVoiceEngine:
    def __init__(self, model_path: str = str(MODEL_DIR)):
        global _voice_engine_instance
        _voice_engine_instance = self
        self.model_path = Path(model_path)
        self.logger = logging.getLogger("SkemiVoice")
        self.logger.setLevel(logging.INFO)
        self._stop_event = asyncio.Event()
        self._audio_queue = queue.Queue()
        self.is_listening = False
        
        # Default to a fast local model on 4GB VRAM; medium remains opt-in.
        self.model_size = os.getenv("SKEMI_WHISPER_MODEL", "medium").strip() or "medium"
        self.whisper = None

        # Audio state
        self.last_audio_heartbeat = time.time()
        self.event_callback = None
        self.command_callback = None
        
        self.tts_voice = "vi-VN-NamMinhNeural"
        self.pygame_initialized = False
        self.is_speaking = False
        self._tts_lock = threading.Lock()
        
        # TTS Cache
        self.cache_dir = Path("data/tts_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize pyttsx3 for offline fallback
        self.offline_engine = None
        if HAS_PYTTSX3:
            try:
                self.offline_engine = pyttsx3.init()
                # Try to find a Vietnamese voice
                voices = self.offline_engine.getProperty('voices')
                for voice in voices:
                    if "vietnam" in voice.name.lower() or "vi-vn" in voice.id.lower():
                        self.offline_engine.setProperty('voice', voice.id)
                        break
                self.offline_engine.setProperty('rate', 160) # Slightly slower for clarity
            except Exception as e:
                self.logger.warning(f"Failed to init pyttsx3: {e}")

        # TTS Queue and Worker
        self._tts_queue = queue.Queue(maxsize=10)
        threading.Thread(target=self._speak_worker_loop, daemon=True).start()

        # Initialize pygame for audio
        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(1.0)
            self.pygame_initialized = True
        except:
            pass
            
            
    def _play_beep(self):
        """Beep disabled by user request."""
        pass

    def _init_whisper(self):
        if self.whisper is not None:
            return True
        try:
            self.logger.info(f"Loading Whisper model ({self.model_size}) on GPU (Storage: Drive D)...")
            download_dir = "d:/Skemi (1)/models/whisper"
            os.makedirs(download_dir, exist_ok=True)
            
            self.whisper = WhisperModel(
                self.model_size, 
                device="cuda", 
                compute_type="float16",
                download_root=download_dir
            )
            self.logger.info(f"Whisper model LOADED on GPU (CUDA). Running at maximum power.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to load on GPU, falling back to CPU: {e}")
            try:
                self.whisper = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                self.logger.info("Whisper model loaded on CPU as fallback.")
                return True
            except Exception as e2:
                self.logger.error(f"Total Whisper failure: {e2}")
                return False

    def _audio_callback(self, indata, frames, time, status):
        if status:
            self.logger.warning(f"Audio status: {status}")
        self._audio_queue.put(bytes(indata))

    def start(self, callback: Callable[[str], None], event_callback: Optional[Callable[[str, dict], None]] = None):
        """Start listening for wake word in a background thread."""
        self.command_callback = callback
        self.event_callback = event_callback
        self.is_listening = True
        
        thread = threading.Thread(target=lambda: asyncio.run(self._run_loop()), daemon=True)
        thread.start()
        
        # Test disabled per user request
        # self._play_beep()
        self.loop = asyncio.get_event_loop()
        return True

    def _emit_status(self, phase: str, **payload):
        payload.setdefault("phase", phase)
        payload.setdefault("listening", bool(self.is_listening))
        try:
            if self.event_callback:
                self.event_callback(phase, payload)
        except Exception:
            pass

    def _normalize_text(self, text: str) -> str:
        """Basic normalization for matching (lowercase, strip, loose accents)."""
        res = str(text or "").lower().strip()
        return res

    def _speech_intent_key(self, text: str) -> str:
        """Normalize speech for intent routing, not for display."""
        raw = str(text or "").lower()
        raw = "".join(
            ch for ch in unicodedata.normalize("NFKD", raw)
            if not unicodedata.combining(ch)
        )
        raw = raw.replace("đ", "d")
        raw = re.sub(r"[^a-z0-9]+", " ", raw)
        return re.sub(r"\s+", " ", raw).strip()

    def _is_greeting_only(self, text: str) -> bool:
        """Return True for wake/greeting noise that should not become a computer task."""
        key = self._speech_intent_key(text)
        if not key:
            return True
        greeting_words = {
            "alo", "skemi", "hi", "hey", "hello", "chao", "oi", "nay",
            "e", "uh", "um", "a", "da", "troi", "vai", "ok", "okay",
        }
        parts = key.split()
        if parts and all(part in greeting_words for part in parts):
            return True
        return key in {
            "alo alo",
            "skemi oi",
            "oi skemi",
            "chao skemi",
            "hey skemi",
            "troi oi",
            "oi troi",
        }

    def _clean_transcript(self, text: str) -> str:
        source = str(text or "").strip()
        cleaned = re.sub(r"\s+", " ", source)
        for wake in sorted(WAKE_WORDS, key=len, reverse=True):
            cleaned = re.sub(rf"^\s*{re.escape(wake)}\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(ơi|oi|này|nay|ê|e)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def _extract_wake_remainder(self, text: str) -> str:
        source = re.sub(r"\s+", " ", str(text or "")).strip()
        lower = source.lower()
        best_pos = -1
        best_wake = ""
        for wake in sorted(WAKE_WORDS, key=len, reverse=True):
            pos = lower.find(wake.lower())
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos
                best_wake = wake
        if best_pos < 0:
            return ""
        return self._clean_transcript(source[best_pos + len(best_wake):])

    def stop(self):
        self._stop_event.set()
        self.is_listening = False

    async def _run_loop(self, samplerate=16000):
        if not self._init_whisper():
            return

        import sounddevice as sd
        
        # Select working input device
        try:
            input_device_index = sd.default.device[0]
            devices = sd.query_devices()
            input_indices = [i for i, d in enumerate(devices) if d['max_input_channels'] > 0]
            
            self.logger.info(f"[VOICE] Starting signal check on input devices: {input_indices}")
            
            def check_signal(idx):
                try:
                    q = queue.Queue()
                    def cb(data, frames, time, status): q.put(np.linalg.norm(data))
                    with sd.InputStream(device=idx, channels=1, callback=cb, samplerate=16000):
                        time.sleep(0.3)
                        levels = []
                        while not q.empty(): levels.append(q.get())
                        return np.mean(levels) if levels else 0
                except Exception: return 0

            sig = check_signal(input_device_index)
            if sig < 0.02: 
                self.logger.warning(f"[VOICE] Default device seems dead. Scanning alternatives...")
                best_sig = sig
                best_idx = input_device_index
                for idx in input_indices:
                    if idx == input_device_index: continue
                    other_sig = check_signal(idx)
                    if other_sig > best_sig and other_sig > 0.1:
                        best_sig = other_sig
                        best_idx = idx
                
                if best_idx != input_device_index:
                    self.logger.info(f"[VOICE] Switching to device {best_idx} ({devices[best_idx]['name']})")
                    input_device_index = best_idx
                    sd.default.device = (best_idx, sd.default.device[1])
            else:
                self.logger.info(f"[VOICE] Keeping default device {input_device_index} (signal {sig:.4f} is sufficient)")
        except Exception as e:
            self.logger.warning(f"[VOICE] Device auto-select error: {e}")

        self.last_audio_heartbeat = time.time()
        
        audio_buffer = []
        in_command_mode = False
        command_start_time = 0
        last_speech_at = time.time()

        try:
            with sd.RawInputStream(samplerate=samplerate, blocksize=8000, dtype='int16',
                                   channels=1, callback=self._audio_callback,
                                   device=sd.default.device[0]):
                self.logger.info("Skemi Voice Engine (Whisper) active. Listening...")
                pass # Removed noisy print per user request
                
                while not self._stop_event.is_set():
                    try:
                        raw_data = self._audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    
                    # Convert to float32 for Whisper/Energy
                    # Increase gain to 2.0 for high sensitivity
                    audio_array = (np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0) * 2.0
                    rms = np.sqrt(np.mean(np.square(audio_array)))
                    now = time.time()

                    # Heartbeat
                    if now - self.last_audio_heartbeat > 5.0:
                        self.last_audio_heartbeat = now

                    # Voice Activity Detection (Simple)
                    if self.is_speaking:
                        audio_buffer = [] # Clear buffer while speaking
                        continue

                    if rms > SPEECH_RMS_THRESHOLD:
                        if not audio_buffer:
                            self._emit_status("hearing", transcript="")
                        last_speech_at = now
                        audio_buffer.append(audio_array)
                    elif len(audio_buffer) > 0:
                        audio_buffer.append(audio_array) # Append some silence
                        
                        # Process buffer if silence > 0.6s (Live mode) or buffer too long
                        if now - last_speech_at > 0.6 or len(audio_buffer) > 20:
                            full_audio = np.concatenate(audio_buffer)
                            audio_buffer = []
                            self._emit_status("transcribing", transcript="")
                            
                            segments, _ = self.whisper.transcribe(
                                full_audio, 
                                language="vi", 
                                beam_size=1,
                                temperature=0,
                                initial_prompt="Alo."
                            )
                            text = " ".join([s.text for s in segments]).strip()
                            
                            # Filter hallucinations and very short junk
                            if text:
                                lower_text = text.lower().strip(".,!? ")
                                intent_key = self._speech_intent_key(text)
                                # Skip common short junk words or hallucinations regardless of length
                                if intent_key in {"ay", "nao", "a", "lao", "ui", "nay", "la"}:
                                    self.logger.info(f"Skipping junk word: {text}")
                                    text = ""
                                elif any(self._speech_intent_key(h) in intent_key for h in HALLUCINATIONS):
                                    self.logger.debug(f"Filtered Whisper hallucination: {text}")
                                    text = ""
                                elif len(text) < 2:
                                    text = ""
                                
                                if text:
                                    self._emit_status("final", transcript=text)
                                    # SHOW IN TERMINAL CLEARLY
                                    print(f"\n[BẠN]: {text}")
                                    
                                    if self._is_greeting_only(text):
                                        self.logger.info(f"Voice greeting/noise ignored: {text}")
                                        self._emit_status("listening", transcript="")
                                        continue

                                    if self.command_callback:
                                        # Acknowledge with TTS before executing
                                        self.logger.info(f"Command: {text}")
                                        self._emit_status("processing", transcript=text)
                                        self.speak("Đã nhận. Đang xử lý...")
                                        self._emit_status("dispatching", transcript=text)
                                        if asyncio.iscoroutinefunction(self.command_callback):
                                            asyncio.run_coroutine_threadsafe(self.command_callback(text), self.loop)
                                        else:
                                            self.command_callback(text)
                                if not self.command_callback:
                                    self._emit_status("listening", transcript="")
                    
                    # Reset command mode if timeout
                    if in_command_mode and now - command_start_time > 15.0:
                        self.logger.info("Command mode timeout.")
                        self._emit_status("timeout", transcript="")
                        in_command_mode = False

        except Exception as e:
            self.logger.error(f"Voice loop error: {e}")
        finally:
            self.is_listening = False

    def _trigger_command_mode(self):
        """Trigger visual feedback for command mode."""
        self._emit_status("listening", transcript="")
        # Silent trigger
        pass

    def speak(self, text: str):
        if not text: return
        
        # Master Translation Filter: Force all status messages to Vietnamese
        text_map = {
            "Stopping the current task": "Đang dừng tác vụ hiện tại...",
            "Could not launch the requested": "Không tìm thấy ứng dụng yêu cầu.",
            "Task completed": "Đã hoàn thành nhiệm vụ.",
            "Starting": "Bắt đầu xử lý.",
            "I'm thinking": "Tôi đang suy nghĩ...",
            "Thinking": "Đang suy nghĩ...",
            "Finished": "Đã xong.",
            "Error": "Có lỗi xảy ra.",
            "Searching": "Đang tìm kiếm...",
            "Opening": "Đang mở...",
            "Clicking": "Đang nhấn...",
            "Typing": "Đang nhập..."
        }
        for eng, vie in text_map.items():
            if eng.lower() in text.lower():
                text = vie
                break

        # Clean text (remove markers, URLs, etc.)
        clean_text = re.sub(r'https?://\S+', '', text)
        clean_text = re.sub(r'[|#*\[\]]', ' ', clean_text).strip()
        
        if not clean_text:
            return
            
        print(f"[SKEMI]: {clean_text}")

        if self._tts_queue.full():
            try: self._tts_queue.get_nowait()
            except: pass
        self._tts_queue.put(clean_text)

    def _speak_worker_loop(self):
        """Background worker to process TTS requests sequentially."""
        while True:
            text = self._tts_queue.get()
            if text:
                self._speak_sync(text)
            self._tts_queue.task_done()

    def _speak_sync(self, text: str):
        """Synchronous version of speak to be called by worker thread."""
        with self._tts_lock:
            self.is_speaking = True
            self._emit_status("speaking", transcript="")
            try:
                asyncio.run(self._generate_and_play(text))
            except Exception as e:
                self.logger.error(f"TTS error: {e}")
                self._speak_offline(text)
            finally:
                self.is_speaking = False
                if self.is_listening:
                    self._emit_status("listening", transcript="")

    def _speak_worker(self, text: str):
        with self._tts_lock:
            self.is_speaking = True
            self._emit_status("speaking", transcript="")
            try:
                # Run async TTS in a new event loop for this thread
                asyncio.run(self._generate_and_play(text))
            except Exception as e:
                self.logger.error(f"TTS error: {e}")
                # Use offline fallback if everything fails
                self._speak_offline(text)
            finally:
                self.is_speaking = False
                if self.is_listening:
                    self._emit_status("listening", transcript="")

    def _speak_offline(self, text: str):
        """Fallback to pyttsx3 for offline speech."""
        if not self.offline_engine:
            return
        try:
            self.logger.info(f"Using offline TTS for: {text[:30]}...")
            self.offline_engine.say(text)
            self.offline_engine.runAndWait()
        except Exception as e:
            self.logger.error(f"Offline TTS error: {e}")

    def _play_audio_file(self, path: Path | str) -> bool:
        """Play an audio file through pygame, returning whether playback started cleanly."""
        if not self.pygame_initialized:
            self.logger.warning("Pygame mixer is not initialized; using offline TTS fallback.")
            return False
        try:
            audio_path = str(path)
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 256:
                self.logger.warning(f"TTS audio file is missing or too small: {audio_path}")
                return False
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()
            started_at = time.time()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.unload()
            elapsed = time.time() - started_at
            if elapsed < 0.15:
                self.logger.warning(f"Pygame playback ended too quickly ({elapsed:.2f}s); falling back.")
                return False
            self.logger.info(f"TTS playback finished in {elapsed:.2f}s")
            return True
        except Exception as e:
            self.logger.warning(f"Pygame playback failed: {e}")
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            return False

    async def _generate_and_play(self, text: str):
        # Hash text to use as cache filename
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{text_hash}.mp3"
        
        # Check cache first
        if cache_path.exists():
            try:
                self.logger.info(f"TTS Cache HIT: {text[:30]}...")
                if self._play_audio_file(cache_path):
                    return
            except Exception as e:
                self.logger.warning(f"Cache play failed, re-downloading: {e}")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Generate TTS with retry
            max_retries = 2
            success = False
            if HAS_EDGE_TTS:
                for attempt in range(max_retries):
                    try:
                        communicate = edge_tts.Communicate(text, self.tts_voice)
                        await communicate.save(tmp_path)
                        success = True
                        # Save to cache if successful
                        shutil.copy(tmp_path, str(cache_path))
                        break
                    except Exception as e:
                        self.logger.warning(f"TTS attempt {attempt+1} failed: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5)
            
            if not success:
                # Use offline fallback
                self._speak_offline(text)
                return

            # Play using pygame
            if not self._play_audio_file(tmp_path):
                self._speak_offline(text)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except:
                pass

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ve = SkemiVoiceEngine()
    ve.start(lambda cmd: print(f"\n>>> EXECUTING VOICE COMMAND: {cmd}\n"))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ve.stop()
