"""
ui/widgets/led_widget.py
LED 상태 표시 위젯
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor, QRadialGradient


class LedIndicator(QWidget):
    """원형 LED 표시 위젯"""

    COLORS = {
        "green":  ("#27ae60", "#a9dfbf"),
        "red":    ("#e74c3c", "#f1948a"),
        "orange": ("#e67e22", "#f0b27a"),
        "blue":   ("#2980b9", "#85c1e9"),
        "gray":   ("#566573", "#aab7b8"),
        "yellow": ("#f1c40f", "#f9e79f"),
    }

    def __init__(self, color: str = "green", size: int = 16, parent=None):
        super().__init__(parent)
        self._color_key = color
        self._size = size
        self._on = False
        self.setFixedSize(size, size)

    def set_on(self, on: bool):
        self._on = on
        self.update()

    def set_color(self, color: str):
        self._color_key = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._on:
            base, highlight = self.COLORS.get(self._color_key, self.COLORS["green"])
        else:
            base, highlight = self.COLORS["gray"]

        cx = cy = self._size / 2
        r = self._size / 2 - 1

        grad = QRadialGradient(cx * 0.7, cy * 0.7, r * 0.3, cx, cy, r)
        grad.setColorAt(0, QColor(highlight))
        grad.setColorAt(1, QColor(base))

        painter.setBrush(grad)
        painter.setPen(QColor("#1a1a2e"))
        painter.drawEllipse(1, 1, self._size - 2, self._size - 2)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)


class LedLabel(QWidget):
    """LED + 텍스트 라벨 조합 위젯"""

    def __init__(self, text: str = "", color: str = "green",
                 size: int = 14, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self._led = LedIndicator(color=color, size=size)
        self._label = QLabel(text)
        self._label.setStyleSheet("color: #a0a0c0; font-size: 11px;")

        layout.addWidget(self._led)
        layout.addWidget(self._label)

    def set_on(self, on: bool):
        self._led.set_on(on)

    def set_color(self, color: str):
        self._led.set_color(color)

    def set_text(self, text: str):
        self._label.setText(text)
