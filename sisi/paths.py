"""Спільні шляхи проєкту."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERSONA = ROOT / "persona.md"
MEMORY = ROOT / "memory" / "user.md"
DATA = ROOT / "data"
WALLPAPERS = DATA / "wallpapers"
HOME = DATA / "home"  # робоча папка для claude -p (порожня, без CLAUDE.md проєкту)
STATE = DATA / "state.json"
REMINDERS = DATA / "reminders.json"
ACTIONS_LOG = DATA / "actions.log"
MCP_CONFIG = DATA / "mcp.json"

for d in (DATA, WALLPAPERS, HOME, MEMORY.parent):
    d.mkdir(parents=True, exist_ok=True)
