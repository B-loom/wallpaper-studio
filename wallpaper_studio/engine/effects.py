"""Effets visuels superposes au fond d'ecran.

Chaque effet est un systeme de particules simple, dessine par Qt dans une
couche transparente placee au-dessus du contenu. L'implementation privilegie la
sobriete : nombre de particules borne, calculs en virgule flottante simple,
cadence plafonnee. Sur un processeur modeste, une couche d'effets coute
typiquement 1 a 3 % de processeur a 30 images par seconde.

Les effets disponibles sont declares dans :data:`EFFECT_REGISTRY`. Tout effet
listé dans l'interface est implemente ici : aucun bouton decoratif.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QElapsedTimer, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .playback import EffectConfig

log = logging.getLogger(__name__)

#: Nombre maximal de particules, toutes couches confondues.
MAX_PARTICLES = 900


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float = 1.0
    max_life: float = 1.0
    phase: float = 0.0


class EffectLayer:
    """Classe de base d'un effet de particules."""

    name = "base"
    label = "Effet"
    #: Nombre de particules pour une intensite de 1.0.
    base_count = 120

    def __init__(self, config: EffectConfig, size: Tuple[int, int]):
        self.config = config
        self.width, self.height = size
        self.particles: List[Particle] = []
        self._rng = random.Random()
        self.resize(size)

    @property
    def count(self) -> int:
        return max(1, int(self.base_count * max(0.05, self.config.intensity)))

    def resize(self, size: Tuple[int, int]) -> None:
        self.width, self.height = max(1, size[0]), max(1, size[1])
        self.particles = [self.spawn(initial=True) for _ in range(self.count)]

    def spawn(self, initial: bool = False) -> Particle:
        raise NotImplementedError

    def update(self, dt: float) -> None:
        raise NotImplementedError

    def draw(self, painter: QPainter) -> None:
        raise NotImplementedError


class RainEffect(EffectLayer):
    name = "pluie"
    label = "Pluie"
    base_count = 220

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=self._rng.uniform(-50, self.width + 50),
            y=self._rng.uniform(-self.height, 0) if initial else self._rng.uniform(-60, -10),
            vx=self._rng.uniform(-40, -10),
            vy=self._rng.uniform(600, 1100),
            size=self._rng.uniform(8, 20),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.y > self.height + 20:
                fresh = self.spawn()
                p.x, p.y, p.vx, p.vy, p.size = fresh.x, fresh.y, fresh.vx, fresh.vy, fresh.size

    def draw(self, painter: QPainter) -> None:
        pen = QPen(QColor(190, 215, 255, 150))
        pen.setWidthF(1.3)
        painter.setPen(pen)
        for p in self.particles:
            # La trainee suit la direction de chute : plus lisible qu'un trait vertical.
            scale = p.size / max(1.0, math.hypot(p.vx, p.vy)) * 60
            painter.drawLine(
                QPointF(p.x, p.y), QPointF(p.x - p.vx * scale * 0.02, p.y - p.vy * scale * 0.02)
            )


class SnowEffect(EffectLayer):
    name = "neige"
    label = "Neige"
    base_count = 160

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=self._rng.uniform(0, self.width),
            y=self._rng.uniform(0, self.height) if initial else self._rng.uniform(-40, -5),
            vx=self._rng.uniform(-18, 18),
            vy=self._rng.uniform(25, 85),
            size=self._rng.uniform(1.6, 4.2),
            phase=self._rng.uniform(0, math.tau),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.phase += dt * 1.6
            # Oscillation laterale : chute en feuille morte.
            p.x += (p.vx + math.sin(p.phase) * 22) * dt
            p.y += p.vy * dt
            if p.y > self.height + 10:
                fresh = self.spawn()
                p.x, p.y, p.vx, p.vy, p.size = fresh.x, fresh.y, fresh.vx, fresh.vy, fresh.size
            if p.x < -20:
                p.x = self.width + 10
            elif p.x > self.width + 20:
                p.x = -10

    def draw(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 205))
        for p in self.particles:
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)


class StarsEffect(EffectLayer):
    name = "etoiles"
    label = "Etoiles"
    base_count = 170

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=self._rng.uniform(0, self.width),
            y=self._rng.uniform(0, self.height),
            vx=0.0,
            vy=0.0,
            size=self._rng.uniform(0.7, 2.3),
            phase=self._rng.uniform(0, math.tau),
            life=self._rng.uniform(0.4, 1.0),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            # Scintillement : vitesse propre a chaque etoile.
            p.phase += dt * (0.7 + p.size * 0.6)

    def draw(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        for p in self.particles:
            twinkle = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(p.phase))
            painter.setBrush(QColor(255, 253, 235, int(230 * twinkle * p.life)))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)


