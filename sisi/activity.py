"""Що зараз робить хазяїн: активне вікно, історія Opera, категорії занять."""
import ctypes
import os
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import psutil

OPERA_HISTORY = Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "Default" / "History"

# Сайти, яких Сісі не бачить в історії та в заголовках вікон (можна доповнювати)
PRIVATE_DOMAINS = {
    "bankaustria.at", "erstebank.at", "george.sparkasse.at", "raiffeisen.at", "bawag.at",
    "n26.com", "revolut.com", "paypal.com", "finanzonline.bmf.gv.at", "accounts.google.com",
}
PRIVATE_TITLE_WORDS = ("banking", "online-banking", "login", "anmelden", "passwort", "password")

_user32 = ctypes.windll.user32


def foreground():
    """(процес, заголовок) активного вікна."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    length = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value).name()
    except (psutil.Error, ValueError):
        proc = ""
    return proc, buf.value


def _private_title(title: str) -> bool:
    t = title.casefold()
    return any(w in t for w in PRIVATE_TITLE_WORDS)


BROWSERS = {"opera.exe", "chrome.exe", "msedge.exe", "firefox.exe"}
CODE = {"code.exe", "pycharm64.exe", "devenv.exe", "idea64.exe", "windowsterminal.exe",
        "docker desktop.exe", "cursor.exe", "powershell.exe", "cmd.exe"}
CHAT = {"discord.exe": "Discord", "telegram.exe": "Telegram", "slack.exe": "Slack"}
ANIME_SITES = ("anime", "crunchyroll", "aniwatch", "animego", "jut.su", "hianime", "netflix")


def categorize(proc: str, title: str):
    """Повертає (категорія, опис) для активного вікна. Категорії стабільні, опис — людський."""
    p = proc.lower()
    if _private_title(title):
        return "private", "щось особисте (деталі приховані)"
    if p in BROWSERS:
        clean = title.rsplit(" - ", 1)[0] if " - " in title else title
        tl = title.casefold()
        if "youtube" in tl:
            return "youtube", f"YouTube: «{clean.replace(' - YouTube', '')}»"
        if any(s in tl for s in ANIME_SITES):
            return "anime", f"дивиться аніме/кіно: «{clean}»"
        if "twitch" in tl:
            return "twitch", f"Twitch: «{clean}»"
        return "browser", f"браузер: «{clean}»"
    if p in CODE:
        return "work", f"працює ({proc}): «{title[:80]}»"
    if p in CHAT:
        return "chat", f"сидить у {CHAT[p]}"
    if p in ("steam.exe", "battle.net.exe", "faceit.exe"):
        return "launcher", f"лаунчер {proc.removesuffix('.exe')}"
    if not p or p in ("explorer.exe", "python.exe", "cmd.exe"):
        return "idle", "робочий стіл / провідник"
    return "app", f"{proc.removesuffix('.exe')}: «{title[:60]}»"


def _chrome_time(us: int) -> datetime:
    return (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=us)).astimezone().replace(tzinfo=None)


def opera_history(minutes: int = 60, limit: int = 30, search: str = ""):
    """Останні відвідування Opera: [(час, заголовок, домен)]. Банки й логіни відфільтровано."""
    if not OPERA_HISTORY.exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "History"
        shutil.copy2(OPERA_HISTORY, copy)  # оригінал заблокований, поки Opera відкрита
        since = datetime.now() - timedelta(minutes=minutes)
        since_us = int((since.astimezone(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1e6)
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT v.visit_time, u.title, u.url FROM visits v JOIN urls u ON u.id = v.url "
                "WHERE v.visit_time >= ? ORDER BY v.visit_time DESC LIMIT 400", (since_us,)).fetchall()
        finally:
            con.close()
    out, seen = [], set()
    needle = search.casefold()
    for t, title, url in rows:
        dom = urlparse(url).hostname or ""
        dom = dom.removeprefix("www.")
        if any(dom == d or dom.endswith("." + d) for d in PRIVATE_DOMAINS) or _private_title(title or ""):
            continue
        title = (title or dom).strip()
        if needle and needle not in title.casefold() and needle not in dom:
            continue
        key = (title, dom)
        if key in seen:
            continue
        seen.add(key)
        out.append((_chrome_time(t), title, dom))
        if len(out) >= limit:
            break
    return out


def format_history(items):
    return "\n".join(f"- {t:%H:%M} {title} ({dom})" for t, title, dom in items) or "(нічого)"
