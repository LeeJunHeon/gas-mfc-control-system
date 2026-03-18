"""
ui/widgets/mfc_widget.py
MFC 표시 위젯 - PV(현재값), SV(설정값), MAX 표시
라이트 테마 + 산업용 HMI 스타일
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QDoubleSpinBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QMouseEvent


class _ClickableLabel(QLabel):
    """더블클릭 이벤트를 전달하는 QLabel"""
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class MfcWidget(QWidget):
    """
    MFC 한 채널의 상태 표시 위젯

    ┌──────────────────────────┐
    │  Gas Name  (10 ppm)      │
    │  PV: [   21.3 sccm ]    │
    │  SV: [    0.0 sccm ]    │
    │  MAX: 2000  (클릭 편집)  │
    └──────────────────────────┘
    """
    max_changed = Signal(int, float)  # (ch_idx, new_max_sccm)

    def __init__(self, ch_idx: int, name: str = "CH1",
                 full_scale: float = 2000.0, color: str = "#3498db",
                 source_conc_ppm: float | None = None,
                 parent=None):
        super().__init__(parent)
        self._ch_idx = ch_idx
        self._name = name
        self._full_scale = full_scale
        self._color = color
        self._source_conc = source_conc_ppm
        self._pv = 0.0
        self._sv = 0.0

        self._build_ui()
        self.setFixedWidth(160)
        self.setMinimumHeight(90)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # 프레임 외곽 - 흰 배경 + 채널 색상 테두리
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet(
            f"QFrame {{ border: 2px solid {self._color}; "
            f"border-radius: 4px; background-color: #ffffff; }}"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4, 3, 4, 3)
        fl.setSpacing(2)

        # 가스 이름 + 소스 농도 헤더
        header_text = self._name
        if self._source_conc and self._source_conc > 0:
            header_text += f"  ({int(self._source_conc)} ppm)"
        self._lbl_name = QLabel(header_text)
        self._lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_name.setStyleSheet(
            f"color: {self._color}; font-weight: bold; font-size: 11px; "
            "background: transparent; border: none;"
        )
        fl.addWidget(self._lbl_name)

        # PV 행 - 청록 배경
        pv_row = QHBoxLayout()
        pv_row.setSpacing(2)
        lbl_pv_tag = QLabel("PV")
        lbl_pv_tag.setFixedWidth(22)
        lbl_pv_tag.setStyleSheet(
            "color: #0e6655; font-size: 10px; font-weight: bold; "
            "border: none; background: transparent;")
        self._lbl_pv = QLabel("0.0")
        self._lbl_pv.setMinimumWidth(80)
        self._lbl_pv.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_pv.setStyleSheet(
            "background: #d1f2eb; color: #0e6655; font-weight: bold; "
            "font-size: 12px; font-family: Consolas, monospace; "
            "border: 1px solid #a3e4d7; border-radius: 2px; padding: 1px 3px;")
        lbl_unit1 = QLabel("sccm")
        lbl_unit1.setStyleSheet(
            "color: #7f8c8d; font-size: 9px; border: none; background: transparent;")
        pv_row.addWidget(lbl_pv_tag)
        pv_row.addWidget(self._lbl_pv, stretch=1)
        pv_row.addWidget(lbl_unit1)
        fl.addLayout(pv_row)

        # SV 행 - 주황 배경
        sv_row = QHBoxLayout()
        sv_row.setSpacing(2)
        lbl_sv_tag = QLabel("SV")
        lbl_sv_tag.setFixedWidth(22)
        lbl_sv_tag.setStyleSheet(
            "color: #935116; font-size: 10px; font-weight: bold; "
            "border: none; background: transparent;")
        self._lbl_sv = QLabel("0.0")
        self._lbl_sv.setMinimumWidth(80)
        self._lbl_sv.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_sv.setStyleSheet(
            "background: #fdebd0; color: #935116; font-weight: bold; "
            "font-size: 12px; font-family: Consolas, monospace; "
            "border: 1px solid #f0b27a; border-radius: 2px; padding: 1px 3px;")
        lbl_unit2 = QLabel("sccm")
        lbl_unit2.setStyleSheet(
            "color: #7f8c8d; font-size: 9px; border: none; background: transparent;")
        sv_row.addWidget(lbl_sv_tag)
        sv_row.addWidget(self._lbl_sv, stretch=1)
        sv_row.addWidget(lbl_unit2)
        fl.addLayout(sv_row)

        # MAX 행 - 빨간 글씨, 더블클릭 편집
        max_row = QHBoxLayout()
        max_row.setSpacing(2)
        lbl_max_tag = QLabel("MAX")
        lbl_max_tag.setStyleSheet(
            "color: #e74c3c; font-size: 9px; font-weight: bold; "
            "border: none; background: transparent;")
        self._lbl_max = _ClickableLabel(f"{self._full_scale:.0f}")
        self._lbl_max.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_max.setStyleSheet(
            "color: #e74c3c; font-size: 10px; font-weight: bold; "
            "border: none; background: transparent; "
            "text-decoration: underline;")
        self._lbl_max.setToolTip("더블클릭으로 MAX 값 변경")
        self._lbl_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_max.double_clicked.connect(self._on_max_dblclick)
        lbl_max_unit = QLabel("sccm")
        lbl_max_unit.setStyleSheet(
            "color: #7f8c8d; font-size: 9px; border: none; background: transparent;")
        max_row.addWidget(lbl_max_tag)
        max_row.addWidget(self._lbl_max, stretch=1)
        max_row.addWidget(lbl_max_unit)
        fl.addLayout(max_row)

        root.addWidget(frame)

    def _on_max_dblclick(self):
        value, ok = QInputDialog.getDouble(
            self, "MAX 변경",
            f"{self._name} Full Scale (sccm):",
            self._full_scale, 0.1, 100000.0, 1)
        if ok:
            self._full_scale = value
            self._lbl_max.setText(f"{value:.0f}")
            self.max_changed.emit(self._ch_idx, value)

    # ── 공개 API ──────────────────────────────────────

    def set_pv(self, pv_sccm: float):
        self._pv = pv_sccm
        self._lbl_pv.setText(f"{pv_sccm:.1f}")

    def set_sv(self, sv_sccm: float):
        self._sv = sv_sccm
        self._lbl_sv.setText(f"{sv_sccm:.1f}")

    def set_name(self, name: str):
        self._name = name
        header = name
        if self._source_conc and self._source_conc > 0:
            header += f"  ({int(self._source_conc)} ppm)"
        self._lbl_name.setText(header)

    def set_source_conc(self, ppm: float | None):
        self._source_conc = ppm
        self.set_name(self._name)

    def set_full_scale(self, fs: float):
        self._full_scale = fs
        self._lbl_max.setText(f"{fs:.0f}")

    def set_enabled_display(self, enabled: bool):
        """채널 비활성화 시 회색 처리"""
        self.setEnabled(enabled)

    @property
    def full_scale(self) -> float:
        return self._full_scale

    def sizeHint(self) -> QSize:
        return QSize(160, 92)
