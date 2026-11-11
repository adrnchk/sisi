"""Сісі: консольний чат + іконка в треї + голос + спостерігач. Запуск: run_sisi.bat"""
import re
import sys
import threading
import time

from . import brain, emotions, settings
from .notify import toast
from .tts import TTS
from .tray import Tray
from .voice import Voice
from .watcher import Watcher

NAME = "Сісі"
_print_lock = threading.Lock()


def _bubbles_with_emotions(text: str):
    """[(емоція або None, текст бульбашки)]"""
    parts = re.split(r"^\s*-{3,}\s*$", text, flags=re.MULTILINE)
    out = [emotions.parse(p) for p in parts if p.strip()]
    return [(e, t) for e, t in out if t]


def _bubbles(text: str):
    return [t for _, t in _bubbles_with_emotions(text)]


class App:
    def __init__(self):
        self.tts = TTS()
        self.voice = Voice(on_text=self.on_voice, on_status=self.status)
        self.watcher = Watcher(self.deliver)
        self.tray = Tray(self)

    # ---------- вивід ----------

    def status(self, text):
        with _print_lock:
            print(f"\n  ({text})\nТи: ", end="", flush=True)

    def say(self, text: str, prefix: str = "", speak=True):
        bubbles = _bubbles(text)
        with _print_lock:
            for i, part in enumerate(bubbles):
                if i:
                    time.sleep(min(0.4 + len(part) * 0.02, 2.0))  # ніби друкує
                print(f"\n{prefix}{NAME}: {part}")
                if speak:
                    self.tts.say(part)
            print()

    def deliver(self, text: str, kind: str):
        """Репліка, яку Сісі пише першою (подія або нагадування)."""
        toast(" · ".join(_bubbles(text)[:3]))
        print()
        self.say(text, prefix="⏰ " if kind == "reminder" else "💬 ", speak=not self.watcher.in_game)
        with _print_lock:
            print("Ти: ", end="", flush=True)

    # ---------- ввід ----------

    def handle(self, text: str, via_voice=False):
        if settings.get("paused"):
            print(f"\n  ({NAME} на паузі — розбуди її в треї)\n")
            return
        self.tts.stop()  # перебив — замовкає
        if via_voice:
            with _print_lock:
                print(f"\nТи (голосом): {text}")
        print("  ...", end="\r", flush=True)
        try:
            answer = brain.reply(text)
        except Exception as e:  # noqa: BLE001
            print(f"\n[помилка: {e}]\n")
            return
        self.say(answer)
        if via_voice:
            with _print_lock:
                print("Ти: ", end="", flush=True)

    def on_voice(self, text):
        threading.Thread(target=self.handle, args=(text, True), daemon=True).start()

    # ---------- пауза ----------

    def set_paused(self, paused: bool):
        settings.set("paused", paused)
        if paused:
            self.tts.stop()
            self.voice.unload()  # звільнити пам'ять моделі розпізнавання
            self.status(f"{NAME} на повній паузі: не слухає, не дивиться, не витрачає ліміт")
        else:
            self.status(f"{NAME} знову тут")

    # ---------- запуск ----------

    def run(self):
        self.tray.start()
        self.voice.start()
        self.watcher.start()
        key = settings.get("ptt_key")
        print(f"{NAME} онлайн. Пиши тут або тримай «{key}», щоб говорити голосом.\n"
              f"Налаштування — в іконці в треї. Команди: /нова — нова розмова, /вихід — вийти.\n")
        if settings.get("paused"):
            print(f"  ({NAME} зараз на паузі — розбуди її в треї)\n")
        while True:
            try:
                text = input("Ти: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text in ("/вихід", "/exit"):
                break
            if text in ("/нова", "/new"):
                brain.new_session()
                print("(нова розмова, пам'ять лишилась)\n")
                continue
            self.handle(text)
        self.tray.icon.stop()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    App().run()


if __name__ == "__main__":
    main()
