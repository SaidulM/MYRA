"""Lightweight native dotted MYRA core.

This is intentionally a small CPU-friendly Qt painter, not a claim that
the full Three.js MALE/FEMALE hologram has already been ported.
"""
import math
import random
import time

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class ParticleOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self._phase = 0.0
        self._last = time.monotonic()
        rng = random.Random(2026)
        self._particles = []
        for _ in range(900):
            theta = rng.uniform(0, math.tau)
            phi = math.acos(rng.uniform(-1, 1))
            radius = 0.72 + rng.random() * 0.28
            self._particles.append((theta, phi, radius, rng.random()))
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        now = time.monotonic()
        self._phase += (now - self._last) * 0.45
        self._last = now
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(3, 10, 16))
        width, height = self.width(), self.height()
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.38
        pulse = 1.0 + math.sin(self._phase * 1.7) * 0.025

        points = []
        for theta, phi, local_radius, seed in self._particles:
            angle = theta + self._phase * (0.55 + seed * 0.15)
            x = math.sin(phi) * math.cos(angle)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(angle)
            wobble = 1.0 + math.sin(self._phase * 2.0 + seed * 10.0) * 0.018
            scale = 0.82 + (z + 1.0) * 0.11
            px = cx + x * radius * local_radius * pulse * wobble
            py = cy + y * radius * local_radius * pulse * wobble
            alpha = int(55 + ((z + 1.0) / 2.0) * 180)
            size = 1.0 + scale * (0.7 + seed)
            points.append((z, px, py, alpha, size))

        painter.setPen(QColor(0, 210, 235, 55))
        painter.drawEllipse(QPointF(cx, cy), radius * 1.08, radius * 1.08)
        for _, px, py, alpha, size in sorted(points):
            painter.setPen(QColor(0, 225, 245, max(20, min(235, alpha))))
            painter.setBrush(QColor(0, 225, 245, max(20, min(235, alpha))))
            painter.drawEllipse(QPointF(px, py), size, size)
