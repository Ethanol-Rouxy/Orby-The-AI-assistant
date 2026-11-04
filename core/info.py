"""Infos externes : actualités (flux RSS), météo (Open-Meteo, sans clé) et état du système.

Aucune dépendance à l'interface. Les fonctions réseau sont lentes : appelle-les dans un
thread (ui.async_util.run_async).
"""
import ctypes
import html
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import config
from core import settings

try:
    import psutil
    psutil.cpu_percent(interval=None)   # le premier appel renvoie toujours 0 : on l'« amorce »
    PSUTIL_ERROR = None
except Exception as _e:                  # ImportError, mais aussi tout autre souci au chargement
    psutil = None
    PSUTIL_ERROR = f"{type(_e).__name__}: {_e}"
    print(f"[système] psutil inutilisable ({PSUTIL_ERROR}).\n"
          f"          Python utilisé par Orby : {sys.executable}\n"
          f"          Installe-le DANS CE PYTHON : \"{sys.executable}\" -m pip install psutil")

PSUTIL_HINT = f'"{sys.executable}" -m pip install psutil'

_UA = {"User-Agent": "Mozilla/5.0 (Orby desktop assistant)"}
_cache = {}


def _get(url: str, timeout: float = 8) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ================================================================== ACTUALITÉS
def _clean(text) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _when(raw: str):
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None


def _parse_feed(feed: dict, per_feed: int) -> list:
    """Lit un flux RSS ou Atom. Un flux en panne est simplement ignoré."""
    try:
        root = ET.fromstring(_get(feed["url"]))
    except Exception:
        return []
    out = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
            continue
        title = link = date = ""
        for ch in el:
            tag = ch.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = _clean(ch.text)
            elif tag == "link":
                link = (ch.text or "").strip() or ch.get("href", "")
            elif tag in ("pubDate", "published", "updated", "date"):
                date = ch.text or ""
        if title and link.startswith("http"):
            out.append({"title": title, "link": link, "source": feed["name"], "date": _when(date)})
        if len(out) >= per_feed:
            break
    return out


def fetch_news(force: bool = False) -> list:
    """Liste de {title, link, source, date}, sources mélangées. Mise en cache 10 min."""
    hit = _cache.get("news")
    if hit and not force and time.time() - hit[0] < 600:
        return hit[1]
    feeds = config.NEWS_FEEDS
    total = getattr(config, "NEWS_COUNT", 15)
    if not feeds:
        return []
    per_feed = -(-total // len(feeds)) + 2
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        lists = list(pool.map(lambda f: _parse_feed(f, per_feed), feeds))
    items, seen = [], set()
    for rank in range(per_feed):                 # une info de chaque source à tour de rôle
        for lst in lists:
            if rank < len(lst):
                it = lst[rank]
                key = it["title"].lower()[:60]
                if key not in seen:
                    seen.add(key)
                    items.append(it)
    items = items[:total]
    if items:
        _cache["news"] = (time.time(), items)
    return items


# ======================================================================= MÉTÉO
def describe_weather(code: int, is_day: bool = True):
    """(texte, emoji) pour un code météo WMO."""
    if code == 0:
        return "Ciel dégagé", "☀️" if is_day else "🌙"
    if code == 1:
        return "Plutôt dégagé", "🌤️"
    if code == 2:
        return "Éclaircies", "⛅"
    if code == 3:
        return "Couvert", "☁️"
    if code in (45, 48):
        return "Brouillard", "🌫️"
    if 51 <= code <= 57:
        return "Bruine", "🌦️"
    if 61 <= code <= 67:
        return "Pluie", "🌧️"
    if 71 <= code <= 77 or code in (85, 86):
        return "Neige", "🌨️"
    if 80 <= code <= 82:
        return "Averses", "🌦️"
    if code >= 95:
        return "Orage", "⛈️"
    return "Météo inconnue", "❔"


def _geocode(city: str) -> dict:
    key = f"geo:{city.lower()}"
    saved = settings.load().get(key)
    if saved:
        return saved
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "fr"})
    results = json.loads(_get(url)).get("results")
    if not results:
        raise ValueError(f"Ville introuvable : {city}")
    r = results[0]
    geo = {"lat": r["latitude"], "lon": r["longitude"], "name": r["name"]}
    settings.save(**{key: geo})
    return geo


def fetch_weather(city: str | None = None) -> dict:
    city = (city or getattr(config, "WEATHER_CITY", "Paris")).strip()
    key = f"weather:{city.lower()}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    geo = _geocode(city)
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": geo["lat"], "longitude": geo["lon"], "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    data = json.loads(_get(url))
    cur, day = data["current"], data["daily"]
    desc, icon = describe_weather(int(cur["weather_code"]), bool(cur.get("is_day", 1)))
    result = {
        "place": geo["name"], "desc": desc, "icon": icon,
        "temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
        "wind": round(cur["wind_speed_10m"]),
        "tmin": round(day["temperature_2m_min"][0]), "tmax": round(day["temperature_2m_max"][0]),
        "rain": day["precipitation_probability_max"][0],
    }
    _cache[key] = (time.time(), result)
    return result


