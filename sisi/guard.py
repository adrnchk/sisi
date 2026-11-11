"""PreToolUse-хук для Claude Code: жорсткі заборони для файлових інструментів і PowerShell Сісі.

Claude Code передає сюди JSON виклику інструмента (stdin). Код виходу 2 = заборонити,
текст у stderr бачить модель. Це «другий замок» поверх правил персони:
  - не чіпати системні папки, AppData і код самої Сісі;
  - не видаляти остаточно (лише в Кошик) і не чистити Кошик;
  - не запускати файли із Завантажень і не виконувати скачаний код;
  - не лізти в реєстр, диски, завантажувач, політики.
Перевірка команд — за шаблонами, тобто «найкраща спроба», а не пісочниця.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_DIR = ROOT / "data" / "home"

_env = os.environ
PROTECTED = [
    Path(_env.get("SystemRoot", r"C:\Windows")),
    Path(_env.get("ProgramFiles", r"C:\Program Files")),
    Path(_env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    Path(_env.get("ProgramData", r"C:\ProgramData")),
    Path(_env.get("USERPROFILE", r"C:\Users\Default")) / "AppData",
    Path(r"C:\$Recycle.Bin"), Path(r"C:\Recovery"), Path(r"C:\System Volume Information"),
    Path(r"C:\Boot"), Path(r"C:\EFI"),
]
ALLOWED_INSIDE = [HOME_DIR]
# Власну папку Сісі можна читати, писати — лише в data/ (іконки, файли для себе тощо).
# Код, персона, пам'ять і git змінюються тільки через її інструменти / хазяїном.
PROJECT_LOCKED = [ROOT / n for n in (
    "sisi", "persona.md", "decisions.md", "README.md", "requirements.txt",
    "run_sisi.bat", ".git", ".venv", "memory", ".gitignore")] + [ROOT / "data" / f for f in (
    "settings.json", "state.json", "guard_settings.json", "mcp.json", "actions.log", "reminders.json")]
PROJECT_LOCKED_RE = re.compile(
    r"documents\\sisi\\(sisi\\|persona\.md|decisions\.md|readme\.md|requirements\.txt|run_sisi\.bat"
    r"|\.git|\.venv|memory\\|\.gitignore|data\\(settings|state|guard_settings|mcp|reminders)\.json|data\\actions\.log)")
WRITE_TOKENS = re.compile(
    r"\b(set-content|add-content|out-file|clear-content|move-item|rename-item|copy-item|new-item|mi|mv|ren|"
    r"copy|move|sc|ac)\b|-outfile|writealltext|writeallbytes|appendalltext|>>?|deletefile|deletedirectory")

# слова/фрагменти шляхів, які в командах означають системне
PROTECTED_WORDS = [
    r"\\windows\\", r"c:\\windows", r"\$env:windir", r"%windir%", r"\$env:systemroot", r"%systemroot%",
    r"program files", r"\$env:programfiles", r"%programfiles", r"programdata", r"\$env:programdata",
    r"\\appdata\\", r"\$env:appdata", r"\$env:localappdata", r"%appdata%", r"%localappdata%",
    r"\$recycle\.bin", r"system volume information", r"system32",
]
FORBIDDEN_CMDS = {
    r"\bclear-recyclebin\b": "очищати Кошик заборонено",
    r"\b(remove-item|ri|del|erase|rd|rmdir)\b": "остаточне видалення заборонене — тільки в Кошик (Recycle)",
    r"(^|[\s;|&(])rm\s": "остаточне видалення заборонене — тільки в Кошик (Recycle)",
    r"\b(format|format-volume|diskpart|clear-disk|initialize-disk|bcdedit|bcdboot)\b": "диски й завантажувач — заборонено",
    r"\b(reg(\.exe)?\s+(add|delete|import|load|restore)|set-itemproperty\s+.*hk(lm|cu)|new-itemproperty|remove-itemproperty)\b": "реєстр — заборонено",
    r"\bhk(lm|cu|cr|u)\:": "реєстр — заборонено",
    r"\b(set-executionpolicy|set-mppreference|add-mppreference|netsh|takeown|icacls|cacls|cipher)\b": "системні налаштування й безпека — заборонено",
    r"\b(invoke-expression|iex)\b": "виконання скачаного/згенерованого коду заборонене",
    r"\b(stop-computer|restart-computer|shutdown)\b": "вимкнення/перезавантаження — лише хазяїн сам",
    r"\b(new-localuser|net\s+user|add-localgroupmember)\b": "облікові записи — заборонено",
}
DOWNLOAD_EXEC = re.compile(
    r"downloads.*\.(exe|msi|bat|cmd|ps1|vbs|js|jar|scr|com|lnk)\b|"
    r"(start-process|saps|&|\.\s|invoke-item|ii)\s+[^;|]*downloads", re.I)


def _blocked_path(p: str):
    if not p:
        return None
    try:
        path = Path(os.path.expandvars(p)).expanduser()
        path = (HOME_DIR / path if not path.is_absolute() else path).resolve()
    except (OSError, ValueError):
        return None
    for ok in ALLOWED_INSIDE:
        if path == ok or ok in path.parents:
            return None
    for root in PROTECTED:
        try:
            root = root.resolve()
        except OSError:
            continue
        if path == root or root in path.parents:
            return f"шлях {path} у захищеній папці ({root}) — туди не можна"
    return None


def check(tool: str, inp: dict):
    """Повертає причину заборони або None."""
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Glob", "Grep"):
        for key in ("file_path", "path", "notebook_path"):
            reason = _blocked_path(inp.get(key, ""))
            if reason:
                return reason
        if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            reason = _locked_in_project(inp.get("file_path") or inp.get("notebook_path") or "")
            if reason:
                return reason
        pattern = inp.get("pattern", "") if tool == "Glob" else ""
        if pattern and os.path.isabs(pattern):
            return _blocked_path(pattern.split("*")[0])
        return None
    if tool in ("PowerShell", "Bash"):
        cmd = inp.get("command", "")
        low = cmd.lower().replace("/", "\\")
        for pat in PROTECTED_WORDS:
            if re.search(pat, low):
                return "команда зачіпає системні/захищені папки — заборонено"
        for pat, why in FORBIDDEN_CMDS.items():
            if re.search(pat, low, re.I):
                return why
        if DOWNLOAD_EXEC.search(cmd):
            return "запуск файлів із Завантажень заборонений"
        if PROJECT_LOCKED_RE.search(low) and WRITE_TOKENS.search(low):
            return "свій код, персону, пам'ять і налаштування змінювати не можна (писати можна лише в data\\)"
    return None


def _locked_in_project(p: str):
    if not p:
        return None
    try:
        path = Path(os.path.expandvars(p)).expanduser()
        path = (HOME_DIR / path if not path.is_absolute() else path).resolve()
    except (OSError, ValueError):
        return None
    for locked in PROJECT_LOCKED:
        locked = locked.resolve()
        if path == locked or locked in path.parents:
            return (f"{path.name}: свій код, персону, пам'ять і налаштування змінювати не можна "
                    "(писати можна лише в data\\)")
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    reason = check(data.get("tool_name", ""), data.get("tool_input") or {})
    if reason:
        try:
            sys.path.insert(0, str(ROOT))
            from sisi.store import log_action
            log_action("guard_blocked", f"{data.get('tool_name')}: {reason}")
        except Exception:  # noqa: BLE001
            pass
        print(f"Заборонено запобіжником Сісі: {reason}. Видаляти можна лише в Кошик: "
              "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(шлях,'OnlyErrorDialogs','SendToRecycleBin') "
              "(для папок — DeleteDirectory).", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
