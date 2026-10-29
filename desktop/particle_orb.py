"""Native PySide6 dotted hologram for MYRA.

CORE, MALE and FEMALE are true morphing point clouds rendered by Qt —
no browser, WebEngine, Three.js, command prompt or PowerShell is used.
The busts are smooth chest-up silhouettes with no carved facial features,
no scan ring and no pedestal/statue base.
"""
import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

try:
    from .hologram_geometry import build_point_clouds, interpolate
except ImportError:  # direct module execution during diagnostics
    from hologram_geometry import build_point_clouds, interpolate


THEMES = {
    "normal": (0, 225, 245),
    "friendly": (65, 255, 150),
    "hacker": (255, 55, 75),
}


def _ease(value):
    value = max(0.0, min(1.0, value))
    return 1.0 - (1.0 - value) ** 3


class HologramWidget(QWidget):
    def __init__(self, parent=None, point_count=2800):
        super().__init__(parent)
        self.setMinimumSize(220, 260)
        self.setMouseTracking(True)
        self._clouds, self._samples = build_point_clouds(count=point_count)
        self._form = "core"
        self._from_form = "core"
        self._morph = 1.0
        self._theme = THEMES["normal"]
        self._state = "idle"  # idle | listening | thinking | speaking
        self._phase = 0.0
        self._formation = 0.0
        self._formation_done = False
        self._yaw = -0.28
        self._pitch = 0.05
        self._dragging = False
        self._last_mouse = None
        self._last = time.monotonic()

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # Public controls ----------------------------------------------------
    def set_form(self, form):
        form = str(form or "core").lower()
        if form not in self._clouds or form == self._form:
            return
        # When interrupting a morph, the widget still moves smoothly from
        # the currently displayed target cloud rather than jumping.
        self._from_form = self._form
        self._form = form
        self._morph = 0.0

    def current_form(self):
        return self._form

    def set_theme(self, name):
        self._theme = THEMES.get(str(name or "normal").lower(), THEMES["normal"])
        self.update()

    def set_state(self, state):
        state = str(state or "idle").lower()
        self._state = state if state in {"idle", "listening", "thinking", "speaking"} else "idle"
        self.update()

    # Interaction --------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_mouse is not None:
            delta = event.position() - self._last_mouse
            self._yaw += delta.x() * 0.008
            self._pitch = max(-0.55, min(0.55, self._pitch + delta.y() * 0.006))
            self._last_mouse = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._last_mouse = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _tick(self):
        now = time.monotonic()
        elapsed = max(0.0, min(0.08, now - self._last))
        self._last = now
        speed = {"idle": 0.35, "listening": 0.8, "thinking": 1.05, "speaking": 1.25}[self._state]
        self._phase += elapsed * speed
        if not self._dragging:
            self._yaw += elapsed * 0.10
        if self._morph < 1.0:
            self._morph = min(1.0, self._morph + elapsed / 1.05)
        if not self._formation_done:
            self._formation = min(1.0, self._formation + elapsed / 2.2)
            if self._formation >= 1.0:
                self._formation_done = True
        if self.isVisible():
            self.update()

    def _display_point(self, index):
        source = self._clouds[self._from_form][index]
        target = self._clouds[self._form][index]
        point = interpolate(source, target, _ease(self._morph))
        if not self._formation_done:
            # Formation happens once only.  A bottom-to-top wave brings
            # particles from a small sphere into the first selected form.
            start = self._clouds["core"][index]
            start = (start[0] * 0.28, start[1] * 0.28, start[2] * 0.28)
            delay = (target[1] + 0.95) / 1.9 * 0.58
            local = _ease((self._formation - delay) / 0.42)
            point = interpolate(start, point, local)
        return point

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(2, 8, 14))

        width, height = float(self.width()), float(self.height())
        cx, cy = width / 2.0, height / 2.0
        scale = min(width * 0.55, height * 0.46)
        pulse = 1.0
        if self._state == "speaking":
            pulse += math.sin(self._phase * 5.2) * 0.025
        elif self._state == "listening":
            pulse += math.sin(self._phase * 3.0) * 0.018

        cos_yaw, sin_yaw = math.cos(self._yaw), math.sin(self._yaw)
        cos_pitch, sin_pitch = math.cos(self._pitch), math.sin(self._pitch)
        sweep = ((self._phase * 0.16) % 1.45) - 0.22
        projected = []

        for index, sample in enumerate(self._samples):
            x, y, z = self._display_point(index)
            # Subtle living-particle wobble.
            wobble = 1.0 + math.sin(self._phase * 1.7 + sample["c"] * 11.0) * 0.008
            x, y, z = x * wobble, y * wobble, z * wobble

            rx = x * cos_yaw + z * sin_yaw
            rz = -x * sin_yaw + z * cos_yaw
            ry = y * cos_pitch - rz * sin_pitch
            rz2 = y * sin_pitch + rz * cos_pitch

            perspective = 1.0 / (1.28 - rz2 * 0.24)
            px = cx + rx * scale * pulse * perspective
            py = cy - ry * scale * pulse * perspective
            depth = (rz2 + 1.0) / 2.0
            scan_norm = (y + 0.95) / 1.9
            scan = math.exp(-((scan_norm - sweep) * 6.2) ** 2)
            alpha = 42 + depth * 155 + scan * 58
            if y < -0.68:
                alpha *= max(0.18, 1.0 - ((-0.68 - y) / 0.24) * 0.75)
            if self._state == "thinking":
                alpha *= 0.88 + 0.16 * math.sin(self._phase * 4.0 + sample["a"] * 8.0)
            size = (0.75 + depth * 1.05 + sample["b"] * 0.45) * (0.85 + perspective * 0.35)
            projected.append((rz2, px, py, max(14, min(242, int(alpha))), size))

        # Group by quantized alpha/size.  Creating one pen/brush per dot
        # is wasteful for ~2.8k particles at 30 fps; bucketing keeps the
        # same dotted look while reducing Qt object churn substantially.
        groups = {}
        for _z, px, py, alpha, size in sorted(projected, key=lambda item: item[0]):
            key = (max(0, min(15, alpha // 16)), round(size * 2.0) / 2.0)
            groups.setdefault(key, []).append((px, py))

        red, green, blue = self._theme
        for (alpha_bucket, size), points in groups.items():
            alpha = max(14, min(242, alpha_bucket * 16 + 15))
            color = QColor(red, green, blue, alpha)
            painter.setPen(color)
            painter.setBrush(color)
            for px, py in points:
                painter.drawEllipse(QPointF(px, py), size, size)
        painter.end()


# Backwards-compatible name used by the first native shell.
ParticleOrb = HologramWidget
