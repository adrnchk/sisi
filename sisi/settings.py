"""Налаштування Сісі (data/settings.json). Змінюються з іконки в треї."""
import json
import threading

from .paths import DATA

FILE = DATA / "settings.json"
DEFAULTS = {
    "paused": False,          # повна пауза: нічого не слухає, не дивиться, не витрачає ліміт
    "game_mode": False,
    "guard": False,           # запобіжник guard.py (системні папки, остаточне видалення тощо)       # ігровий режим вручну (автоматично вмикається, коли запущена гра)
    "tts": True,              # озвучувати відповіді
    "voice_input": True,      # голосовий ввід (push-to-talk)
    "ptt_key": "right ctrl",  # клавіша push-to-talk (одна клавіша)
    "mic": "",                # назва мікрофона ("" = стандартний Windows)
    "tts_voice": "uk-UA-PolinaNeural",
    "tts_rate": "+8%",
    "tts_pitch": "+12Hz",
    "whisper_model": "large-v3-turbo",
}
_lock = threading.Lock()
_listeners = []


def _load():
    try:
        return {**DEFAULTS, **json.loads(FILE.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def get(key):
    with _lock:
        return _load()[key]


def set(key, value):  # noqa: A001
    with _lock:
        s = _load()
        s[key] = value
        FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    for fn in list(_listeners):
        fn(key, value)


def toggle(key):
    set(key, not get(key))
    return get(key)


def on_change(fn):
    _listeners.append(fn)
