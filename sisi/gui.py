"""Сісі з вікном у стилі візуальної новели. Запуск: run_sisi.bat (або автозапуск).

  pythonw -m sisi.gui          — показати вікно
  pythonw -m sisi.gui --tray   — стартувати тихо в треї (автозапуск з Windows)
"""
import base64
import ctypes
import json
import sys
import threading

import webview

from . import brain, emotions, settings
from .chat import App, _bubbles, _bubbles_with_emotions
from .notify import toast
from .paths import DATA, ROOT
from .store import log_action

UI = ROOT / "sisi" / "ui" / "index.html"
PORTRAIT = DATA / "assets" / "sisi_portrait.jpg"
BG = DATA / "assets" / "sisi_bg.jpg"


def _data_url(path):
    if not path.exists():
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def _html():
    return (UI.read_text(encoding="utf-8")
            .replace("{{PORTRAIT}}", _data_url(PORTRAIT))
            .replace("{{BG}}", _data_url(BG)))


class Api:
    """Те, що викликає JavaScript з вікна."""

    def __init__(self, app):
        self._app = app

    def send(self, text):
        threading.Thread(target=self._app.handle, args=(text,), daemon=True).start()

    def ready(self):
        self._app.on_ready()

    def sprite(self, name):
        """Спрайт емоції як data URL ("" — нема такого спрайта)."""
        return sprite_url(name)


SPRITES = DATA / "assets" / "sprites"
_MIME = {".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def sprite_url(name: str) -> str:
    """name — емоція (calm) або її кадр (calm_talk — рот відкритий, calm_blink — очі закриті)."""
    base = name.removesuffix("_talk").removesuffix("_blink")
    if base not in emotions.EMOTIONS:
        return ""
    for ext, mime in _MIME.items():
        f = SPRITES / f"{name}{ext}"
        if f.exists():
            return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    return _data_url(PORTRAIT) if name == "calm" else ""


class GuiApp(App):
    def __init__(self, start_hidden=False):
        super().__init__()
        self.start_hidden = start_hidden
        self.window = None
        self._ready = threading.Event()
        self.tts.on_playing = lambda on: self.js("setTalking", on)
        settings.on_change(lambda k, v: self.js("setPaused", v) if k == "paused" else None)

    # ---------- міст у вікно ----------

    def js(self, fn, *args):
        if not self.window or not self._ready.is_set():
            return
        try:
            self.window.evaluate_js(f"{fn}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)})")
        except Exception as e:  # noqa: BLE001
            log_action("gui_error", str(e)[:200])

    def on_ready(self):
        self._ready.set()
        if settings.get("paused"):
            self.js("setPaused", True)

    def show_window(self):
        if self.window:
            self.window.show()
            self.window.restore()

    # ---------- перевизначення виводу консольного App ----------

    def status(self, text):
        self.js("setStatus", text)

    def say(self, text: str, prefix: str = "", speak=True, proactive=False):
        items = _bubbles_with_emotions(text)
        self.js("sisiSay", [{"emotion": e, "text": t} for e, t in items], proactive)
        if speak:
            for _, t in items:
                self.tts.say(t)

    def deliver(self, text: str, kind: str):
        visible = self.window is not None and not getattr(self.window, "hidden_by_user", False)
        if not visible:
            toast(" · ".join(_bubbles(text)[:3]))
        self.say(text, speak=not self.watcher.in_game, proactive=True)

    def handle(self, text: str, via_voice=False):
        text = text.strip()
        if text in ("/нова", "/new"):
            brain.new_session()
            self.status("нова розмова, пам'ять лишилась")
            return
        if settings.get("paused"):
            self.status("Сісі на паузі — розбуди її в треї")
            return
        self.tts.stop()
        if via_voice:
            self.js("userSaid", text, True)
        self.js("setThinking", True)
        try:
            answer = brain.reply(text)
        except Exception as e:  # noqa: BLE001
            self.js("setThinking", False)
            self.status(f"помилка: {str(e)[:150]}")
            return
        self.js("setThinking", False)
        self.say(answer)

    # ---------- запуск ----------

    def _on_closing(self):
        """Хрестик ховає вікно в трей, а не вимикає Сісі."""
        self.window.hidden_by_user = True
        self.window.hide()
        return False

    def _on_shown(self):
        self.window.hidden_by_user = False

    def run(self):
        self.window = webview.create_window(
            "Сісі", html=_html(), js_api=Api(self), width=1100, height=760, min_size=(720, 560),
            background_color="#0c0816", hidden=self.start_hidden)
        self.window.hidden_by_user = self.start_hidden
        self.window.events.closing += self._on_closing
        self.window.events.shown += self._on_shown
        self.tray.start()
        self.voice.start()
        self.watcher.start()
        webview.start()


def _single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\Sisi.SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if sys.stdout is None:  # pythonw: нема консолі — пишемо помилки в лог
        log = open(DATA / "gui.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stderr = log
    if not _single_instance():
        toast("Я вже тут, у треї 🙂")
        return
    GuiApp(start_hidden="--tray" in sys.argv).run()


if __name__ == "__main__":
    main()
