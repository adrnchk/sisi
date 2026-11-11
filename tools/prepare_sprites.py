"""Прибирає фон зі спрайтів (модель isnet-anime) і кладе їх у data/assets/sprites як прозорі PNG.

Маска вирізання береться ОДНА — з базової картинки, — і застосовується до всіх емоцій:
так силует однаковий до пікселя і при зміні емоцій нічого не «стрибає».

Запуск: .venv\\Scripts\\python.exe tools\\prepare_sprites.py <назва>=<файл.png> [...]
  напр.: calm=data/assets/emotions_raw/calm_2.png laugh=data/assets/emotions_raw/laugh_1.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "assets" / "sisi_base_calm.png"
SPRITES = ROOT / "data" / "assets" / "sprites"
MASK = ROOT / "data" / "assets" / "sisi_alpha.png"


def alpha_mask():
    if MASK.exists():
        return Image.open(MASK).convert("L")
    from rembg import new_session, remove
    cut = remove(Image.open(BASE).convert("RGB"), session=new_session("isnet-anime"), only_mask=True)
    m = cut.convert("L").filter(ImageFilter.GaussianBlur(0.8))
    m.save(MASK)
    return m


def main():
    SPRITES.mkdir(parents=True, exist_ok=True)
    mask = alpha_mask()
    for arg in sys.argv[1:]:
        name, src = arg.split("=", 1)
        img = Image.open(ROOT / src if not Path(src).is_absolute() else src).convert("RGB")
        if img.size != mask.size:
            raise SystemExit(f"{src}: розмір {img.size} не збігається з базою {mask.size}")
        rgba = img.copy()
        rgba.putalpha(mask)
        rgba.save(SPRITES / f"{name}.png")
        print("OK", name, flush=True)


if __name__ == "__main__":
    main()
