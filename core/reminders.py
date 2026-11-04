"""Rappels : stockés dans ~/.orby/reminders.json (partagés entre l'IA, le mini-écran et l'app).

Formats acceptés pour l'heure (au début de la phrase) :
    18:30 appeler Paul      18h30 appeler Paul      18h sortir le linge
    dans 10 min boire       10 min boire            dans 2 h pause
    2026-11-02 09:00 rdv    (la date complète est aussi acceptée)
"""
import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

PATH = Path.home() / ".orby" / "reminders.json"
_lock = threading.Lock()

_DURATION = re.compile(r"^(dans\s+)?(\d+)\s*(min(?:ute)?s?|h(?:eures?)?)\s+(.+)$", re.I | re.S)
_CLOCK = re.compile(r"^(\d{1,2})[:hH](\d{2})?\s+(.+)$", re.S)
_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})\s+(.+)$", re.S)


def parse_reminder(line: str, now: datetime | None = None):
    """'18:30 appeler Paul' -> (datetime, 'appeler Paul'). Lève ValueError si incompréhensible."""
    now = now or datetime.now()
    line = line.strip()
    if m := _ISO.match(line):
        day, hh, mm, text = m.groups()
        return datetime.fromisoformat(f"{day} {int(hh):02d}:{mm}"), text.strip()
    if m := _DURATION.match(line):
        dans, n, unit, text = m.groups()
        if dans or unit.lower().startswith("min"):    # « 18h … » seul = heure, pas durée
            delta = timedelta(minutes=int(n)) if unit.lower().startswith("min") else timedelta(hours=int(n))
            return now + delta, text.strip()
    if m := _CLOCK.match(line):
        hh, mm, text = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if hh > 23 or mm > 59:
            raise ValueError("Heure invalide.")
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at <= now:
            at += timedelta(days=1)                    # déjà passée : demain
        return at, text.strip()
    raise ValueError("Format : « 18:30 texte » ou « dans 10 min texte »")


def parse_when(when: str, now: datetime | None = None) -> datetime:
    """Comme parse_reminder mais sans texte (utilisé par l'outil de l'IA)."""
    return parse_reminder(when.strip() + " x", now)[0]


def _read() -> list:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(items: list):
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load() -> list:
    """[{'id', 'text', 'at'}] triés par heure."""
    with _lock:
        return sorted(_read(), key=lambda r: r["at"])


def add(text: str, at: datetime) -> dict:
    with _lock:
        items = _read()
        rid = max((r["id"] for r in items), default=0) + 1
        item = {"id": rid, "text": text, "at": at.isoformat(timespec="minutes")}
        items.append(item)
        _write(items)
        return item


def remove(rid: int):
    with _lock:
        _write([r for r in _read() if r["id"] != rid])


def pop_due(now: datetime | None = None) -> list:
    """Retire et renvoie les rappels dont l'heure est passée."""
    now = now or datetime.now()
    with _lock:
        items = _read()
        due = [r for r in items if datetime.fromisoformat(r["at"]) <= now]
        if due:
            _write([r for r in items if r not in due])
        return due


def label(r: dict, now: datetime | None = None) -> str:
    """'18:30' si c'est aujourd'hui, sinon '02/11 18:30'."""
    now = now or datetime.now()
    at = datetime.fromisoformat(r["at"])
    return at.strftime("%H:%M") if at.date() == now.date() else at.strftime("%d/%m %H:%M")
