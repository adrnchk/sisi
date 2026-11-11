"""MCP-сервер з інструментами Сісі.

Запускається Claude Code (claude -p) через data/mcp.json.
Жорсткі запобіжники з decisions.md реалізовані тут, у коді, а не в промпті:
  - завантажуються лише зображення (перевірка сигнатури файлу), нічого не запускається;
  - програми відкриваються лише через ярлики меню «Пуск» / робочого столу;
  - кожна дія пишеться в data/actions.log.
"""
import csv
import ctypes
import io
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from sisi.paths import MEMORY, WALLPAPERS  # noqa: E402
from sisi.store import add_reminder, get_state, log_action, update_state  # noqa: E402

mcp = FastMCP("sisi")

UA = "Sisi/0.1 (personal desktop assistant)"
MAX_IMAGE_BYTES = 40 * 1024 * 1024
WALLPAPER_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
MEMORY_SECTIONS = ["Словник користувача", "Про користувача", "Стосунки"]

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATE_AND_SEND = 0x01 | 0x02


# ---------- допоміжне ----------

def _http_get(url, limit=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1 if limit else -1)
    if limit and len(data) > limit:
        raise ValueError("файл завеликий")
    return data


def _image_ext(data: bytes):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"BM":
        return ".bmp"
    return None


def _current_wallpaper():
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buf), buf, 0)
    return buf.value


def _apply_wallpaper(path: str) -> bool:
    return bool(ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATE_AND_SEND))


def _shortcut_dirs():
    dirs = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    return [d for d in dirs if d.is_dir()]


def _find_shortcuts(name: str):
    needle = name.casefold().strip()
    found = {}
    for d in _shortcut_dirs():
        for p in d.rglob("*"):
            if p.suffix.lower() in (".lnk", ".url") and needle in p.stem.casefold():
                found.setdefault(p.stem, p)
    return found


# ---------- інструменти ----------

@mcp.tool()
def search_wallpapers(query: str, count: int = 6) -> str:
    """Шукає шпалери на Wallhaven (лише безпечні, SFW, від 1920x1080).
    Повертає список з прямими посиланнями на зображення (поле url) — їх можна передати в download_image."""
    params = urllib.parse.urlencode({
        "q": query, "purity": "100", "categories": "111",
        "atleast": "1920x1080", "sorting": "relevance",
    })
    data = json.loads(_http_get(f"https://wallhaven.cc/api/v1/search?{params}"))
    items = [
        {"url": w["path"], "resolution": w["resolution"], "colors": w.get("colors", [])}
        for w in data.get("data", [])[: max(1, min(count, 12))]
    ]
    log_action("search_wallpapers", query)
    return json.dumps(items, ensure_ascii=False) if items else "Нічого не знайдено."


@mcp.tool()
def download_image(url: str) -> str:
    """Завантажує зображення (JPG/PNG/BMP) за прямим https-посиланням у папку шпалер Сісі.
    Інші типи файлів відхиляються. Повертає шлях до збереженого файлу."""
    if urllib.parse.urlparse(url).scheme != "https":
        return "Помилка: дозволені лише https-посилання."
    try:
        data = _http_get(url, limit=MAX_IMAGE_BYTES)
    except Exception as e:  # noqa: BLE001
        return f"Помилка завантаження: {e}"
    ext = _image_ext(data)
    if not ext:
        log_action("download_rejected", url)
        return "Помилка: це не зображення JPG/PNG/BMP, файл не збережено."
    name = datetime.now().strftime("wall_%Y%m%d_%H%M%S") + ext
    path = WALLPAPERS / name
    path.write_bytes(data)
    log_action("download_image", f"{url} -> {path}")
    return str(path)


@mcp.tool()
def set_wallpaper(path: str) -> str:
    """Ставить зображення шпалерами робочого столу. Попередні шпалери запам'ятовуються для undo_wallpaper."""
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in WALLPAPER_EXT:
        return "Помилка: потрібен існуючий файл JPG/PNG/BMP."
    if _image_ext(p.read_bytes()[:16]) is None:
        return "Помилка: файл не є зображенням."
    previous = _current_wallpaper()
    if not _apply_wallpaper(str(p.resolve())):
        return "Помилка: Windows не прийняла шпалери."
    update_state(previous_wallpaper=previous)
    log_action("set_wallpaper", f"{p} (було: {previous})")
    return f"Готово. Нові шпалери: {p.name}"


