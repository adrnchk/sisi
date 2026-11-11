"""Консольний чат із Сісі. Запуск: run_sisi.bat"""
import re
import sys
import threading
import time

from . import brain
from .store import pop_due_reminders

NAME = "Сісі"
_print_lock = threading.Lock()


def _bubbles(text: str):
    parts = re.split(r"^\s*-{3,}\s*$", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def say(text: str):
    with _print_lock:
        for i, part in enumerate(_bubbles(text)):
            if i:
                time.sleep(min(0.4 + len(part) * 0.02, 2.0))  # ніби друкує
            print(f"\n{NAME}: {part}")
        print()


def _reminder_loop():
    while True:
        for r in pop_due_reminders():
            with _print_lock:
                print(f"\n\n⏰ {NAME}: {r['message']}\n\nТи: ", end="", flush=True)
        time.sleep(10)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    threading.Thread(target=_reminder_loop, daemon=True).start()
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
