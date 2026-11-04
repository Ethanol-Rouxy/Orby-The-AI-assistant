"""Avatars interchangeables.

Pour remplacer le carré par un personnage animé plus tard :
  1. crée une classe qui hérite de BaseAvatar
  2. implémente set_state() (et set_accent(), play_start(), play_stop() si tu veux)
  3. ajoute-la dans AVATARS, puis mets AVATAR = "ta_cle" dans config.py
SpriteAvatar (spritesheets) est déjà fourni : il se règle dans config.py.
Le reste de l'application n'a pas besoin d'être modifié.
"""
import math
import types
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

import config

# Noms des animations de déplacement (fichiers drag_*.png)
DRAG_NAMES = ("drag", "drag_straight", "drag_left", "drag_right",
              "drag_left_up", "drag_left_down", "drag_right_up", "drag_right_down")


def _cfg(name, default):
    """Lit un réglage de config.py, avec une valeur par défaut s'il est absent."""
    return getattr(config, name, default)


class BaseAvatar(QWidget):
    """Contrat que tout avatar doit respecter."""

    # Émis quand une animation "start" ou "stop" est terminée (argument : son nom)
    animation_finished = Signal(str)
    split_closed = Signal()   # le retour tête + corps -> sprite normal est terminé

    # États envoyés par l'assistant : "idle", "thinking", "working", "error"
    def set_state(self, state: str):
        raise NotImplementedError

    # Couleur de l'IA actuellement utilisée (Gemini, Groq...). Optionnel.
    def set_accent(self, color: str):
        pass

    # Marge transparente autour du dessin (laisse la place aux effets). Défini par l'avatar.
    pad = 0

    # Zoom (1.0 = taille normale). Ignoré par les avatars à taille fixe.
    def set_zoom(self, zoom: float):
        pass

    # Interaction en cours : "pet" (caresse), "drag" (déplacement) ou None.
    def set_interaction(self, kind):
        pass

    # Vitesse du déplacement en pixels/seconde (choix de l'animation, inclinaison).
    def set_drag_velocity(self, vx: float, vy: float = 0.0):
        pass

    # Déplacement en 2 sprites (tête + corps). enter_split() agrandit l'avatar et renvoie le
    # décalage (QPoint) à appliquer à la fenêtre, ou None si non géré. end_split() émet split_closed.
    def enter_split(self):
        return None

    def end_split(self):
        pass

    # Animations d'apparition / de disparition. Par défaut : rien à jouer.
    def play_start(self):
        QTimer.singleShot(0, lambda: self.animation_finished.emit("start"))

    def play_stop(self):
        QTimer.singleShot(0, lambda: self.animation_finished.emit("stop"))


class DotAvatar(BaseAvatar):
    COLORS = {"idle": "#6c7a89", "thinking": "#f5a623",
              "working": "#4a90e2", "error": "#e74c3c"}

    def __init__(self):
        super().__init__()
        self.setFixedSize(32, 32)
        self.state = "idle"
        self.accent = QColor("#4285F4")
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def set_state(self, state: str):
        self.state = state
        if state in ("thinking", "working"):
            self.timer.start(50)
        else:
            self.timer.stop()  # pas d'animation au repos = 0 % de CPU
            self.phase = 0.0
            self.update()

    def set_accent(self, color: str):
        self.accent = QColor(color)
        self.update()

    def _tick(self):
        self.phase += 0.3
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 9 + 3 * math.sin(self.phase)
        p.setPen(QPen(self.accent, 2))
        p.setBrush(QColor(self.COLORS.get(self.state, "#6c7a89")))
        p.drawEllipse(QPointF(self.width() / 2, self.height() / 2), r, r)


