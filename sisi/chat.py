"""Консольний чат із Сісі + фоновий спостерігач. Запуск: run_sisi.bat"""
import re
import sys
import threading
import time

from . import brain
from .notify import toast
from .watcher import Watcher

NAME = "Сісі"
_print_lock = threading.Lock()


def _bubbles(text: str):
    parts = re.split(r"^\s*-{3,}\s*$", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def say(text: str, prefix: str = ""):
    with _print_lock:
        for i, part in enumerate(_bubbles(text)):
            if i:
                time.sleep(min(0.4 + len(part) * 0.02, 2.0))  # ніби друкує
            print(f"\n{prefix}{NAME}: {part}")
        print()


def deliver(text: str, kind: str):
    """Репліка, яку Сісі пише першою (подія або нагадування)."""
    bubbles = _bubbles(text)
    icon = "⏰ " if kind == "reminder" else "💬 "
    toast(" · ".join(bubbles[:3]))
    print()  # з нового рядка, навіть якщо хазяїн щось друкує
    say(text, prefix=icon)
    with _print_lock:
        print("Ти: ", end="", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    Watcher(deliver).start()
    print(f"{NAME} онлайн. Команди: /нова — нова розмова, /вихід — вийти.\n")
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
        print("  ...", end="\r", flush=True)
        try:
            answer = brain.reply(text)
        except Exception as e:  # noqa: BLE001
            print(f"\n[помилка: {e}]\n")
            continue
        say(answer)


if __name__ == "__main__":
    main()
