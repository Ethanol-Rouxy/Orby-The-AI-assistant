"""Réglages mémorisés entre deux lancements (zoom, position d'Orby).

Stockés dans ~/.orby/settings.json : supprime ce fichier pour tout réinitialiser.
"""
import json
from pathlib import Path

PATH = Path.home() / ".orby" / "settings.json"


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(**changes):
    data = load()
    data.update(changes)
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
