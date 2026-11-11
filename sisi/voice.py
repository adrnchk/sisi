"""Голосовий ввід: тримаєш клавішу push-to-talk — Сісі слухає, відпускаєш — розпізнає (faster-whisper, локально на CPU)."""
import gc
import os
import threading
import warnings

# прибрати шумні попередження huggingface_hub у консолі чату
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
warnings.filterwarnings("ignore", module="huggingface_hub")

import keyboard
import numpy as np
import sounddevice as sd

from . import settings
from .store import log_action

SAMPLE_RATE = 16000
MIN_SECONDS = 0.4


class Voice:
    def __init__(self, on_text, on_status):
        """on_text(text) — розпізнана фраза; on_status(text) — службові повідомлення."""
        self.on_text = on_text
        self.on_status = on_status
        self._model = None
        self._model_lock = threading.Lock()
        self._frames = []
        self._stream = None
        self._hooks = []
        self.recording = False

    # ---------- модель ----------

    def _get_model(self):
        with self._model_lock:
            if self._model is None:
                self.on_status("вантажу розпізнавання мови (перший раз може завантажуватись кілька хвилин)...")
                from faster_whisper import WhisperModel
                self._model = WhisperModel(settings.get("whisper_model"), device="cpu", compute_type="int8")
            return self._model

    def unload(self):
        """Звільнити пам'ять (для паузи)."""
        with self._model_lock:
            self._model = None
        gc.collect()

    # ---------- клавіша ----------

    def start(self):
        self.bind(settings.get("ptt_key"))

    def bind(self, key: str):
        """Слухаємо всі клавіші й порівнюємо точну назву: так правий і лівий Ctrl
        (у них однаковий скан-код) не плутаються."""
        self.unbind()
        self._key = key.lower()

        def on_event(ev):
            if (ev.name or "").lower() != self._key:
                return
            if ev.event_type == keyboard.KEY_DOWN:
                self._down(ev)
            else:
                self._up(ev)

        self._hooks = [keyboard.hook(on_event)]

    def unbind(self):
        for h in self._hooks:
            try:
                keyboard.unhook(h)
            except (KeyError, ValueError):
                pass
        self._hooks = []

    @staticmethod
    def capture_key() -> str:
        """Чекає натискання однієї клавіші й повертає її назву."""
        while True:
            ev = keyboard.read_event(suppress=False)
            if ev.event_type == keyboard.KEY_DOWN and ev.name:
                return ev.name

    # ---------- запис ----------

    def _down(self, _ev):
        if self.recording or settings.get("paused") or not settings.get("voice_input"):
            return
        self.recording = True
        self._frames = []
        try:
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                          device=self.device_index(),
                                          callback=lambda data, *_: self._frames.append(data.copy()))
            self._stream.start()
            self.on_status("🎙 слухаю...")
        except Exception as e:  # noqa: BLE001
            self.recording = False
            self.on_status(f"мікрофон недоступний: {e}")

    def _up(self, _ev):
        if not self.recording:
            return
        self.recording = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass
        frames, self._frames = self._frames, []
        if not frames:
            return
        audio = np.concatenate(frames).flatten()
        if len(audio) < SAMPLE_RATE * MIN_SECONDS:
            self.on_status("занадто коротко — тримай клавішу, поки говориш")
            return
        peak = float(np.abs(audio).max())
        if peak < 0.01:
            self.on_status(f"тиша з мікрофона «{self.device_name()}» — обери інший мікрофон у треї")
            log_action("stt_silence", self.device_name())
            return
        self.on_status("розпізнаю...")
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _transcribe(self, audio):
        try:
            segments, _ = self._get_model().transcribe(audio, language="uk", vad_filter=True, beam_size=5)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:  # noqa: BLE001
            log_action("stt_error", str(e)[:200])
            self.on_status(f"не вдалось розпізнати: {e}")
            return
        log_action("stt", text[:200] or "(порожньо)")
        if text:
            self.on_text(text)
        else:
            self.on_status("не розібрала слів — спробуй ще раз, ближче до мікрофона")

    # ---------- мікрофон ----------

    @staticmethod
    def microphones():
        """Назви мікрофонів (MME — ті самі, що в налаштуваннях звуку Windows)."""
        names = []
        for d in sd.query_devices():
            api = sd.query_hostapis(d["hostapi"])["name"]
            if d["max_input_channels"] > 0 and api == "MME" and "Sound Mapper" not in d["name"]:
                names.append(d["name"])
        return names

    @staticmethod
    def device_index():
        """Індекс вибраного мікрофона (None = стандартний Windows)."""
        want = settings.get("mic")
        if not want:
            return None
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["name"] == want:
                return i
        return None

    def device_name(self):
        i = self.device_index()
        return sd.query_devices(i if i is not None else sd.default.device[0])["name"]
