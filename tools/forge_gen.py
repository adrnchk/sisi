"""Генерація варіантів Сісі через API Forge (txt2img). Зберігає PNG і аркуш-превʼю з номерами seed.

Запуск: .venv\\Scripts\\python.exe tools\\forge_gen.py [кількість] [додаткові теги]
"""
import base64
import io
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

API = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUT = Path(__file__).resolve().parent.parent / "data" / "assets" / "candidates"

BASE = ("1girl, solo, original, maid, maid headdress, short hair, black hair, bob cut, pink eyes, "
        "navy maid dress, white apron, white gloves, lace jabot, teal bow, gem brooch, upper body, "
        "looking at viewer, light smile, simple background, white background, "
        "masterpiece, high score, great score, absurdres")
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, "
            "cropped, worst quality, low quality, low score, bad score, average score, signature, "
            "watermark, username, blurry")


def generate(prompt, seed=-1):
    body = {
        "prompt": prompt, "negative_prompt": NEGATIVE, "seed": seed,
        "sampler_name": "Euler a", "steps": 28, "cfg_scale": 5, "width": 832, "height": 1216,
        "override_settings": {"sd_model_checkpoint": "animagine-xl-4.0-opt"},
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.load(r)
    info = json.loads(data["info"])
    return Image.open(io.BytesIO(base64.b64decode(data["images"][0]))), info["seed"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    extra = " ".join(sys.argv[2:])
    prompt = BASE + (", " + extra if extra else "")
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    results = []
    for i in range(n):
        img, seed = generate(prompt)
        path = OUT / f"sisi_{stamp}_{i + 1}_seed{seed}.png"
        img.save(path)
        results.append((img, seed))
        print(f"{i + 1}/{n} seed={seed} -> {path.name}", flush=True)
    # аркуш-превʼю
    w, h = 416, 608
    sheet = Image.new("RGB", (w * n, h + 40), "#1a1326")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    for i, (img, seed) in enumerate(results):
        sheet.paste(img.resize((w, h)), (i * w, 0))
        d.text((i * w + 12, h + 6), f"#{i + 1}  seed {seed}", fill="#e8d8ff", font=font)
    sheet_path = OUT / f"sheet_{stamp}.jpg"
    sheet.save(sheet_path, quality=88)
    print("SHEET", sheet_path)


if __name__ == "__main__":
    main()
