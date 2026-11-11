"""Емоції Сісі: тег на початку кожної бульбашки, напр. «[laugh] ахаха, ну ти й скажеш».

Кожній емоції відповідає спрайт data/assets/sprites/<емоція>.png (або .webp/.jpg).
Немає спрайта — лишається попередній. Немає calm — використовується портрет зі шпалер.
"""
import re

EMOTIONS = {
    "calm": "спокійна — за замовчуванням",
    "happy": "радісна, задоволена",
    "laugh": "сміється",
    "smug": "лукава, кокетлива усмішка, підколює",
    "shy": "соромиться, червоніє, ніяковіє",
    "sad": "сумна",
    "angry": "сердиться, дується, ревнує",
    "surprised": "здивована, шокована",
    "thinking": "задумалась, міркує",
    "worried": "хвилюється, турбується",
    "sleepy": "сонна, втомлена",
}

_TAG = re.compile(r"^\s*\[([a-zA-Z_]+)\]\s*")
_ANY_TAG = re.compile(r"\[(" + "|".join(EMOTIONS) + r")\]\s*", re.I)


def parse(bubble: str):
    """«[laugh] текст» -> ("laugh", "текст"). Невідомий або відсутній тег -> (None, текст)."""
    m = _TAG.match(bubble)
    if m and m.group(1).lower() in EMOTIONS:
        return m.group(1).lower(), bubble[m.end():].strip()
    return None, bubble.strip()


def strip(text: str) -> str:
    """Прибрати всі теги емоцій з тексту (для консолі, озвучки, сповіщень)."""
    return _ANY_TAG.sub("", text).strip()


def persona_list() -> str:
    return "\n".join(f"- `[{k}]` — {v}" for k, v in EMOTIONS.items())