class ParticlesEffect(EffectLayer):
    name = "particules"
    label = "Particules"
    base_count = 130

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=self._rng.uniform(0, self.width),
            y=self._rng.uniform(0, self.height),
            vx=self._rng.uniform(-26, 26),
            vy=self._rng.uniform(-26, 26),
            size=self._rng.uniform(1.2, 3.4),
            phase=self._rng.uniform(0, math.tau),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.phase += dt
            # Rebond souple sur les bords.
            if p.x < 0 or p.x > self.width:
                p.vx = -p.vx
                p.x = min(max(p.x, 0), self.width)
            if p.y < 0 or p.y > self.height:
                p.vy = -p.vy
                p.y = min(max(p.y, 0), self.height)

    def draw(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(140, 200, 255, 165))
        for p in self.particles:
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)


class FogEffect(EffectLayer):
    name = "brouillard"
    label = "Brouillard"
    base_count = 16

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=self._rng.uniform(-0.25 * self.width, self.width),
            y=self._rng.uniform(0, self.height),
            vx=self._rng.uniform(6, 26),
            vy=self._rng.uniform(-3, 3),
            size=self._rng.uniform(0.25, 0.55) * self.width,
            life=self._rng.uniform(0.25, 0.6),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.x - p.size > self.width:
                p.x = -p.size
                p.y = self._rng.uniform(0, self.height)

    def draw(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        for p in self.particles:
            gradient = QRadialGradient(QPointF(p.x, p.y), p.size)
            alpha = int(70 * p.life * self.config.intensity * 2)
            gradient.setColorAt(0.0, QColor(225, 232, 245, min(110, alpha)))
            gradient.setColorAt(1.0, QColor(225, 232, 245, 0))
            painter.setBrush(gradient)
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size * 0.55)


class GlowEffect(EffectLayer):
    name = "lueurs"
    label = "Lueurs"
    base_count = 10

    _PALETTE = (
        (120, 190, 255), (255, 150, 200), (160, 255, 200),
        (255, 220, 140), (190, 160, 255),
    )

    def spawn(self, initial: bool = False) -> Particle:
        p = Particle(
            x=self._rng.uniform(0, self.width),
            y=self._rng.uniform(0, self.height),
            vx=self._rng.uniform(-14, 14),
            vy=self._rng.uniform(-14, 14),
            size=self._rng.uniform(0.08, 0.22) * self.width,
            phase=self._rng.uniform(0, math.tau),
        )
        p.life = self._rng.randrange(len(self._PALETTE))
        return p

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.phase += dt * 0.8
            if p.x < -p.size or p.x > self.width + p.size:
                p.vx = -p.vx
            if p.y < -p.size or p.y > self.height + p.size:
                p.vy = -p.vy

    def draw(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        for p in self.particles:
            r, g, b = self._PALETTE[int(p.life) % len(self._PALETTE)]
            pulse = 0.55 + 0.45 * math.sin(p.phase)
            gradient = QRadialGradient(QPointF(p.x, p.y), p.size)
            gradient.setColorAt(0.0, QColor(r, g, b, int(95 * pulse)))
            gradient.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(gradient)
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)


