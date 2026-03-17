"""
ui/widgets/mfc_widget.py
MFC 표시 위젯 - PV(현재값), SV(설정값), MAX 표시
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QDoubleSpinBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont


class MfcWidget(QWidget):
    """
    MFC 한 채널의 상태 표시 위젯

    ┌──────────────────────────┐
    │  [Gas Name]              │
    │  PV: [   21.3 sccm ]    │
    │  SV: [    0.0 sccm ]    │
    │  MAX: 2000               │
    └──────────────────────────┘
    """
    max_changed = Signal(int, float)  # (ch_idx, new_max_sccm) - MAX 수동 변경 시

    def __init__(self, ch_idx: int, name: str = "CH1",
                 full_scale: float = 2000.0, color: str = "#3498db",
                 parent=None):
        super().__init__(parent)
        self._ch_idx = ch_idx
        self._name = name
        self._full_scale = full_scale
        self._color = color
        self._pv = 0.0
        self._sv = 0.0

        self._build_ui()
        self.setFixedWidth(160)
        self.setMinimumHeight(90)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(2)

        # 프레임 외곽
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet(
            f"QFrame {{ border: 2px solid {self._color}; "
            f"border-radius: 4px; background-color: #0a0a1e; }}"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4, 3, 4, 3)
        fl.setSpacing(2)

        # 가스 이름 헤더
        self._lbl_name = QLabel(self._name)
        self._lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_name.setStyleSheet(
            f"color: {self._color}; font-weight: bold; font-size: 11px; "
            "background: transparent; border: none;"
        )
        fl.addWidget(self._lbl_name)

        # PV 행
        pv_row = QHBoxLayout()
        lbl_pv_tag = QLabel("PV")
        lbl_pv_tag.setFixedWidth(22)
        lbl_pv_tag.setStyleSheet(
            "color: #00ffee; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        self._lbl_pv = QLabel("0.0")
        self._lbl_pv.setObjectName("label_pv")
        self._lbl_pv.setMinimumWidth(80)
        self._lbl_pv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_unit1 = QLabel("sccm")
        lbl_unit1.setStyleSheet("color: #a0a0c0; font-size: 9px; border: none; background: transparent;")
        pv_row.addWidget(lbl_pv_tag)
        pv_row.addWidget(self._lbl_pv)
        pv_row.addWidget(lbl_unit1)
        fl.addLayout(pv_row)

        # SV 행
        sv_row = QHBoxLayout()
        lbl_sv_tag = QLabel("SV")
        lbl_sv_tag.setFixedWidth(22)
        lbl_sv_tag.setStyleSheet(
            "color: #ffcc00; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        self._lbl_sv = QLabel("0.0")
        self._lbl_sv.setObjectName("label_sv")
        self._lbl_sv.setMinimumWidth(80)
        self._lbl_sv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_unit2 = QLabel("sccm")
        lbl_unit2.setStyleSheet("color: #a0a0c0; font-size: 9px; border: none; background: transparent;")
        sv_row.addWidget(lbl_sv_tag)
        sv_row.addWidget(self._lbl_sv)
        sv_row.addWidget(lbl_unit2)
        fl.addLayout(sv_row)

        # MAX 행 (편집 가능)
        max_row = QHBoxLayout()
        lbl_max_tag = QLabel("MAX")
        lbl_max_tag.setStyleSheet(
            "color: #e74c3c; font-size: 9px; font-weight: bold; border: none; background: transparent;")
        self._spin_max = QDoubleSpinBox()
        self._spin_max.setRange(0.1, 100000)
        self._spin_max.setValue(self._full_scale)
        self._spin_max.setDecimals(1)
        self._spin_max.setSuffix(" sccm")
        self._spin_max.setFixedWidth(100)
        self._spin_max.setStyleSheet(
            "font-size: 9px; color: #e74c3c; background: #1a1a2e; "
            "border: 1px solid #e74c3c; padding: 1px;")
        self._spin_max.valueChanged.connect(self._on_max_changed)
        max_row.addWidget(lbl_max_tag)
        max_row.addWidget(self._spin_max)
        fl.addLayout(max_row)

        root.addWidget(frame)

    def _on_max_changed(self, value: float):
        self._full_scale = value
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
        self._lbl_name.setText(name)

    def set_full_scale(self, fs: float):
        self._full_scale = fs
        self._spin_max.blockSignals(True)
        self._spin_max.setValue(fs)
        self._spin_max.blockSignals(False)

    def set_enabled_display(self, enabled: bool):
        """채널 비활성화 시 회색 처리"""
        alpha = "ff" if enabled else "40"
        self.setStyleSheet(f"opacity: {'1' if enabled else '0.3'};")
        self.setEnabled(enabled)

    @property
    def full_scale(self) -> float:
        return self._full_scale

    def sizeHint(self) -> QSize:
        return QSize(160, 92)