class SquareAvatar(BaseAvatar):
    """Petit personnage carré : cligne des yeux, rebondit quand il réfléchit."""
    COLORS = {"idle": "#3d4a6b", "thinking": "#b97a14",
              "working": "#2b6cb0", "error": "#b83b3b"}

    def __init__(self):
        super().__init__()
        self.setFixedSize(72, 72)
        self.state = "idle"
        self.accent = QColor("#4285F4")
        self.phase = 0.0
        self.blink = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._schedule_blink()

    def set_state(self, state: str):
        self.state = state
        if state in ("thinking", "working"):
            self.timer.start(50)
        else:
            self.timer.stop()  # au repos : aucun redessin en continu
            self.phase = 0.0
            self.update()

    def set_accent(self, color: str):
        self.accent = QColor(color)
        self.update()

    def _tick(self):
        self.phase += 0.3
        self.update()

    def _schedule_blink(self):
        QTimer.singleShot(random.randint(2500, 6000), self._start_blink)

    def _start_blink(self):
        self.blink = True
        self.update()
        QTimer.singleShot(140, self._end_blink)

    def _end_blink(self):
        self.blink = False
        self.update()
        self._schedule_blink()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bob = 0.0 if self.state in ("idle", "error") else 3 * math.sin(self.phase)
        body = QRectF(8, 10 + bob, 56, 52)
        p.setPen(QPen(self.accent, 3))
        p.setBrush(QColor(self.COLORS.get(self.state, "#3d4a6b")))
        p.drawRoundedRect(body, 12, 12)

        ey = body.top() + 22
        for cx in (body.left() + 18, body.right() - 18):
            if self.blink or self.state == "error":
                p.setPen(QPen(QColor("white"), 2))
                p.drawLine(QPointF(cx - 5, ey), QPointF(cx + 5, ey))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(cx, ey), 6, 6)
                p.setBrush(QColor("#14161d"))
                p.drawEllipse(QPointF(cx, ey + 1), 3, 3)
        p.setPen(QPen(QColor("white"), 2))
        my = body.bottom() - 12
        p.drawLine(QPointF(body.center().x() - 6, my), QPointF(body.center().x() + 6, my))


