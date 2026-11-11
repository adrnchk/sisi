"""Спостерігач: помічає події на ПК і дає Сісі привід написати першою.

Прості правила тут, у коді (безкоштовно). Claude викликається лише тоді, коли привід є,
і Сісі сама вирішує, чи казати щось (може відповісти SKIP).
"""
import ctypes
import random
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path

import psutil

from . import activity, brain, settings
from .store import get_state, log_action, pop_due_reminders, update_state

# ---- налаштування ----
TICK_SEC = 15
GAMES = {"dota2.exe": "Dota 2", "hearthstone.exe": "Hearthstone"}
MIN_GAME_MIN = 5            # коротші сесії не коментуємо
AWAY_MIN = 20               # стільки без миші/клавіатури = «пішов»
LONG_SESSION_H = 3          # перше нагадування про довгу сесію
LONG_SESSION_REPEAT_H = 2
NIGHT_HOURS = range(1, 6)   # 01:00–05:59
MORNING_FROM_HOUR = 5
MIN_GAP_MIN = 10            # мінімум між проактивними репліками
MAX_PER_HOUR = 4
SETTLE_MIN = 4              # нове заняття вважається «засів», якщо триває стільки хвилин
SETTLE_CHANCE = 0.5         # не реагувати на кожну зміну — так природніше
SETTLE_CATEGORIES = {"youtube", "anime", "twitch", "work", "app"}
RANDOM_MIN, RANDOM_MAX = 35, 90   # «просто так» зазирнути — раз на стільки хвилин
RANDOM_QUIET_MIN = 25       # якщо нещодавно вже писала — не зазирати
DOWNLOADS = Path.home() / "Downloads"
PARTIAL_EXT = {".crdownload", ".part", ".tmp", ".download", ".opdownload"}


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    info = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000


def running_games() -> set:
    names = set()
    for p in psutil.process_iter(["name"]):
        n = (p.info.get("name") or "").lower()
        if n in GAMES:
            names.add(GAMES[n])
    return names


def _downloads_snapshot() -> set:
    try:
        return {p.name for p in DOWNLOADS.iterdir()
                if p.is_file() and p.suffix.lower() not in PARTIAL_EXT}
    except OSError:
        return set()


