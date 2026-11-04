"""Bureaux virtuels Windows : savoir sur quel bureau on se trouve.

On lit l'identifiant du bureau courant dans le registre (là où l'Explorateur le range) :
aucune dépendance en plus. Hors Windows, ou si la clé est introuvable, rien ne se passe.
"""
import sys
import uuid

IS_WINDOWS = sys.platform.startswith("win")
_BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer"


def _read(path: str, name: str):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return bytes(winreg.QueryValueEx(key, name)[0])
    except (OSError, TypeError, ValueError):
        return None


def _session_id() -> int:
    import ctypes
    sid = ctypes.c_ulong(1)
    k32 = ctypes.windll.kernel32
    k32.ProcessIdToSessionId(k32.GetCurrentProcessId(), ctypes.byref(sid))
    return sid.value


def current_id():
    """GUID (texte) du bureau virtuel affiché, ou None si inconnu."""
    if not IS_WINDOWS:
        return None
    paths = (rf"{_BASE}\SessionInfo\{_session_id()}\VirtualDesktops", rf"{_BASE}\VirtualDesktops")
    for path in paths:
        raw = _read(path, "CurrentVirtualDesktop")
        if raw and len(raw) == 16:
            return str(uuid.UUID(bytes_le=raw))
    return None


def all_ids() -> list:
    """Les bureaux existants, dans l'ordre."""
    if not IS_WINDOWS:
        return []
    raw = _read(rf"{_BASE}\VirtualDesktops", "VirtualDesktopIDs") or b""
    return [str(uuid.UUID(bytes_le=raw[i:i + 16])) for i in range(0, len(raw) - 15, 16)]


class DesktopGuard:
    """Retient le bureau « maison » d'Orby et dit si on est dessus."""

    def __init__(self):
        self.available = IS_WINDOWS
        self.home = current_id() if IS_WINDOWS else None
        if IS_WINDOWS:
            if self.home:
                print(f"[bureaux] suivi actif, bureau de départ : {self.home}")
            else:
                print("[bureaux] bureau de départ inconnu (un seul bureau pour l'instant ?) : "
                      "il sera déduit dès que tu en crées un autre.")

    def poll(self) -> str:
        """'home' (on est sur le bureau d'Orby), 'away' (autre bureau) ou 'home' si on ne sait pas."""
        if not self.available:
            return "home"
        cur = current_id()
        if cur is None:
            return "home"
        if self.home is None:               # lancé avant la création du 2e bureau : le 1er est le « maison »
            ids = all_ids()
            self.home = ids[0] if ids else cur
        return "home" if cur == self.home else "away"

    def bring_here(self):
        """Orby adopte le bureau actuel comme bureau « maison »."""
        cur = current_id()
        if cur:
            self.home = cur
