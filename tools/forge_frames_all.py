"""Кадри рота (_talk) і кліпання (_blink) для всіх обраних емоцій.

Для емоцій, де рот уже відкритий (happy, laugh, surprised, sleepy), кадр _talk — із ЗАКРИТИМ ротом:
вікно чергує кадри, тож рот однаково «рухається».
Запуск: .venv\\Scripts\\python.exe tools\\forge_frames_all.py [спроб=2] [емоція ...]
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forge_emotions as fe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "assets" / "emotions_raw"

# які сирі картинки стали спрайтами (див. prepare_sprites)
CHOSEN = {
    "happy": RAW / "happy_2.png", "laugh": RAW / "laugh2_2.png", "smug": RAW / "smug_3.png",
    "shy": RAW / "shy_1.png", "sad": RAW / "sad_2.png", "angry": RAW / "angry_1.png",
    "surprised": RAW / "surprised_1.png", "thinking": RAW / "thinking_1.png",
    "worried": RAW / "worried_2.png", "sleepy": RAW / "sleepy_3.png",
}
MOUTH = [(370, 625, 495, 715)]
EYES = [(255, 530, 390, 645), (425, 480, 540, 600)]

# емоція: (теги для _talk, теги для _blink або None)
PLAN = {
    "happy":     ("closed mouth, smile, happy", "closed eyes, smile, happy"),
    "laugh":     ("closed mouth, smile, closed eyes, ^_^, blush", None),
    "smug":      ("open mouth, talking, smug, smirk", "closed eyes, smug, smirk"),
    "shy":       ("open mouth, talking, blush, embarrassed", "closed eyes, blush, embarrassed"),
    "sad":       ("open mouth, talking, sad", "closed eyes, sad, frown"),
    "angry":     ("open mouth, talking, angry, pout", "closed eyes, angry, frown, furrowed brow"),
    "surprised": ("closed mouth, surprised", "closed eyes, surprised"),
    "thinking":  ("open mouth, talking, thinking", "closed eyes, thinking"),
    "worried":   ("open mouth, talking, worried", "closed eyes, worried, frown"),
    "sleepy":    ("closed mouth, sleepy, tired", None),
}
NO_EYE_TAGS = fe.BASE.replace("pink eyes, ", "").replace("looking at viewer, ", "")


def main():
    args = sys.argv[1:]
    n = int(args[0]) if args and args[0].isdigit() else 2
    names = [a for a in args if not a.isdigit()] or list(PLAN)
    rows = []
    base_prompt = fe.BASE
    for emo in names:
        src = Image.open(CHOSEN[emo]).convert("RGB")
        talk_tags, blink_tags = PLAN[emo]
        fe.BASE = base_prompt
        talk = fe.inpaint(src, talk_tags, MOUTH, 0.55, n)
        for i, im in enumerate(talk, 1):
            im.save(RAW / f"{emo}_talk_{i}.png")
        rows.append((f"{emo}_talk", talk))
        if blink_tags:
            fe.BASE = NO_EYE_TAGS
            blink = fe.inpaint(src, blink_tags, EYES, 0.9, n)
            for i, im in enumerate(blink, 1):
                im.save(RAW / f"{emo}_blink_{i}.png")
            rows.append((f"{emo}_blink", blink))
        print("done", emo, flush=True)
    fe.BASE = base_prompt
    fe.sheet(rows, RAW / "sheet_frames_all.jpg")


if __name__ == "__main__":
    main()