class SpriteAvatar(BaseAvatar):
    """Personnage animé à partir de spritesheets (voir config.SPRITE_*).

    Une feuille = des images de 100x100 rangées de gauche à droite, puis de haut en bas.
    Animations : idle (boucle), start / stop (jouées une fois), et en option
    thinking / working / error / pet / drag_* (boucles).
    Sans pet.png / drag_*.png, des effets dessinés par le code prennent le relais
    (coeurs et petit "squish" pour la caresse, inclinaison pour le déplacement).
    """
    STATE_COLORS = {"thinking": "#f5a623", "working": "#4a90e2", "error": "#e74c3c"}
    SPECIAL = ("start", "stop", "pet") + DRAG_NAMES
    DRAG_ANIMS = DRAG_NAMES
    HEART_COLORS = ("#ff4fa3", "#3fd8ff")
    MAX_TILT = 12.0   # degrés

    def __init__(self, zoom: float = 1.0):
        super().__init__()
        self.fw, self.fh = config.SPRITE_FRAME_SIZE
        self.zoom = zoom
        self.anims = {}
        for name, cfg in config.SPRITE_ANIMATIONS.items():
            anim = self._load(name, cfg)
            if anim:
                self.anims[name] = anim

        self.state = "idle"
        self.accent = QColor("#4285F4")
        self.current = None
        self.index = 0
        self.locked = False         # vrai pendant start / stop : on ignore les autres états
        self.interaction = None     # "pet" | "drag" | None
        self.drag_dir = None        # "left", "right", "left_up", "straight"... (sens du déplacement)
        self._cand = None           # sens candidat, en attente de confirmation
        self._cand_t = 0.0
        self.tilt = 0.0
        self.tilt_target = 0.0
        self.hearts = []
        self.fx_time = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.fx_timer = QTimer(self)        # effets de secours : actif seulement quand il le faut
        self.fx_timer.timeout.connect(self._fx_tick)
        self._add_drag_mirrors()
        # --- déplacement en 2 sprites : tête (suit la souris) + corps (pendule) ---
        self.split = None
        if _cfg("SPLIT_ENABLED", True):
            head = self._load("split_head", _cfg("SPLIT_HEAD", {"file": "drag-head.png"}))
            body = self._load("split_body", _cfg("SPLIT_BODY", {"file": "corps.png"}))
            if head and body:
                self.split = {"head": head, "body": body}
                print(f"[split] ACTIF : tête {head['size'][0]}x{head['size'][1]} ({len(head['frames'])} img), "
                      f"corps {body['size'][0]}x{body['size'][1]} ({len(body['frames'])} img)")
            else:
                print("[split] INACTIF : "
                      f"{'tête' if not head else ''}{' et ' if not head and not body else ''}"
                      f"{'corps' if not body else ''} non chargé(s) (voir les messages [sprites] ci-dessus). "
                      "Retour aux animations drag_*.")
        self.split_on = False
        self._settling = False
        self._sp_head = QPointF()             # coin de la tête dans l'avatar agrandi
        self._sp_t = 0.0
        self._sp_last = 0.0
        self._sp_settle_t = 0.0
        self._reset_split_state()
        self.split_timer = QTimer(self)
        self.split_timer.timeout.connect(self._split_tick)
        self._resize()
        if "idle" in self.anims:
            self._play("idle")

    # ------------------------------------------------------------ Chargement
    def _load(self, name: str, cfg: dict):
        path = config.SPRITES_DIR / cfg["file"]
        if not path.exists():
            if name in ("idle", "start", "stop") or name.startswith("split_"):
                print(f"[sprites] {cfg['file']} introuvable dans {config.SPRITES_DIR}")
            return None
        sheet = QPixmap(str(path))
        if sheet.isNull():
            print(f"[sprites] {cfg['file']} n'est pas une image valide")
            return None
        fw, fh = self._frame_size(sheet, cfg, name)
        cols, rows = sheet.width() // fw, sheet.height() // fh
        if cols * rows == 0:
            print(f"[sprites] {cfg['file']} ({sheet.width()}x{sheet.height()}) est plus petit "
                  f"qu'une image ({fw}x{fh})")
            return None
        if sheet.width() % fw or sheet.height() % fh:
            print(f"[sprites] ATTENTION {cfg['file']} : {sheet.width()}x{sheet.height()} "
                  f"n'est pas un multiple de {fw}x{fh}, les bords seront ignorés")
        frames = [sheet.copy(c * fw, r * fh, fw, fh)
                  for r in range(rows) for c in range(cols)]
        if cfg.get("frames"):
            frames = frames[: cfg["frames"]]
        else:  # on retire les cases vides à la fin de la feuille
            while len(frames) > 1 and self._is_blank(frames[-1]):
                frames.pop()
        fps = cfg.get("fps", 8)
        loop = cfg.get("loop", name not in ("start", "stop"))
        print(f"[sprites] {name}: {len(frames)} images à {fps} img/s"
              f"{'' if loop else ' (jouée une fois)'}")
        return {"frames": frames, "fps": fps, "loop": loop, "size": (fw, fh),
                "scale": cfg.get("scale", 1.0)}

    def _frame_size(self, sheet: QPixmap, cfg: dict, name: str):
        """Taille d'une image de la feuille. Pour la tête / le corps, si la feuille n'est pas un
        multiple de SPRITE_FRAME_SIZE, on la prend telle quelle (une image, ou une bande de
        `frames` images côte à côte) au lieu de la découper de travers."""
        if cfg.get("frame_size"):
            return tuple(cfg["frame_size"])
        fw, fh = self.fw, self.fh
        if name.startswith("split_") and (sheet.width() < fw or sheet.height() < fh
                                          or sheet.width() % fw or sheet.height() % fh):
            n = cfg.get("frames") or 1
            size = (sheet.width() // n, sheet.height())
            print(f"[sprites] {cfg['file']} fait {sheet.width()}x{sheet.height()} (pas un multiple de "
                  f"{fw}x{fh}) : lu comme {n} image(s) de {size[0]}x{size[1]}. "
                  f"Ajoute \"frame_size\": (l, h) dans config.py pour forcer une autre taille.")
            return size
        return fw, fh

    def _add_drag_mirrors(self):
        """Si un côté d'une animation de déplacement manque, crée-le en miroir de l'autre."""
        if not _cfg("DRAG_MIRROR", True):
            return
        flip = QTransform().scale(-1, 1)
        pairs = (("drag_right", "drag_left"), ("drag_left", "drag_right"),
                 ("drag_right_up", "drag_left_up"), ("drag_left_up", "drag_right_up"),
                 ("drag_right_down", "drag_left_down"), ("drag_left_down", "drag_right_down"))
        for src, dst in pairs:
            if src in self.anims and dst not in self.anims:
                anim = self.anims[src]
                self.anims[dst] = {**anim, "frames": [f.transformed(flip) for f in anim["frames"]]}
                print(f"[sprites] {dst}: créée en miroir de {src}")

    @staticmethod
    def _is_blank(pm: QPixmap) -> bool:
        img = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        return not any(bytes(img.constBits())[3::4])  # aucun pixel visible

    # ---------------------------------------------------------------- Taille
    def _resize(self):
        scale = config.SPRITE_SCALE * self.zoom
        self.sw, self.sh = round(self.fw * scale), round(self.fh * scale)
        self.pad = max(12, round(0.14 * max(self.sw, self.sh)))   # place pour l'inclinaison et les coeurs
        self.setFixedSize(self.sw + 2 * self.pad, self.sh + 2 * self.pad)

    def set_zoom(self, zoom: float):
        self.zoom = zoom
        self._resize()
        self.update()

    # ------------------------------------------------------------- Lecture
    def _interval(self, fps: float) -> int:
        return max(10, int(1000 / max(0.1, fps * config.SPRITE_SPEED)))

    def _play(self, name: str):
        anim = self.anims[name]
        self.current, self.index = name, 0
        if len(anim["frames"]) > 1:
            self.timer.start(self._interval(anim["fps"]))
        else:
            self.timer.stop()
        self.update()

    def _tick(self):
        anim = self.anims[self.current]
        if self.index + 1 < len(anim["frames"]):
            self.index += 1
        elif anim["loop"]:
            self.index = 0
        else:
            self.timer.stop()          # animation jouée une fois : terminée
            self._on_finished(self.current)
        self.update()

    def _on_finished(self, name: str):
        if name == "start":
            self.locked = False
            self._apply_state()
        self.animation_finished.emit(name)   # après "stop", on reste sur la dernière image

    def _run_once(self, name: str):
        if name in self.anims:
            self.locked = True
            self._play(name)
            if len(self.anims[name]["frames"]) == 1:   # image unique : on termine tout de suite
                QTimer.singleShot(self._interval(self.anims[name]["fps"]),
                                  lambda: self._on_finished(name))
        else:
            if name == "start":
                self._apply_state()
            QTimer.singleShot(0, lambda: self.animation_finished.emit(name))

    def _drag_chain(self) -> tuple:
        """Animations à essayer, de la plus précise à la plus générale."""
        d = self.drag_dir
        if d in ("left_up", "left_down", "right_up", "right_down"):
            first = (f"drag_{d}", f"drag_{d.split('_')[0]}")    # diagonale, puis gauche/droite
        elif d in ("left", "right"):
            first = (f"drag_{d}",)
        else:
            first = ()                                          # vertical ou inconnu : animation de base
        return first + ("drag", "drag_straight")

    def _wanted(self) -> str:
        if self.interaction == "drag":
            if not self.split:                      # sans sprites tête/corps : anciennes anims drag_*
                for name in self._drag_chain():
                    if name in self.anims:
                        return name
        elif self.interaction in self.anims:
            return self.interaction
        if self.state in self.anims and self.state not in self.SPECIAL:
            return self.state
        return "idle"

    def _apply_state(self):
        if self.locked:
            return
        name = self._wanted()
        if name in self.anims and name != self.current:
            self._play(name)

    # --------------------------------------------------------------- API
    def play_start(self):
        self.locked = False
        self._run_once("start")

    def play_stop(self):
        self._run_once("stop")

    def set_state(self, state: str):
        self.state = state
        self._apply_state()
        self.update()

    def set_accent(self, color: str):
        self.accent = QColor(color)
        self.update()

    def set_interaction(self, kind):
        self.interaction = kind
        self.drag_dir = None            # le sens sera détecté dès les premiers mouvements
        self._cand = None
        self._apply_state()
        if kind:
            self._ensure_fx()
        self.update()

    @staticmethod
    def _classify_drag(vx: float, vy: float):
        """Sens du déplacement : left, right, left_up, left_down, right_up, right_down, straight.
        Retourne None si la souris va trop lentement pour décider (on garde le sens actuel)."""
        if math.hypot(vx, vy) < _cfg("DRAG_MIN_SPEED", 80):
            return None
        ratio = _cfg("DRAG_AXIS_RATIO", 0.4)
        ax, ay = abs(vx), abs(vy)
        if ax < ratio * ay:                     # presque vertical : on garde l'animation de base
            return "straight"
        side = "right" if vx > 0 else "left"
        if ay < ratio * ax:                     # presque horizontal
            return side
        return f"{side}_{'down' if vy > 0 else 'up'}"   # diagonale (l'écran compte y vers le bas)

    def set_drag_velocity(self, vx: float, vy: float = 0.0):
        if self.split:                  # le corps est géré par la physique, pas par des animations
            return
        if self.interaction == "drag":
            cand = self._classify_drag(vx, vy)
            if cand is not None and cand != self.drag_dir:
                now = time.monotonic()
                if cand != self._cand:                       # nouveau sens : on attend qu'il se confirme
                    self._cand, self._cand_t = cand, now
                if self.drag_dir is None or (now - self._cand_t) * 1000 >= _cfg("DRAG_HOLD_MS", 90):
                    self.drag_dir, self._cand = cand, None
                    self._apply_state()
            elif cand == self.drag_dir:
                self._cand = None
        # l'inclinaison n'est qu'un effet de secours : coupée si une vraie animation de déplacement joue
        if _cfg("DRAG_TILT", True) and self.current not in self.DRAG_ANIMS:
            self.tilt_target = max(-self.MAX_TILT, min(self.MAX_TILT, vx * 0.012))
            self._ensure_fx()
        else:
            self.tilt_target = 0.0

    # ------------------------------------------------- Effets de secours
    def _ensure_fx(self):
        if not self.fx_timer.isActive():
            self.fx_timer.start(33)

    def _fx_tick(self):
        dt = 0.033
        self.fx_time += dt
        self.tilt += (self.tilt_target - self.tilt) * 0.25    # ressort vers la cible
        self.tilt_target *= 0.88                              # la cible retombe doucement
        if (self.interaction == "pet" and _cfg("PET_HEARTS", True)
                and len(self.hearts) < 8 and random.random() < 0.22):
            life = random.uniform(0.9, 1.3)
            self.hearts.append({
                "x": self.pad + self.sw * random.uniform(0.25, 0.75),
                "y": self.pad + self.sh * 0.18,
                "vy": random.uniform(0.6, 1.1) * max(0.6, self.sh / 100),
                "phase": random.uniform(0, 6.28), "life": life,
                "color": random.choice(self.HEART_COLORS),
            })
        for h in self.hearts:
            h["y"] -= h["vy"]
            h["x"] += math.sin(h["phase"] + self.fx_time * 6) * 0.6
            h["life"] -= dt
        self.hearts = [h for h in self.hearts if h["life"] > 0]
        if (not self.interaction and not self.hearts
                and abs(self.tilt) < 0.15 and abs(self.tilt_target) < 0.15):
            self.tilt = self.tilt_target = 0.0
            self.fx_timer.stop()
        self.update()

    @staticmethod
    def _draw_heart(p: QPainter, cx: float, cy: float, s: float, color: QColor):
        path = QPainterPath()
        path.moveTo(cx, cy + s * 0.35)
        path.cubicTo(cx - s * 1.1, cy - s * 0.5, cx - s * 0.4, cy - s * 1.0, cx, cy - s * 0.35)
        path.cubicTo(cx + s * 0.4, cy - s * 1.0, cx + s * 1.1, cy - s * 0.5, cx, cy + s * 0.35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    # ------------------------------------------ Déplacement : tête + corps
    def _scale(self) -> float:
        return config.SPRITE_SCALE * self.zoom

    def _reset_split_state(self):
        self._sp_ang = 0.0          # direction du corps autour de la tête : 0 = en dessous, π = au-dessus
        self._sp_omega = 0.0        # vitesse de rotation (rad / tick)
        self._sp_extra = 0.0        # distance supplémentaire due à la vitesse (pixels)
        self._sp_vel = (0.0, 0.0)   # vitesse de la tête (px / s), lissée
        self._sp_hprev = None
        self._sp_moving = False

    def _split_geom(self):
        """Tout ce qu'il faut savoir (en pixels écran) sur la tête, le corps et l'orbite du corps."""
        s = self._scale()
        hfw, hfh = self.split["head"]["size"]
        bfw, bfh = self.split["body"]["size"]
        hs, bs = self.split["head"]["scale"], self.split["body"]["scale"]
        x1, y1, x2, y2 = _cfg("SPLIT_HEAD_BOX", (22, 6, 79, 52))   # zone occupée par la tête dans sa feuille
        k = s * hs
        return types.SimpleNamespace(
            s=s, hw=hfw * k, hh=hfh * k, bw=bfw * s * bs, bh=bfh * s * bs,
            cx=(x1 + x2) / 2 * k, cy=(y1 + y2) / 2 * k,             # centre de la tête
            a=(x2 - x1) / 2 * k, b=(y2 - y1) / 2 * k,               # demi-largeur / demi-hauteur de la tête
            gap=_cfg("SPLIT_GAP", 2.5) * s,                         # espace tête -> corps au repos
            max_extra=_cfg("SPLIT_MAX_EXTRA", 14) * s,
            shape=_cfg("SPLIT_HEAD_SHAPE", 2.5))

    @staticmethod
    def _orbit_dist(g, theta: float, extra: float) -> float:
        """Distance centre de la tête -> centre du corps dans la direction theta : on suit le contour de
        la tête (ellipse), plus l'espace, plus la demi-hauteur du corps (son « bas » pointe vers l'extérieur)."""
        ux, uy = abs(math.sin(theta)), abs(math.cos(theta))
        edge = (((ux / g.a) ** g.shape) + ((uy / g.b) ** g.shape)) ** (-1.0 / g.shape)
        return edge + g.gap + g.bh / 2 + extra

    def enter_split(self):
        if not self.split:
            return None
        if self.split_on:                 # on ressaisit Orby pendant qu'il se « remet en place »
            self._settling = False
            return QPoint(0, 0)
        g = self._split_geom()
        hx, hy = (v * g.s for v in _cfg("SPLIT_HEAD_POS", (0, 0)))
        # zone où le corps peut aller : un cercle autour du centre de la tête
        radius = max(g.a, g.b) + g.gap + g.bh / 2 + g.max_extra + math.hypot(g.bw, g.bh) / 2 + 2
        left, top = math.floor(min(0.0, g.cx - radius)), math.floor(min(0.0, g.cy - radius))
        right, bottom = math.ceil(max(g.hw, g.cx + radius)), math.ceil(max(g.hh, g.cy + radius))
        self._resize()                                   # (re)calcule self.pad
        pad = self.pad
        self._sp_head = QPointF(-left + pad, -top + pad)             # coordonnées ENTIÈRES : image nette
        self.setFixedSize(right - left + 2 * pad, bottom - top + 2 * pad)
        self.split_on, self._settling = True, False
        self._reset_split_state()
        self._sp_t = 0.0
        self._sp_last = time.monotonic()
        self.split_timer.start(16)
        self.update()
        # décalage de la fenêtre pour que la tête reste exactement là où était le sprite
        return QPoint(-left - round(hx), -top - round(hy))

    def end_split(self):
        """Orby est relâché : le corps revient à sa place, puis on attend avant de remettre l'idle."""
        if self.split_on:
            self._settling, self._sp_settle_t = True, 0.0

    def _head_center_global(self) -> QPointF:
        g = self._split_geom()
        o = self.mapToGlobal(QPoint(0, 0))
        return QPointF(o.x() + self._sp_head.x() + g.cx, o.y() + self._sp_head.y() + g.cy)

    def _split_tick(self):
        now = time.monotonic()
        dt, self._sp_last = max(0.001, min(0.1, now - self._sp_last)), now
        self._sp_t += dt
        g = self._split_geom()

        # vitesse de la tête (lissée sur ~80 ms)
        h = self._head_center_global()
        if self._sp_hprev is not None:
            k = min(1.0, dt / 0.08)
            ix, iy = (h.x() - self._sp_hprev.x()) / dt, (h.y() - self._sp_hprev.y()) / dt
            self._sp_vel = (self._sp_vel[0] + (ix - self._sp_vel[0]) * k,
                            self._sp_vel[1] + (iy - self._sp_vel[1]) * k)
        self._sp_hprev = h
        vx, vy = self._sp_vel
        speed = math.hypot(vx, vy)

        follow = _cfg("SPLIT_FOLLOW", 0.06)
        brake = _cfg("SPLIT_BRAKE", 0.18)
        min_speed = _cfg("SPLIT_MIN_SPEED", 90)
        stretch = _cfg("SPLIT_STRETCH", 0.02)
        for _ in range(max(1, min(4, round(dt / 0.016)))):
            # en mouvement : le corps se place à l'OPPOSÉ de la direction ; à l'arrêt : il retombe en dessous
            limit = min_speed * (0.6 if self._sp_moving else 1.0)           # hystérésis : pas de clignotement
            self._sp_moving = speed > limit and not self._settling
            target = math.atan2(-vx, -vy) if self._sp_moving else 0.0
            diff = (target - self._sp_ang + math.pi) % (2 * math.pi) - math.pi
            self._sp_omega += follow * diff - brake * self._sp_omega
            self._sp_omega = max(-0.5, min(0.5, self._sp_omega))
            self._sp_ang = (self._sp_ang + self._sp_omega + math.pi) % (2 * math.pi) - math.pi
            extra_target = min(g.max_extra, speed * stretch * g.s) if self._sp_moving else 0.0
            self._sp_extra += (extra_target - self._sp_extra) * 0.15

        if self._settling:
            self._sp_settle_t += dt
            delay = _cfg("SPLIT_RELEASE_DELAY", 0.7)
            calm = (abs(self._sp_ang) < 0.08 and abs(self._sp_omega) < 0.03 and self._sp_extra < 0.5)
            if self._sp_settle_t >= delay and (calm or self._sp_settle_t >= delay + 1.5):
                self.split_timer.stop()
                self.split_on = self._settling = False
                self._resize()
                self.update()
                self.split_closed.emit()
                return
        self.update()

    @staticmethod
    def _split_frame(anim: dict, t: float):
        n = len(anim["frames"])
        if n == 1:
            return anim["frames"][0]
        i = int(t * anim["fps"] * config.SPRITE_SPEED)
        return anim["frames"][i % n] if anim["loop"] else anim["frames"][min(i, n - 1)]

    def _paint_split(self):
        p = QPainter(self)
        g = self._split_geom()
        head_c = QPointF(self._sp_head.x() + g.cx, self._sp_head.y() + g.cy)
        theta = self._sp_ang
        dist = self._orbit_dist(g, theta, self._sp_extra)
        c_l = QPointF(round(head_c.x() + math.sin(theta) * dist),      # arrondi : pas de demi-pixel = pas de flou
                      round(head_c.y() + math.cos(theta) * dist))
        # le « bas » du corps pointe à l'opposé de la tête : il pivote avec sa position autour de elle
        body = self._split_frame(self.split["body"], self._sp_t)
        body_smooth = bool(_cfg("SPLIT_BODY_SMOOTH", False))           # True = rotation lissée (un peu floue)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, config.SPRITE_SMOOTH or body_smooth)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, body_smooth)
        p.save()
        p.translate(c_l)
        p.rotate(-math.degrees(theta))
        p.drawPixmap(QRectF(-g.bw / 2, -g.bh / 2, g.bw, g.bh), body, QRectF(body.rect()))
        p.restore()
        head = self._split_frame(self.split["head"], self._sp_t)       # la tête par-dessus le corps
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, config.SPRITE_SMOOTH)   # tête : pixels nets
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.drawPixmap(QRectF(self._sp_head, QSizeF(g.hw, g.hh)), head, QRectF(head.rect()))
        if _cfg("SPLIT_DEBUG", False):                                 # repères pour régler les valeurs
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(QColor("#ff2e97"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(head_c, 3, 3)                                # rose : centre de la tête
            p.setBrush(QColor("#3fd8ff"))
            p.drawEllipse(c_l, 3, 3)                                   # cyan : centre du corps
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#ffb02e"), 1))
            p.drawEllipse(head_c, g.a, g.b)                            # orange : contour de la tête utilisé

    def paintEvent(self, _):
        if self.split_on:
            self._paint_split()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        smooth = config.SPRITE_SMOOTH or self.sw < self.fw or abs(self.tilt) > 0.3
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
        target = QRect(self.pad, self.pad, self.sw, self.sh)

        p.save()
        if abs(self.tilt) > 0.05:                        # penché pendant le déplacement
            c = QPointF(target.center())
            p.translate(c)
            p.rotate(self.tilt)
            p.translate(-c)
        if self.interaction == "pet" and "pet" not in self.anims:   # petit "squish" de plaisir
            k = 0.035 * math.sin(self.fx_time * 16)
            p.translate(target.center().x(), target.bottom())
            p.scale(1 + k, 1 - k)
            p.translate(-target.center().x(), -target.bottom())
        anim = self.anims.get(self.current)
        if anim:
            p.drawPixmap(target, anim["frames"][self.index])
        p.restore()

        for h in self.hearts:                            # coeurs de la caresse
            color = QColor(h["color"])
            color.setAlphaF(max(0.0, min(1.0, h["life"] / 0.5)))
            self._draw_heart(p, h["x"], h["y"], max(5.0, self.sw * 0.07), color)

        # Pas d'animation dédiée à cet état ? Un petit point de couleur le signale.
        if (not self.locked and self.state in self.STATE_COLORS
                and self.state not in self.anims):
            p.setPen(QPen(self.accent, 2))
            p.setBrush(QColor(self.STATE_COLORS[self.state]))
            p.drawEllipse(QPointF(self.pad + self.sw - 12, self.pad + 12), 6, 6)


def make_avatar() -> BaseAvatar:
    """Crée l'avatar choisi dans config.AVATAR (avec un carré de secours)."""
    if config.AVATAR == "sprite":
        avatar = SpriteAvatar()
        if "idle" in avatar.anims:
            return avatar
        print("[sprites] animation 'idle' absente : personnage carré de secours")
        return SquareAvatar()
    return AVATARS[config.AVATAR]()


AVATARS = {"dot": DotAvatar, "square": SquareAvatar, "sprite": SpriteAvatar}
