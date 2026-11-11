"""Іконка Сісі в треї: пауза, ігровий режим, озвучка, голосовий ввід, клавіша push-to-talk."""
import os
import threading

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import settings


def _icon_image(paused=False):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (120, 120, 130, 255) if paused else (186, 104, 200, 255)
    d.ellipse((2, 2, 62, 62), fill=color)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 38)
    except OSError:
        font = ImageFont.load_default()
    d.text((32, 33), "С", fill="white", font=font, anchor="mm")
    return img


class Tray:
    def __init__(self, app):
        self.app = app
        S = settings
        item = pystray.MenuItem
        has_window = hasattr(app, "show_window")
        self.icon = pystray.Icon("sisi", _icon_image(S.get("paused")), "Сісі", menu=pystray.Menu(
            item("💬 Відкрити чат", lambda: app.show_window(), default=True, visible=has_window),
            item(lambda _: "▶ Розбудити Сісі" if S.get("paused") else "⏸ Повна пауза", self._pause,
                 default=not has_window),
            item("🎮 Ігровий режим", lambda: S.toggle("game_mode"), checked=lambda _: S.get("game_mode")),
            item("🛡 Запобіжник", lambda: S.toggle("guard"), checked=lambda _: S.get("guard")),
            pystray.Menu.SEPARATOR,
            item("🔊 Озвучка відповідей", self._tts, checked=lambda _: S.get("tts")),
            item("🎙 Голосовий ввід", lambda: S.toggle("voice_input"), checked=lambda _: S.get("voice_input")),
            item(lambda _: f"⌨ Кнопка push-to-talk: {S.get('ptt_key')}", self._set_key),
            item("🎤 Мікрофон", pystray.Menu(lambda: self._mic_items())),
            item("🖼 Оновити спрайти", lambda: app.js("clearSprites"), visible=has_window),
            pystray.Menu.SEPARATOR,
            item("Вийти", self._quit),
        ))
        settings.on_change(self._changed)

    def _changed(self, key, value):
        if key == "paused":
            self.icon.icon = _icon_image(value)
            self.icon.title = "Сісі (пауза)" if value else "Сісі"
        self.icon.update_menu()

    def _pause(self):
        self.app.set_paused(not settings.get("paused"))

    def _tts(self):
        if not settings.toggle("tts"):
            self.app.tts.stop()

    def _mic_items(self):
        def choose(name):
            return lambda: settings.set("mic", name)

        def is_current(name):
            return lambda _: settings.get("mic") == name

        items = [pystray.MenuItem("Стандартний Windows", choose(""), checked=is_current(""), radio=True)]
        for name in self.app.voice.microphones():
            items.append(pystray.MenuItem(name, choose(name), checked=is_current(name), radio=True))
        return items

    def _set_key(self):
        def worker():
            self.icon.notify("Натисни клавішу, якою хочеш говорити з Сісі", "Push-to-talk")
            key = self.app.voice.capture_key()
            settings.set("ptt_key", key)
            self.app.voice.bind(key)
            self.icon.notify(f"Тепер тримай «{key}», щоб говорити", "Push-to-talk")
        threading.Thread(target=worker, daemon=True).start()

    def _quit(self):
        self.icon.stop()
        os._exit(0)

    def start(self):
        self.icon.run_detached()
