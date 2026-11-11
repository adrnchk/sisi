"""Маленькі JSON-сховища і журнал дій."""
import json
import threading
from datetime import datetime

from .paths import ACTIONS_LOG, REMINDERS, STATE

_lock = threading.Lock()


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_state():
    with _lock:
        return _read(STATE, {})


def update_state(**kwargs):
    with _lock:
        s = _read(STATE, {})
        s.update(kwargs)
        _write(STATE, s)
        return s


def add_reminder(due_iso, message):
    with _lock:
        items = _read(REMINDERS, [])
        items.append({"due": due_iso, "message": message})
        _write(REMINDERS, items)


def pop_due_reminders(now=None):
    now = now or datetime.now()
    with _lock:
        items = _read(REMINDERS, [])
        due = [r for r in items if datetime.fromisoformat(r["due"]) <= now]
        if due:
            _write(REMINDERS, [r for r in items if r not in due])
        return due


def log_action(action, details):
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{action}\t{details}\n"
    with _lock:
        with ACTIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
