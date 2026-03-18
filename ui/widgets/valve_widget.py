"""
ui/widgets/valve_widget.py
밸브 위젯 - 클릭 가능한 P&ID 스타일 밸브 표시
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath


class ValveWidget(QWidget):
    """
    P&ID 나비형 밸브 기호를 그리는 커스텀 위젯
    클릭하면 toggled 시그널 발행
    """
    toggled = Signal(bool)  # True=Open, False=Close

    # 색상 상수
    COLOR_OPEN   = QColor("#27ae60")
    COLOR_CLOSED = QColor("#566573")
    COLOR_ERROR  = QColor("#e74c3c")
    COLOR_BORDER = QColor("#a0a0c0")
    COLOR_PIPE   = QColor("#606080")

    def __init__(self, label: str = "VA", parent=None):
        super().__init__(parent)
        self._label = label
        self._is_open = False
        self._is_error = False
        self._enabled_ctrl = True   # 제어 가능 여부

        self.setFixedSize(60, 68)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{label}: {'열림' if self._is_open else '닫힘'}")

    def set_open(self, open_: bool):
        self._is_open = open_
        self.setToolTip(f"{self._label}: {'열림' if open_ else '닫힘'}")
        self.update()

    def set_error(self, error: bool):
        self._is_error = error
        self.update()

    def set_control_enabled(self, enabled: bool):
        self._enabled_ctrl = enabled
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled
            else Qt.CursorShape.ForbiddenCursor
        )

    @property
    def is_open(self) -> bool:
        return self._is_open

    def mousePressEvent(self, event):
        if self._enabled_ctrl and event.button() == Qt.MouseButton.LeftButton:
            new_state = not self._is_open
            self.set_open(new_state)
            self.toggled.emit(new_state)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, (h - 16) // 2  # 라벨 공간 제외한 중앙

        # 밸브 색상 결정
        if self._is_error:
            color = self.COLOR_ERROR
        elif self._is_open:
            color = self.COLOR_OPEN
        else:
            color = self.COLOR_CLOSED

        # 나비/게이트 밸브 기호: 두 개의 삼각형
        size = min(cx, cy) - 4
        painter.setPen(QPen(self.COLOR_BORDER, 1.5))
        painter.setBrush(QBrush(color))

        # 왼쪽 삼각형
        path_l = QPainterPath()
        path_l.moveTo(cx - size, cy - size)
        path_l.lineTo(cx, cy)
        path_l.lineTo(cx - size, cy + size)
        path_l.closeSubpath()

        # 오른쪽 삼각형
        path_r = QPainterPath()
        path_r.moveTo(cx + size, cy - size)
        path_r.lineTo(cx, cy)
        path_r.lineTo(cx + size, cy + size)
        path_r.closeSubpath()

        painter.drawPath(path_l)
        painter.drawPath(path_r)

        # 중앙 점 (닫힘 상태에서 강조)
        dot_color = QColor("#ffffff") if self._is_open else QColor("#e0e0e0")
        painter.setPen(QPen(dot_color, 1))
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(cx - 3, cy - 3, 6, 6)

        # 테두리 박스 (가상의 밸브 바디)
        painter.setPen(QPen(self.COLOR_BORDER, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(cx - size - 2, cy - size - 2,
                         (size + 2) * 2, (size + 2) * 2)

        # 라벨 텍스트
        painter.setPen(QPen(QColor("#2c3e50"), 1))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, h - 16, w, 16),
                         Qt.AlignmentFlag.AlignCenter, self._label)

        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(60, 68)


class SolenoidWidget(ValveWidget):
    """
    솔밸브 위젯 - ValveWidget과 같은 외형, 라벨만 다름
    """

    def __init__(self, label: str = "SOL", parent=None):
        super().__init__(label, parent)
        # 솔밸브는 다이아몬드 모양으로 구분
        self._is_solenoid = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, (h - 16) // 2

        if self._is_error:
            color = self.COLOR_ERROR
        elif self._is_open:
            color = self.COLOR_OPEN
        else:
            color = self.COLOR_CLOSED

        size = min(cx, cy) - 4
        painter.setPen(QPen(self.COLOR_BORDER, 1.5))
        painter.setBrush(QBrush(color))

        # 다이아몬드 (솔밸브 기호)
        path = QPainterPath()
        path.moveTo(cx, cy - size)
        path.lineTo(cx + size, cy)
        path.lineTo(cx, cy + size)
        path.lineTo(cx - size, cy)
        path.closeSubpath()
        painter.drawPath(path)

        # 라벨
        painter.setPen(QPen(QColor("#2c3e50"), 1))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, h - 16, w, 16),
                         Qt.AlignmentFlag.AlignCenter, self._label)

        painter.end()