def weather_text(city: str | None = None) -> str:
    w = fetch_weather(city)
    rain = f", pluie {w['rain']} %" if w["rain"] is not None else ""
    return (f"{w['place']} : {w['desc']}, {w['temp']}°C (ressenti {w['feels']}°C), "
            f"vent {w['wind']} km/h. Aujourd'hui : min {w['tmin']}°C / max {w['tmax']}°C{rain}.")


# ===================================================================== SYSTÈME
# --- Mode de secours SANS psutil (Windows / Linux) : un peu moins complet, mais ça marche partout.
class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
        (n, ctypes.c_ulonglong) for n in ("total", "avail", "tpf", "apf", "tv", "av", "aev")]


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("pct", ctypes.c_ubyte),
                ("sys", ctypes.c_ubyte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]


_cpu_prev = None


def _cpu_windows():
    global _cpu_prev
    idle, kern, user = (ctypes.c_ulonglong() for _ in range(3))
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None
    cur, prev, _cpu_prev = (idle.value, kern.value + user.value), _cpu_prev, (idle.value, kern.value + user.value)
    if prev is None or cur[1] <= prev[1]:
        return None
    return max(0.0, min(100.0, 100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1]))))


def _cpu_linux():
    global _cpu_prev
    vals = [int(x) for x in open("/proc/stat").readline().split()[1:8]]
    cur, prev, _cpu_prev = (vals[3] + vals[4], sum(vals)), _cpu_prev, (vals[3] + vals[4], sum(vals))
    if prev is None or cur[1] <= prev[1]:
        return None
    return max(0.0, min(100.0, 100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1]))))


def _basic_stats() -> dict:
    cpu = ram = used = total = battery = uptime = None
    try:
        if sys.platform.startswith("win"):
            k32 = ctypes.windll.kernel32
            cpu = _cpu_windows()
            m = _MemStatus()
            m.dwLength = ctypes.sizeof(m)
            if k32.GlobalMemoryStatusEx(ctypes.byref(m)):
                ram, total, used = float(m.dwMemoryLoad), m.total / 1e9, (m.total - m.avail) / 1e9
            p = _PowerStatus()
            if k32.GetSystemPowerStatus(ctypes.byref(p)) and p.flag != 128 and p.pct <= 100:
                battery = {"percent": int(p.pct), "plugged": p.ac == 1}
            k32.GetTickCount64.restype = ctypes.c_ulonglong
            uptime = k32.GetTickCount64() / 1000
        elif sys.platform.startswith("linux"):
            cpu = _cpu_linux()
            mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
            total, avail = mem["MemTotal"] * 1024, mem["MemAvailable"] * 1024
            ram, total, used = 100.0 * (1 - avail / total), total / 1e9, (total - avail) / 1e9
            uptime = float(open("/proc/uptime").read().split()[0])
            for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
                status = (bat / "status").read_text().strip()
                battery = {"percent": int((bat / "capacity").read_text()), "plugged": status != "Discharging"}
                break
    except Exception:
        pass
    try:
        du = shutil.disk_usage(Path.home().anchor or "/")
        disk = 100.0 * du.used / du.total
    except Exception:
        disk = None
    return {"cpu": cpu, "ram": ram, "ram_used": used, "ram_total": total, "disk": disk,
            "battery": battery, "uptime": uptime, "source": "basique"}


def system_stats():
    """Dict (cpu, ram, ram_used, ram_total, disk, battery, uptime, source).
    Une valeur peut être None si elle n'est pas détectable sur cette machine."""
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            try:
                disk = psutil.disk_usage(Path.home().anchor or "/").percent
            except Exception:
                disk = None
            battery = None
            try:
                b = psutil.sensors_battery()
                if b:
                    battery = {"percent": round(b.percent), "plugged": bool(b.power_plugged)}
            except Exception:
                pass
            return {"cpu": psutil.cpu_percent(interval=None), "ram": vm.percent,
                    "ram_used": vm.used / 1e9, "ram_total": vm.total / 1e9, "disk": disk,
                    "battery": battery, "uptime": time.time() - psutil.boot_time(), "source": "psutil"}
        except Exception:
            pass
    return _basic_stats()


def system_text() -> str:
    s = system_stats()
    parts = []
    if s["cpu"] is not None:
        parts.append(f"CPU {s['cpu']:.0f} %")
    if s["ram"] is not None:
        parts.append(f"RAM {s['ram']:.0f} % ({s['ram_used']:.1f}/{s['ram_total']:.1f} Go)")
    if s["disk"] is not None:
        parts.append(f"disque {s['disk']:.0f} %")
    if s["battery"]:
        parts.append(f"batterie {s['battery']['percent']} %" + (" (sur secteur)" if s["battery"]["plugged"] else ""))
    if s["uptime"] is not None:
        parts.append(f"allumé depuis {int(s['uptime'] // 3600)} h")
    return ", ".join(parts) or "Infos système indisponibles sur cette machine."


if sys.platform.startswith("win"):        # amorce le calcul du CPU du mode de secours
    try:
        _cpu_windows()
    except Exception:
        pass
