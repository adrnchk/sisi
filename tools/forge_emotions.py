"""Емоції Сісі через inpaint обличчя базової картинки (поза й полотно не змінюються).

Запуск:
  .venv\\Scripts\\python.exe tools\\forge_emotions.py [спроб=3] [емоція ...]        — емоції з бази
  .venv\\Scripts\\python.exe tools\\forge_emotions.py frames <спрайт.png> <емоція>  — кадри _talk і _blink
Результат: data/assets/emotions_raw/<емоція>_<n>.png + аркуш sheet_<...>.jpg
"""
import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forge_gen import BASE, NEGATIVE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:7860/sdapi/v1/img2img"
BASE_IMG = ROOT / "data" / "assets" / "sisi_base_calm.png"
OUT = ROOT / "data" / "assets" / "emotions_raw"
W, H = 832, 1216

# зони на базовій картинці (координати 832x1216)
FACE = [(250, 470, 575, 740)]
EYES = [(262, 540, 380, 635), (432, 490, 530, 590)]
MOUTH = [(380, 635, 485, 705)]

# емоція: (теги замість "light smile", зона, denoise)
EMOTIONS = {
    "calm":      ("light smile, closed mouth", FACE, 0.35),
    "happy":     ("smile, happy, open mouth, bright eyes", FACE, 0.6),
    "laugh":     ("laughing, closed eyes, ^_^, open mouth, happy", FACE, 0.7),
    "smug":      ("smug, smirk, half-closed eyes, raised eyebrow", FACE, 0.62),
    "shy":       ("blush, embarrassed, looking away, wavy mouth, nose blush", FACE, 0.62),
    "sad":       ("sad, frown, looking down, teary eyes", FACE, 0.62),
    "angry":     ("pout, angry, puffed cheeks, furrowed brow, v-shaped eyebrows", FACE, 0.65),
    "surprised": ("surprised, wide-eyed, open mouth, :o, raised eyebrows", FACE, 0.65),
    "thinking":  ("thinking, looking up, closed mouth, pensive", FACE, 0.6),
    "worried":   ("worried, nervous, frown, raised eyebrows", FACE, 0.6),
    "sleepy":    ("sleepy, half-closed eyes, yawning, open mouth, tired", FACE, 0.65),
}
FRAMES = {
    "talk":  ("open mouth, talking", MOUTH, 0.55),
    "blink": ("closed eyes", EYES, 0.6),
}


def b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def make_mask(boxes):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for b in boxes:
        d.ellipse(b, fill=255)
    return m.filter(ImageFilter.GaussianBlur(4))


def inpaint(img, tags, boxes, denoise, n):
    body = {
        "init_images": [b64(img)], "mask": b64(make_mask(boxes)),
        "prompt": BASE.replace("light smile", tags), "negative_prompt": NEGATIVE,
        "sampler_name": "Euler a", "steps": 30, "cfg_scale": 5, "width": W, "height": H,
        "denoising_strength": denoise, "inpainting_fill": 1, "inpaint_full_res": True,
        "inpaint_full_res_padding": 48, "mask_blur": 8, "seed": -1, "n_iter": n, "batch_size": 1,
        "override_settings": {"sd_model_checkpoint": "animagine-xl-4.0-opt"},
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        data = json.load(r)
    return [Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB") for s in data["images"][:n]]


def sheet(rows, path):
    """rows: [(назва, [картинки])] — показує обличчя крупно."""
    cw, ch = 300, 300
    cols = max(len(r[1]) for r in rows)
    s = Image.new("RGB", (cols * cw + 140, len(rows) * ch), "#1a1326")
    d = ImageDraw.Draw(s)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for y, (name, imgs) in enumerate(rows):
        d.text((10, y * ch + ch // 2 - 12), name, fill="#e8d8ff", font=font)
        for x, im in enumerate(imgs):
            s.paste(im.crop((200, 420, 620, 840)).resize((cw, ch)), (140 + x * cw, y * ch))
            d.text((140 + x * cw + 6, y * ch + 4), str(x + 1), fill="#ff8ad8", font=font)
    s.save(path, quality=88)
    print("SHEET", path, flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    if args and args[0] == "frames":
        src, emo = Image.open(args[1]).convert("RGB"), args[2]
        rows = []
        for kind, (tags, boxes, dn) in FRAMES.items():
            imgs = inpaint(src, tags, boxes, dn, 3)
            for i, im in enumerate(imgs, 1):
                im.save(OUT / f"{emo}_{kind}_{i}.png")
            rows.append((f"{emo}_{kind}", imgs))
            print("done", emo, kind, flush=True)
        sheet(rows, OUT / f"sheet_{emo}_frames.jpg")
        return
    n = int(args[0]) if args and args[0].isdigit() else 3
    names = [a for a in args if not a.isdigit()] or list(EMOTIONS)
    base = Image.open(BASE_IMG).convert("RGB")
    rows = []
    for name in names:
        tags, boxes, dn = EMOTIONS[name]
        imgs = inpaint(base, tags, boxes, dn, n)
        for i, im in enumerate(imgs, 1):
            im.save(OUT / f"{name}_{i}.png")
        rows.append((name, imgs))
        print("done", name, flush=True)
    sheet(rows, OUT / f"sheet_{'_'.join(names) if len(names) < 4 else 'all'}.jpg")


if __name__ == "__main__":
    main()
