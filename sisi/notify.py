"""Сповіщення Windows (toast)."""
from winotify import Notification, audio

from .store import log_action


def toast(text: str, title: str = "Сісі"):
    msg = " ".join(text.split())
    if len(msg) > 220:
        msg = msg[:217] + "..."
    try:
        n = Notification(app_id="Сісі", title=title, msg=msg, duration="short")
        n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception as e:  # noqa: BLE001
        log_action("toast_error", str(e)[:200])