class Watcher:
    def __init__(self, deliver):
        """deliver(text, kind) — показати репліку Сісі (чат + сповіщення)."""
        self.deliver = deliver
        self.game_started = {}       # гра -> час початку
        self.game_missing = {}       # гра -> скільки тіків її нема (захист від мерехтіння)
        self.away_since = None
        self.session_start = datetime.now()
        self.next_long_session = self.session_start + timedelta(hours=LONG_SESSION_H)
        self.held = []               # події, відкладені під час гри / відсутності
        self.held_reminders = []
        self.sent_times = []
        self.downloads_seen = _downloads_snapshot()
        self.downloads_pending = set()
        self.timeline = deque(maxlen=int(3 * 3600 / TICK_SEC))  # (час, категорія, опис) за 3 год
        self.current_key = None      # поточне заняття (категорія або конкретне відео)
        self.current_since = datetime.now()
        self.announced_key = None    # на що вже реагувала
        self.next_random = datetime.now() + timedelta(minutes=random.randint(RANDOM_MIN, RANDOM_MAX))

    # ---------- службове ----------

    @property
    def in_game(self):
        """Ігровий режим: запущена гра або ввімкнено вручну в треї."""
        return bool(self.game_started) or settings.get("game_mode")

    def _rate_ok(self, now):
        self.sent_times = [t for t in self.sent_times if now - t < timedelta(hours=1)]
        if len(self.sent_times) >= MAX_PER_HOUR:
            return False
        return not self.sent_times or now - self.sent_times[-1] >= timedelta(minutes=MIN_GAP_MIN)

    def _fire(self, description, kind, force=False):
        now = datetime.now()
        if self.in_game or self.away_since:
            self.held.append(description)
            return
        if not force and not self._rate_ok(now):
            log_action("event_dropped", f"{kind}: {description}")
            return
        log_action("event", f"{kind}: {description[:200]}")
        try:
            text = brain.event(f"{description}\n\nКонтекст:\n{self.context()}")
        except Exception as e:  # noqa: BLE001
            log_action("event_error", str(e)[:300])
            return
        if text:
            self.sent_times.append(now)
            self.deliver(text, kind)

    def _flush_held(self, lead):
        events = [lead] + self.held if lead else list(self.held)
        self.held.clear()
        for r in self.held_reminders:
            self.deliver(r["message"], "reminder")
        self.held_reminders.clear()
        if events:
            desc = events[0] if len(events) == 1 else (
                events[0] + "\nПоки хазяїн був зайнятий, ти також помітила:\n- " + "\n- ".join(events[1:]))
            self._fire(desc, "flush", force=True)

    def context(self) -> str:
        """Що хазяїн робить зараз і робив останню годину — щоб Сісі реагувала по ситуації."""
        lines = []
        if self.timeline:
            _, _, label = self.timeline[-1]
            mins = int((datetime.now() - self.current_since).total_seconds() // 60)
            lines.append(f"Зараз: {label} (~{mins} хв)")
            hour_ago = datetime.now() - timedelta(hours=1)
            cnt = Counter(cat for t, cat, _ in self.timeline if t >= hour_ago)
            if cnt:
                per = ", ".join(f"{c} ~{n * TICK_SEC // 60} хв" for c, n in cnt.most_common(5))
                lines.append(f"Остання година за категоріями: {per}")
            recent = []
            for _, cat, label in reversed(self.timeline):
                if label not in recent and cat not in ("idle", "private"):
                    recent.append(label)
                if len(recent) >= 6:
                    break
            if recent:
                lines.append("Нещодавні заняття: " + "; ".join(recent))
        try:
            hist = activity.opera_history(minutes=45, limit=10)
            lines.append("Історія Opera за 45 хв:\n" + activity.format_history(hist))
        except Exception as e:  # noqa: BLE001
            lines.append(f"(історія Opera недоступна: {e})")
        if self.game_started:
            lines.append("Зараз у грі: " + ", ".join(self.game_started))
        return "\n".join(lines)

    # ---------- перевірки ----------

    def _check_activity(self, now):
        proc, title = activity.foreground()
        cat, label = activity.categorize(proc, title)
        self.timeline.append((now, cat, label))
        key = label if cat in ("youtube", "anime", "twitch") else cat  # нове відео = нове заняття
        if key != self.current_key:
            self.current_key, self.current_since = key, now
            return
        if self.in_game or self.away_since or key == self.announced_key:
            return
        if cat in SETTLE_CATEGORIES and now - self.current_since >= timedelta(minutes=SETTLE_MIN):
            self.announced_key = key
            if random.random() < SETTLE_CHANCE:
                self._fire(f"Ти помітила, що хазяїн уже кілька хвилин як {label}.", "settled")

    def _check_random(self, now):
        if now < self.next_random:
            return
        self.next_random = now + timedelta(minutes=random.randint(RANDOM_MIN, RANDOM_MAX))
        if self.in_game or self.away_since or idle_seconds() > 300:
            return
        if self.sent_times and now - self.sent_times[-1] < timedelta(minutes=RANDOM_QUIET_MIN):
            return
        self._fire("Тобі просто захотілось глянути, чим хазяїн зайнятий, і, може, щось сказати "
                   "або спитати по темі того, що він робить. Якщо з контексту незрозуміло — можеш "
                   "глянути на екран (look_at_screen). Не пиши банальщини — краще SKIP.", "random")

    def _check_reminders(self):
        for r in pop_due_reminders():
            if self.in_game:
                self.held_reminders.append(r)
            else:
                self.deliver(r["message"], "reminder")

    def _check_games(self, now):
        current = running_games()
        for g in current - set(self.game_started):
            self.game_started[g] = now
            self.game_missing[g] = 0
            log_action("game_start", g)
        for g in list(self.game_started):
            if g in current:
                self.game_missing[g] = 0
                continue
            self.game_missing[g] += 1
            if self.game_missing[g] < 2:
                continue
            minutes = int((now - self.game_started.pop(g)).total_seconds() // 60)
            self.game_missing.pop(g, None)
            log_action("game_end", f"{g} {minutes} хв")
            if not self.in_game:
                lead = (f"Хазяїн щойно закрив {g} після {minutes} хв гри."
                        if minutes >= MIN_GAME_MIN else None)
                self._flush_held(lead)

    def _check_presence(self, now):
        idle = idle_seconds()
        st = get_state()
        if self.away_since is None and idle >= AWAY_MIN * 60 and not self.in_game:
            self.away_since = now - timedelta(seconds=idle)
            return
        if self.away_since is not None and idle < 60:
            away_min = int((now - self.away_since).total_seconds() // 60)
            self.away_since = None
            self.session_start = now
            self.next_long_session = now + timedelta(hours=LONG_SESSION_H)
            today = now.date().isoformat()
            if st.get("last_active_date") != today and now.hour >= MORNING_FROM_HOUR:
                update_state(last_active_date=today)
                lead = ("Хазяїн уперше за сьогодні сів за ПК. Привітайся. "
                        "Глянь у пам'ять: чи є в нього плани або щось важливе на сьогодні.")
            else:
                lead = f"Хазяїн повернувся до ПК після {away_min} хв відсутності."
            self._flush_held(lead)
            return
        if self.away_since is None and idle < 300:
            today = now.date().isoformat()
            if st.get("last_active_date") != today and now.hour >= MORNING_FROM_HOUR:
                update_state(last_active_date=today)
                self._fire("Хазяїн уперше за сьогодні за ПК. Привітайся. "
                           "Глянь у пам'ять: чи є в нього плани або щось важливе на сьогодні.", "morning")
            elif now.hour in NIGHT_HOURS and st.get("last_night_date") != today:
                update_state(last_night_date=today)
                self._fire(f"Вже {now:%H:%M} ночі, а хазяїн досі за ПК.", "night")
            elif now >= self.next_long_session:
                hours = (now - self.session_start).total_seconds() / 3600
                self.next_long_session = now + timedelta(hours=LONG_SESSION_REPEAT_H)
                self._fire(f"Хазяїн сидить за ПК вже ~{hours:.0f} год без перерви.", "long_session")

    def _check_downloads(self):
        snap = _downloads_snapshot()
        new = snap - self.downloads_seen
        ready = self.downloads_pending & snap   # файл лежить хоча б два тіки — завантаження завершене
        self.downloads_pending = new - ready
        if ready:
            self.downloads_seen |= ready
            names = sorted(ready)[:10]
            self._fire("У Завантаженнях з'явились нові файли: " + ", ".join(names)
                       + ". (Ти бачиш лише назви, вміст не відкривай.)", "downloads")

    # ---------- цикл ----------

    def tick(self):
        if settings.get("paused"):
            return
        if (not settings.get("game_mode") and not self.game_started and self.away_since is None
                and (self.held or self.held_reminders)):
            self._flush_held(None)  # ігровий режим вимкнули вручну — віддати відкладене
        now = datetime.now()
        self._check_reminders()
        self._check_games(now)
        self._check_presence(now)
        self._check_activity(now)
        self._check_random(now)
        self._check_downloads()

    def run_forever(self):
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log_action("watcher_error", str(e)[:300])
            time.sleep(TICK_SEC)

    def start(self):
        threading.Thread(target=self.run_forever, daemon=True, name="sisi-watcher").start()
