"""Мозок Сісі: Claude Code у headless-режимі (claude -p) через підписку."""
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime

import psutil

from .paths import DATA, HOME, MCP_CONFIG, MEMORY, PERSONA, ROOT
from . import settings
from .store import get_state, update_state

MODEL = os.environ.get("SISI_MODEL", "sonnet")
USE_CHROME = os.environ.get("SISI_CHROME", "1") != "0"
# Вбудовані інструменти Claude Code. Файли й PowerShell — під хуком guard.py
BUILTIN_TOOLS = ["WebSearch", "WebFetch", "Read", "Edit", "Write", "Glob", "Grep", "PowerShell"]
GUARD_SETTINGS = DATA / "guard_settings.json"
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]


class BrainError(RuntimeError):
    pass


def _claude_exe():
    exe = shutil.which("claude")
    if not exe:
        raise BrainError("Не знайдено команду `claude`. Встанови Claude Code CLI і перезапусти термінал.")
    return exe


def _system_prompt():
    persona = PERSONA.read_text(encoding="utf-8")
    memory = MEMORY.read_text(encoding="utf-8") if MEMORY.exists() else ""
    return f"{persona}\n\n---\n\n{memory}"


def _write_mcp_config():
    cfg = {"mcpServers": {"sisi": {
        "command": sys.executable,
        "args": [str(ROOT / "sisi" / "tools_server.py")],
    }}}
    MCP_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_guard_settings():
    """Хук-запобіжник (sisi/guard.py) перевіряє кожен виклик файлових інструментів і PowerShell."""
    guard = f'"{sys.executable}" "{ROOT / "sisi" / "guard.py"}"'
    cfg = {"hooks": {"PreToolUse": [{
        "matcher": "|".join(t for t in BUILTIN_TOOLS if t not in ("WebSearch", "WebFetch")),
        "hooks": [{"type": "command", "command": guard}],
    }]}}
    GUARD_SETTINGS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return GUARD_SETTINGS


def _drives():
    return [p.device for p in psutil.disk_partitions(all=False) if "fixed" in p.opts]


def _time_tag():
    now = datetime.now()
    return f"[зараз: {WEEKDAYS[now.weekday()]}, {now:%d.%m.%Y %H:%M}]"


def _clean_env():
    """Якщо Сісі запущено зсередини іншої сесії Claude Code, прибираємо її змінні,
    щоб дочірній claude брав звичайний вхід користувача, а не налаштування хоста."""
    env = dict(os.environ)
    if "CLAUDECODE" in env:
        for k in list(env):
            if k.startswith(("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_")) or k in (
                    "CLAUDECODE", "CLAUDE_PID", "ANTHROPIC_BASE_URL", "CLAUDE_PREVIEW_CLASSIFIER_FLOOR"):
                env.pop(k)
    return env


def _run(message, session_id):
    _write_mcp_config()
    cmd = [
        _claude_exe(), "-p", message,
        "--output-format", "json",
        "--model", MODEL,
        "--system-prompt", _system_prompt(),
        # персона й пам'ять перечитуються щоразу, а не «заморожуються» на початку розмови
        "--system-prompt-snapshot", "off",
        "--mcp-config", str(MCP_CONFIG), "--strict-mcp-config",
        "--tools", ",".join(BUILTIN_TOOLS),
        "--allowedTools", "mcp__sisi", *BUILTIN_TOOLS,
        "--add-dir", *_drives(),
        "--permission-mode", "dontAsk",
        "--disable-slash-commands",
    ]
    if settings.get("guard"):
        cmd += ["--settings", str(_write_guard_settings())]
    if USE_CHROME:
        # Claude in Chrome: вкладки й дії в браузері користувача (потрібне розширення)
        cmd += ["--chrome", "--allowedTools", "mcp__claude-in-chrome"]
    if session_id:
        cmd += ["--resume", session_id]
    proc = subprocess.run(cmd, cwd=HOME, env=_clean_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise BrainError((proc.stderr or proc.stdout or "порожня відповідь").strip()[-800:]) from None
    if data.get("is_error"):
        raise BrainError(str(data.get("result") or data))
    return data


_lock = threading.Lock()  # чат і спостерігач не мають смикати одну сесію одночасно
SKIP = "SKIP"


def _send(message: str) -> str:
    with _lock:
        session_id = get_state().get("session_id")
        try:
            data = _run(message, session_id)
        except BrainError:
            if not session_id:
                raise
            data = _run(message, None)  # сесію не вдалось продовжити — починаємо нову
        update_state(session_id=data.get("session_id"))
        return data.get("result", "").strip()


def reply(user_text: str) -> str:
    """Надсилає повідомлення хазяїна і повертає відповідь Сісі (сирий текст з розділювачами ---)."""
    return _send(f"{_time_tag()}\n{user_text}")


def event(description: str):
    """Повідомляє Сісі про подію на ПК. Повертає її репліку або None, якщо їй нема що сказати."""
    text = _send(
        f"{_time_tag()}\n[подія — це НЕ повідомлення від хазяїна, а те, що ти помітила сама]\n"
        f"{description}\n"
        f"Якщо тобі справді є що сказати — напиши хазяїну першою. Якщо ні — відповідай рівно {SKIP}."
    )
    if not text or text.strip().strip(".").upper() == SKIP:
        return None
    return text


def new_session():
    update_state(session_id=None)
