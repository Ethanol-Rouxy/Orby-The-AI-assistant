"""Chef d'orchestre : relie Orby, la bulle, la console et le cerveau (Agent)."""
import queue
import random
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import config
from core import reminders, settings
from core.agent import Agent
from core.desktops import DesktopGuard
from ui.bubble import Bubble
from ui.companion import Companion
from ui.console import Console
from ui.hud import Hud

NAME = config.ASSISTANT_NAME


class Bridge(QObject):
    """Relie le thread de l'IA à l'interface (les signaux sont thread-safe)."""
    state = Signal(str)
    switched = Signal(str, str, str)   # ancien, nouveau, raison
    answer = Signal(object, str)       # (page qui attendait, réponse)
    toggle = Signal()


class AssistantApp(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.modes = {m["key"]: m for m in config.MODES}
        self.saved = settings.load()
        self.bridge = Bridge()
        self.agent = Agent(on_state=self.bridge.state.emit,
                           on_switch=self.bridge.switched.emit)

        self.companion = Companion(self.saved.get("zoom", config.DEFAULT_ZOOM))
        self.bubble = Bubble()
        self.hud = Hud()
        self.consoles = {}            # une fenêtre par mode, créées à la demande : plusieurs ouvertes en même temps
        self.win_state = self.saved.get("windows") if isinstance(self.saved.get("windows"), dict) else {}
        self._last_key = "chat"
        self._badge = ("", "#6f8aa6")
        self._jobs = queue.Queue()    # les demandes à l'IA passent l'une après l'autre
        threading.Thread(target=self._worker, daemon=True).start()
        self._away = False            # vrai quand on est sur un autre bureau virtuel
        self._parked = []             # fenêtres cachées pendant ce temps
        self._first_start = True
        self._last_pet_line = 0.0
        self._quitting = False
        self._quit_done = False

        first = self.agent.pool.first_name
        if first:
            color = self.agent.pool.color_of(first)
            self._badge = (first, color)
            self.companion.avatar.set_accent(color)

        self._wire()
        self._setup_tray()
        self._setup_hotkey()

        self.hud.restore_state(self.saved.get("hud_sizes"), self.saved.get("hud_compact", False))
        if not self.hud.restore_position(self.saved.get("hud_pos")):
            self.hud.place_default()
        if self.saved.get("hud_visible"):
            self.hud.show()
        self.reminder_timer = QTimer(self)               # vérifie les rappels toutes les 5 s
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start(5000)

        self.guard = None             # bureaux virtuels (Windows) : Orby reste sur son bureau
        if getattr(config, "DESKTOP_MODE", "stay") == "stay":
            guard = DesktopGuard()
            if guard.available:
                self.guard = guard
                self.desktop_timer = QTimer(self)
                self.desktop_timer.timeout.connect(self._check_desktop)
                self.desktop_timer.start(400)

        if not self.companion.restore_position(self.saved.get("pos")):
            self.companion.place_default()
        self.companion.show()
        self.companion.play_start()          # animation de démarrage, puis Orby parle

    # --------------------------------------------------------------- Liens
    def _wire(self):
        c, b, br = self.companion, self.bubble, self.bridge
        c.clicked.connect(self.toggle_bubble)
        c.dragged.connect(self.bubble.hide)
        c.moved_by_user.connect(self.save_position)
        c.zoom_changed.connect(self.on_zoom_changed)
        c.started.connect(self.on_started)
        c.petted.connect(self.on_petted)
        c.console_requested.connect(lambda: self.open_console(self._last_key))
        c.hide_requested.connect(self.hide_all)
        c.hud_requested.connect(self.toggle_hud)
        self.hud.moved_by_user.connect(lambda: settings.save(hud_pos=[self.hud.x(), self.hud.y()]))
        self.hud.closed.connect(lambda: settings.save(hud_visible=False))
        self.hud.layout_changed.connect(
            lambda: settings.save(hud_sizes=self.hud.sizes, hud_compact=self.hud.compact))
        c.quit_requested.connect(self.quit)
        b.mode_chosen.connect(self.open_console)
        b.quit_requested.connect(self.quit)
        br.state.connect(c.avatar.set_state)
        br.switched.connect(self.on_switched)
        br.answer.connect(self.on_answer)
        br.toggle.connect(self.toggle_companion)

    # ------------------------------------------------------------ Consoles
    def get_console(self, key: str) -> Console:
        """La fenêtre du mode `key` (créée au premier appel)."""
        con = self.consoles.get(key)
        if con is None:
            mode = self.modes[key]
            state = self.win_state.get(key)
            size = state[2:4] if isinstance(state, list) and len(state) == 4 else None
            if size is None and key == "chat":
                size = self.saved.get("console_size")      # ancienne taille mémorisée
            con = Console(mode, size)
            con.set_badge(*self._badge)
            con.ask_requested.connect(
                lambda page, text, m=mode: self.on_ask(page, text, m.get("extra", "")))
            con.chat_requested.connect(self.ask_in_chat)
            con.menu_requested.connect(self.show_menu)
            con.geometry_saved.connect(self._save_window)
            self.consoles[key] = con
        return con

    def _save_window(self, key: str, geo: list):
        self.win_state[key] = geo
        settings.save(windows=self.win_state)

    def any_console_visible(self) -> bool:
        return any(c.isVisible() for c in self.consoles.values())

    def ask_in_chat(self, text: str, send_now: bool = True):
        """Ouvre la fenêtre de chat (sans fermer les autres) et y envoie / pré-remplit un message."""
        con = self.get_console("chat")
        self.open_console("chat")
        if send_now:
            con.ask_requested.emit(con.page, text)
        else:
            con.page.input.setText(text)
            con.page.input.setFocus()

    # ------------------------------------------------------------- Paroles
    def say(self, text: str, ms: int = 5000):
        if self.companion.isVisible():
            self.bubble.show_notice(text, self.companion, ms)

    def on_started(self):
        """Fin de l'animation de démarrage : Orby dit quelque chose."""
        if not self.agent.pool.providers:
            if self._first_start and getattr(config, "STARTUP_OFFER", False):   # infos / HUD marchent sans IA
                offers = [o for o in config.STARTUP_OFFERS if o[1] != "briefing"]
                self.bubble.show_offer("Aucune clé API (.env) : l'IA est désactivée, mais je peux "
                                       "quand même te montrer ça.", offers, self.companion, 20000)
            else:
                self.say("Aucune clé API trouvée : remplis le fichier .env puis relance-moi.", 12000)
        elif self._first_start:
            hour = datetime.now().hour
            moment = "Bonjour" if 5 <= hour < 18 else "Bonsoir"
            line = random.choice(config.STARTUP_LINES)
            try:
                line = line.format(moment=moment, name=NAME)
            except (KeyError, IndexError, ValueError):
                pass   # phrase mal formée dans config.py : on la dit telle quelle
            if getattr(config, "STARTUP_OFFER", False):
                self.bubble.show_offer(f"{line}\n\n{config.STARTUP_OFFER_TEXT}", config.STARTUP_OFFERS,
                                       self.companion, getattr(config, "STARTUP_OFFER_MS", 30000))
            else:
                self.say(line, 3500 + 45 * len(line))
        else:
            self.say(random.choice(config.BACK_LINES), 3500)
        self._first_start = False

    def on_petted(self):
        now = time.monotonic()
        if (now - self._last_pet_line < 25 or self.bubble.isVisible()
                or self.any_console_visible()):
            return
        self._last_pet_line = now
        self.say(random.choice(config.PET_LINES), 2800)

    # ------------------------------------------------------------- Actions
    def toggle_bubble(self):
        if self._quitting:
            return
        if self.bubble.isVisible():
            self.bubble.hide()
        else:
            self.show_menu()

    def show_menu(self):
        self.bubble.show_menu(config.BUBBLE_GREETING, config.MODES, self.companion)

    def open_console(self, key: str):
        self.bubble.hide()
        if key == "_dismiss":
            return
        if key == "hud" or self.modes.get(key, {}).get("page") == "hud":
            self.toggle_hud()
            return
        if key == "briefing":                       # brief du matin : l'IA utilise ses outils
            self.ask_in_chat(config.BRIEFING_PROMPT, True)
            return
        if key not in self.modes:
            return
        con = self.get_console(key)
        self._last_key = key
        state = self.win_state.get(key)
        slot = sum(1 for c in self.consoles.values() if c.isVisible() and c is not con)
        con.open_near(self.companion, state[:2] if isinstance(state, list) else None, slot)

    def toggle_hud(self):
        if self.hud.isVisible():
            self.hud.hide()
        else:
            self.hud.show()
        settings.save(hud_visible=self.hud.isVisible())

    def _check_reminders(self):
        for r in reminders.pop_due():
            msg = f"⏰ Rappel : {r['text']}"
            if self.companion.isVisible():
                self.bubble.show_notice(msg, self.companion, 15000)
            self.tray.showMessage(NAME, msg)

    def on_zoom_changed(self, zoom: float):
        self.bubble.hide()
        settings.save(zoom=zoom)

    def save_position(self):
        settings.save(pos=[self.companion.x(), self.companion.y()])

    def on_ask(self, page, text: str, extra: str = ""):
        """Une fenêtre pose une question. Les demandes sont traitées une par une (l'IA est partagée)."""
        page.begin(text)
        self._jobs.put((page, text, extra))

    def _worker(self):  # thread séparé : aucun appel Qt ici
        while True:
            page, text, extra = self._jobs.get()
            self.agent.set_mode(extra)
            self.bridge.answer.emit(page, self.agent.ask(text))

    def on_answer(self, page, text: str):
        page.deliver(text)

    def on_switched(self, old: str, new: str, reason: str):
        color = self.agent.pool.color_of(new)
        self._badge = (new, color)
        for con in self.consoles.values():
            con.set_badge(new, color)
        self.companion.avatar.set_accent(color)
        if reason:
            msg = f"⚠ {reason} → je bascule sur {new}"
        elif old:
            msg = f"✓ Retour à la normale, j'utilise {new}"
        else:
            return  # tout premier appel réussi : silence
        chat = self.consoles.get("chat")
        if chat:
            chat.notice(msg)
        if self.companion.isVisible():
            if not self.any_console_visible():
                self.bubble.show_notice(msg, self.companion, 7000)
        else:
            self.tray.showMessage(NAME, msg)

    def hide_all(self):
        if self.companion.busy or not self.companion.isVisible():
            return
        self.bubble.hide()
        for con in self.consoles.values():
            con.hide()
        self.save_position()
        self.companion.play_stop(then=self.companion.hide)   # animation d'arrêt, puis masqué

    # ------------------------------------------------------ Bureaux virtuels
    def _windows(self) -> list:
        return [self.companion, self.bubble, self.hud, *self.consoles.values()]

    def _check_desktop(self):
        """Sur un autre bureau virtuel : on cache tout ; de retour sur le bureau d'Orby : on remet."""
        if self._quitting or self.guard is None:
            return
        state = self.guard.poll()
        if state == "away" and not self._away:
            self._away = True
            self._parked = [w for w in self._windows() if w.isVisible()]
            for w in self._parked:
                w.hide()
        elif state == "home" and self._away:
            self._restore_parked()

    def _restore_parked(self):
        self._away = False
        parked, self._parked = self._parked, []
        for w in parked:
            w.show()

    def bring_here(self):
        """Orby vient sur le bureau où tu es, et y reste désormais."""
        if self.guard:
            self.guard.bring_here()
        if self._away:
            self._restore_parked()
        if not self.companion.isVisible():
            self.companion.show()
            self.companion.play_start()

    def toggle_companion(self):
        if self._away:                       # raccourci / icône de notification depuis un autre bureau
            self.bring_here()
            return
        if self.companion.busy:
            return
        if self.companion.isVisible():
            self.hide_all()
        else:
            self.companion.show()
            self.companion.play_start()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self.bubble.hide()
        for con in self.consoles.values():
            con.hide()
        self.hud.hide()
        self.save_position()
        if self.companion.isVisible():
            self.companion.play_stop(then=self._finish_quit)   # animation d'arrêt, puis on quitte
            QTimer.singleShot(4000, self._finish_quit)         # sécurité si elle ne finit pas
        else:
            self._finish_quit()

    def _finish_quit(self):
        if self._quit_done:
            return
        self._quit_done = True
        try:
            self._hotkey.stop()
        except Exception:
            pass
        self.tray.hide()
        self.app.quit()

    # ----------------------------------------------------- Tray / raccourci
    def _setup_tray(self):
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#3fd8ff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(4, 4, 24, 24)
        p.setBrush(QColor("#070b16"))
        p.drawEllipse(9, 11, 14, 10)
        p.end()
        self.tray = QSystemTrayIcon(QIcon(pm), self)
        self.tray.setToolTip(NAME)
        self.menu = QMenu()
        self.menu.addAction(f"Afficher / masquer {NAME}", self.toggle_companion)
        self.menu.addAction("📍 Amener Orby sur ce bureau", self.bring_here)
        self.menu.addAction("⏻ Quitter", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(
            lambda r: self.toggle_companion()
            if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _setup_hotkey(self):
        try:
            from pynput import keyboard
            self._hotkey = keyboard.GlobalHotKeys(
                {config.HOTKEY: self.bridge.toggle.emit})
            self._hotkey.start()
        except Exception as e:  # ex. Wayland : l'icône de notification reste dispo
            print("Raccourci global indisponible :", e)