class WavesEffect(EffectLayer):
    name = "ondes"
    label = "Ondes"
    base_count = 5

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(
            x=0.0, y=self._rng.uniform(0.55, 0.95) * self.height,
            vx=self._rng.uniform(0.35, 0.9), vy=self._rng.uniform(8, 26),
            size=self._rng.uniform(0.008, 0.03) * self.height,
            phase=self._rng.uniform(0, math.tau),
        )

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.phase += dt * p.vx

    def draw(self, painter: QPainter) -> None:
        painter.setBrush(Qt.NoBrush)
        step = max(6, self.width // 160)
        for index, p in enumerate(self.particles):
            pen = QPen(QColor(150, 205, 255, int(90 * self.config.intensity * 2)))
            pen.setWidthF(1.4)
            painter.setPen(pen)
            previous: Optional[QPointF] = None
            for sx in range(0, self.width + step, step):
                angle = p.phase + sx / max(40.0, self.width / (6 + index))
                sy = p.y + math.sin(angle) * p.size * 6
                point = QPointF(sx, sy)
                if previous is not None:
                    painter.drawLine(previous, point)
                previous = point


class MouseGlowEffect(EffectLayer):
    """Halo suivant le curseur : interactivite a la souris."""

    name = "halo_souris"
    label = "Halo a la souris"
    base_count = 1

    def __init__(self, config: EffectConfig, size: Tuple[int, int]):
        self.mouse = QPointF(-10000, -10000)
        super().__init__(config, size)

    def spawn(self, initial: bool = False) -> Particle:
        return Particle(x=0, y=0, vx=0, vy=0, size=0.14 * max(self.width, self.height))

    def update(self, dt: float) -> None:
        pass

    def set_mouse(self, x: float, y: float) -> None:
        self.mouse = QPointF(x, y)

    def draw(self, painter: QPainter) -> None:
        if self.mouse.x() < -1000:
            return
        radius = self.particles[0].size
        gradient = QRadialGradient(self.mouse, radius)
        alpha = int(120 * self.config.intensity)
        gradient.setColorAt(0.0, QColor(255, 255, 255, alpha))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(self.mouse, radius, radius)


#: Effets disponibles, par identifiant.
EFFECT_REGISTRY: Dict[str, type] = {
    cls.name: cls
    for cls in (
        ParticlesEffect, RainEffect, SnowEffect, StarsEffect,
        FogEffect, GlowEffect, WavesEffect, MouseGlowEffect,
    )
}


def available_effects() -> List[Tuple[str, str]]:
    """Liste ``(identifiant, libelle)`` des effets implementes."""
    return [(name, cls.label) for name, cls in EFFECT_REGISTRY.items()]


class EffectsOverlay(QWidget):
    """Couche transparente dessinant les effets actifs au-dessus du fond."""

    def __init__(self, configs: Tuple[EffectConfig, ...] = (), fps: int = 30, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._layers: List[EffectLayer] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._elapsed = QElapsedTimer()
        self._fps = max(5, fps)
        self._frames = 0
        self._fps_timer = QElapsedTimer()
        self._measured_fps: Optional[float] = None

        self.set_effects(configs)

    # --- Configuration -----------------------------------------------------
    def set_effects(self, configs: Tuple[EffectConfig, ...]) -> None:
        """Remplace les effets actifs."""
        self._layers.clear()
        size = (max(1, self.width()), max(1, self.height()))
        budget = MAX_PARTICLES
        for config in configs:
            if not config.enabled or config.intensity <= 0:
                continue
            cls = EFFECT_REGISTRY.get(config.name)
            if cls is None:
                log.warning("Effet inconnu ignore : %s", config.name)
                continue
            layer = cls(config, size)
            # Budget global : au-dela, on reduit le dernier effet ajoute plutot
            # que de laisser la cadence s'effondrer.
            if len(layer.particles) > budget:
                layer.particles = layer.particles[: max(1, budget)]
            budget -= len(layer.particles)
            self._layers.append(layer)

        if self._layers:
            self._elapsed.start()
            self._fps_timer.start()
            self._timer.start(int(1000 / self._fps))
        else:
            self._timer.stop()
            self._measured_fps = None
        self.update()

    def set_fps(self, fps: int) -> None:
        self._fps = max(5, fps)
        if self._timer.isActive():
            self._timer.start(int(1000 / self._fps))

    @property
    def has_effects(self) -> bool:
        return bool(self._layers)

    @property
    def particle_count(self) -> int:
        return sum(len(layer.particles) for layer in self._layers)

    def measured_fps(self) -> Optional[float]:
        return self._measured_fps

    def set_mouse(self, x: float, y: float) -> None:
        for layer in self._layers:
            if isinstance(layer, MouseGlowEffect):
                layer.set_mouse(x, y)

    # --- Rendu -------------------------------------------------------------
    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._layers:
            self._elapsed.restart()
            self._timer.start(int(1000 / self._fps))

    def _tick(self) -> None:
        dt = self._elapsed.restart() / 1000.0
        # Un ecart enorme (veille, systeme sature) ferait « teleporter » les
        # particules : on borne le pas de simulation.
        dt = min(dt, 0.1)
        for layer in self._layers:
            layer.update(dt)
        self._frames += 1
        if self._fps_timer.elapsed() >= 1000:
            self._measured_fps = self._frames * 1000.0 / self._fps_timer.elapsed()
            self._frames = 0
            self._fps_timer.restart()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        size = (max(1, self.width()), max(1, self.height()))
        for layer in self._layers:
            layer.resize(size)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        if not self._layers:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for layer in self._layers:
            layer.draw(painter)
