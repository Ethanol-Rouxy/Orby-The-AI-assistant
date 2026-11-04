"""Les 'mains' de l'assistant : actions que l'IA peut déclencher.

Toutes les actions sur les fichiers sont limitées à config.ALLOWED_DIRS.
"""
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

import config
from core import info, reminders

MAX_CHARS = 12000
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".html",
            ".css", ".xml", ".yaml", ".yml", ".ini", ".toml"}
# On refuse d'ouvrir/exécuter ces types de fichiers (sécurité).
BLOCKED_EXT = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".sh", ".app", ".scr",
               ".vbs", ".jar", ".com", ".lnk", ".dll", ".reg"}


def _safe(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    for d in config.ALLOWED_DIRS:
        d = d.expanduser().resolve()
        if p == d or p.is_relative_to(d):
            return p
    raise PermissionError(f"Chemin hors des dossiers autorisés : {p}")


def is_allowed(path: str) -> bool:
    try:
        _safe(path)
        return True
    except Exception:
        return False


def allowed_roots() -> list:
    return [d.expanduser() for d in config.ALLOWED_DIRS if d.expanduser().exists()]


def list_entries(path: str) -> list:
    """[(nom, est_dossier, chemin)] triés : dossiers d'abord."""
    p = _safe(path)
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    return [(i.name, i.is_dir(), str(i)) for i in items if not i.name.startswith(".")][:300]


def find_files(query: str, folder: str | None = None, limit: int = 40) -> list:
    """[(nom, est_dossier, chemin)] dont le nom contient `query`."""
    roots = [_safe(folder)] if folder else allowed_roots()
    q = query.lower()
    hits = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in filenames:
                if q in f.lower():
                    hits.append((f, False, str(Path(dirpath) / f)))
                    if len(hits) >= limit:
                        return hits
    return hits


def list_dir(path: str) -> str:
    p = _safe(path)
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = [("[D] " if i.is_dir() else "[F] ") + i.name for i in items[:200]]
    return "\n".join(lines) or "(dossier vide)"


def search_files(query: str, folder: str | None = None) -> str:
    roots = ([_safe(folder)] if folder else
             [d.expanduser() for d in config.ALLOWED_DIRS if d.expanduser().exists()])
    q = query.lower()
    hits = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in filenames:
                if q in f.lower():
                    hits.append(str(Path(dirpath) / f))
                    if len(hits) >= 30:
                        return "\n".join(hits)
    return "\n".join(hits) or "Aucun résultat."


def read_file(path: str) -> str:
    p = _safe(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        parts, total = [], 0
        for page in PdfReader(str(p)).pages[:40]:
            t = page.extract_text() or ""
            parts.append(t)
            total += len(t)
            if total > MAX_CHARS:
                break
        text = "\n".join(parts)
    elif ext == ".docx":
        import docx
        text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    elif ext in TEXT_EXT:
        text = p.read_text(encoding="utf-8", errors="replace")
    else:
        return f"Type de fichier non pris en charge : {ext or '(sans extension)'}"
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + "\n[... texte tronqué ...]"
    return text or "(fichier vide ou texte non extractible)"


def open_path(path: str) -> str:
    p = _safe(path)
    if p.suffix.lower() in BLOCKED_EXT:
        return f"Ouverture refusée pour des raisons de sécurité : {p.suffix}"
    if sys.platform.startswith("win"):
        os.startfile(str(p))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])
    return f"Ouvert : {p}"


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "Seules les URL http(s) sont autorisées."
    webbrowser.open(url)
    return f"Ouvert dans le navigateur : {url}"


def launch_app(name: str) -> str:
    cmd = config.APPS.get(name.lower())
    if not cmd:
        return f"Application non autorisée. Disponibles : {', '.join(config.APPS)}"
    subprocess.Popen(cmd)
    return f"Lancé : {name}"


def get_news(limit: int = 8) -> str:
    items = info.fetch_news()[: max(1, int(limit))]
    if not items:
        return "Impossible de récupérer les actualités (connexion ?)."
    return "\n".join(f"- {i['title']} ({i['source']}) {i['link']}" for i in items)


def get_weather(city: str | None = None) -> str:
    return info.weather_text(city)


def system_status() -> str:
    return info.system_text()


def add_reminder(text: str, when: str) -> str:
    at = reminders.parse_when(when)
    reminders.add(text, at)
    return f"Rappel enregistré pour {at:%d/%m %H:%M} : {text}"


def list_reminders() -> str:
    items = reminders.load()
    return "\n".join(f"- {reminders.label(r)} : {r['text']}" for r in items) or "Aucun rappel."


def _fn(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


_S = {"type": "string"}
SCHEMAS = [
    _fn("list_dir", "Liste le contenu d'un dossier.", {"path": _S}, ["path"]),
    _fn("search_files", "Cherche des fichiers par morceau de nom.",
        {"query": _S, "folder": _S}, ["query"]),
    _fn("read_file", "Lit le texte d'un fichier (txt, md, csv, pdf, docx...).",
        {"path": _S}, ["path"]),
    _fn("open_path", "Ouvre un fichier ou dossier avec l'application par défaut.",
        {"path": _S}, ["path"]),
    _fn("open_url", "Ouvre une page web dans le navigateur.", {"url": _S}, ["url"]),
    _fn("launch_app", "Lance une application autorisée.",
        {"name": {"type": "string", "enum": list(config.APPS)}}, ["name"]),
    _fn("get_news", "Donne les actualités importantes du jour (titres + liens).",
        {"limit": {"type": "integer"}}, []),
    _fn("get_weather", "Donne la météo du jour (ville de l'utilisateur par défaut).",
        {"city": _S}, []),
    _fn("system_status", "Donne l'état du PC : CPU, RAM, disque, batterie.", {}, []),
    _fn("add_reminder", "Crée un rappel. `when` : « 18:30 », « 18h30 » ou « dans 10 min ».",
        {"text": _S, "when": _S}, ["text", "when"]),
    _fn("list_reminders", "Liste les rappels en attente.", {}, []),
]

REGISTRY = {f.__name__: f for f in
            (list_dir, search_files, read_file, open_path, open_url, launch_app,
             get_news, get_weather, system_status, add_reminder, list_reminders)}


def run_tool(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if not fn:
        return f"Outil inconnu : {name}"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"Erreur : {e}"