@mcp.tool()
def undo_wallpaper() -> str:
    """Повертає попередні шпалери."""
    prev = get_state().get("previous_wallpaper")
    if not prev or not Path(prev).is_file():
        return "Попередніх шпалер не збережено."
    current = _current_wallpaper()
    _apply_wallpaper(prev)
    update_state(previous_wallpaper=current)
    log_action("undo_wallpaper", prev)
    return f"Повернула попередні шпалери: {Path(prev).name}"


@mcp.tool()
def open_app(name: str) -> str:
    """Відкриває програму за назвою ярлика з меню «Пуск» або робочого столу (наприклад: "Steam", "Dota", "Opera")."""
    found = _find_shortcuts(name)
    if not found:
        return f"Не знайшла ярлика з назвою «{name}»."
    exact = [k for k in found if k.casefold() == name.casefold()]
    if not exact and len(found) > 1:
        return "Знайшла кілька варіантів, уточни: " + ", ".join(sorted(found)[:15])
    key = exact[0] if exact else next(iter(found))
    os.startfile(str(found[key]))  # noqa: S606 — лише ярлики, не довільні файли
    log_action("open_app", str(found[key]))
    return f"Відкрила: {key}"


@mcp.tool()
def open_url(url: str) -> str:
    """Відкриває http/https-сторінку в браузері за замовчуванням."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return "Помилка: лише http/https."
    webbrowser.open(url)
    log_action("open_url", url)
    return "Відкрила в браузері."


@mcp.tool()
def list_desktop() -> str:
    """Показує назви файлів і папок на робочому столі (без вмісту)."""
    desk = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    names = [("[папка] " if p.is_dir() else "") + p.name
             for p in sorted(desk.iterdir()) if p.name.lower() != "desktop.ini"]
    return "\n".join(names) or "Робочий стіл порожній."


@mcp.tool()
def list_running_apps() -> str:
    """Показує, які програми зараз запущені (лише назви процесів з вікнами)."""
    out = subprocess.run(["tasklist", "/v", "/fo", "csv", "/nh"], capture_output=True,
                         text=True, encoding="cp866", errors="replace").stdout
    apps = set()
    for row in csv.reader(io.StringIO(out)):
        if len(row) >= 9 and row[8] not in ("N/A", "", "Н/Д"):
            apps.add(row[0].removesuffix(".exe"))
    return ", ".join(sorted(apps, key=str.casefold)) or "Нічого не знайшла."


@mcp.tool()
def set_reminder(message: str, minutes: int = 0, at_time: str = "") -> str:
    """Ставить нагадування. Або через `minutes` хвилин, або на час `at_time` у форматі HH:MM (сьогодні/завтра).
    `message` — текст, який Сісі скаже, коли час настане (пиши його у своєму стилі)."""
    now = datetime.now()
    if at_time:
        try:
            h, m = map(int, at_time.split(":"))
        except ValueError:
            return "Помилка: час у форматі HH:MM."
        due = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
    elif minutes > 0:
        due = now + timedelta(minutes=minutes)
    else:
        return "Помилка: вкажи minutes або at_time."
    add_reminder(due.isoformat(timespec="seconds"), message)
    log_action("set_reminder", f"{due:%Y-%m-%d %H:%M} {message}")
    return f"Нагадування на {due:%d.%m %H:%M}."


@mcp.tool()
def remember(section: str, fact: str) -> str:
    """Зберігає новий факт у довгострокову пам'ять.
    section: "Словник користувача" (його словечка), "Про користувача" (факти, плани, люди, вподобання) або "Стосунки"."""
    if section not in MEMORY_SECTIONS:
        return "Помилка: section має бути одним з: " + ", ".join(MEMORY_SECTIONS)
    fact = " ".join(fact.split())
    text = MEMORY.read_text(encoding="utf-8") if MEMORY.exists() else "# Пам'ять Сісі\n"
    header = f"## {section}"
    if header not in text:
        text = text.rstrip() + f"\n\n{header}\n- {fact}\n"
    else:
        start = text.index(header)
        nxt = text.find("\n## ", start + len(header))
        end = len(text) if nxt == -1 else nxt
        block = text[start:end].rstrip()
        text = text[:start] + block + f"\n- {fact}\n" + text[end:]
    MEMORY.write_text(text, encoding="utf-8")
    log_action("remember", f"{section}: {fact}")
    return "Запам'ятала."


if __name__ == "__main__":
    mcp.run()
