"""Зменшує картинку й домальовує простір довкола (outpaint) через API Forge, щоб у кадр вліз увесь очіпок.

Запуск: .venv\\Scripts\\python.exe tools\\forge_outpaint.py <вхід.png> <вихід.png> [масштаб=0.82] [кількість=3]
"""
import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forge_gen import BASE, NEGATIVE  # noqa: E402

API = "http://127.0.0.1:7860/sdapi/v1/img2img"
W, H = 832, 1216


def b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 0.82
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    img = Image.open(src).convert("RGB")
    sw, sh = int(W * scale), int(H * scale)
    small = img.resize((sw, sh), Image.LANCZOS)
    x, y = (W - sw) // 2, H - sh                     # персонажка лишається внизу, простір — зверху й з боків
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(small, (x, y))
    mask = Image.new("L", (W, H), 255)               # біле = домалювати
    ImageDraw.Draw(mask).rectangle((x + 20, y + 20, x + sw - 20, H), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(6))
    body = {
        "init_images": [b64(canvas)], "mask": b64(mask), "prompt": BASE, "negative_prompt": NEGATIVE,
        "sampler_name": "Euler a", "steps": 30, "cfg_scale": 5, "width": W, "height": H,
        "denoising_strength": 0.95, "inpainting_fill": 0, "inpaint_full_res": False, "mask_blur": 12,
        "seed": -1, "n_iter": n, "batch_size": 1,
        "override_settings": {"sd_model_checkpoint": "animagine-xl-4.0-opt"},
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.load(r)
    outs = [Image.open(io.BytesIO(base64.b64decode(s))) for s in data["images"][:n]]
    for i, o in enumerate(outs, 1):
        o.save(dst.with_name(f"{dst.stem}_{i}{dst.suffix}"))
    sheet = Image.new("RGB", (416 * n, 608), "white")
    for i, o in enumerate(outs):
        sheet.paste(o.resize((416, 608)), (i * 416, 0))
    sheet.save(dst.with_name(f"{dst.stem}_sheet.jpg"), quality=88)
    print("OK", dst.with_name(f"{dst.stem}_sheet.jpg"))


if __name__ == "__main__":
    main()
