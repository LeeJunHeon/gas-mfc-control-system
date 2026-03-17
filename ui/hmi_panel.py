"""
ui/hmi_panel.py
메인 HMI 패널 - 가스 라인 다이어그램 (밸브 + MFC + 4-way)

참고 이미지와 동일한 구조:
  [Gas label] — [VA valve] — [MFC widget] — [SOL valve] — (line) →
                                                               └→ [4-way valve]
"""
from __future__ import annotations
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QCheckBox, QGroupBox, QPushButton,
    QSizePolicy, QSpacerItem, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen

from app.models import ChannelConfig, FourWayPosition
from services.device_service import DeviceService
from ui.widgets.valve_widget import ValveWidget, SolenoidWidget
from ui.widgets.mfc_widget import MfcWidget
from ui.widgets.led_widget import LedLabel, LedIndicator

logger = logging.getLogger(__name__)

PV_UPDATE_INTERVAL_MS = 1000   # PV 갱신 주기 (ms)


class ChannelRow(QWidget):
    """가스 채널 한 행 위젯"""

    va_toggled  = Signal(int, bool)   # (ch_idx, open)
    sol_toggled = Signal(int, bool)
    max_changed = Signal(int, float)  # (ch_idx, new_fs)
    enabled_changed = Signal(int, bool)

    def __init__(self, ch: ChannelConfig, parent=None):
        super().__init__(parent)
        self._ch = ch
        self._control_enabled = True
        self._build_ui()

    def _build_ui(self):
        ch = self._ch
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)

        # ── 활성화 체크박스 ───────────────
        self._chk_enable = QCheckBox()
        self._chk_enable.setChecked(ch.enabled)
        self._chk_enable.setToolTip("채널 활성화/비활성화")
        self._chk_enable.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self._chk_enable)

        # ── 가스 이름 라벨 ────────────────
        self._lbl_name = QLabel(ch.name)
        self._lbl_name.setFixedWidth(55)
        self._lbl_name.setStyleSheet(
            f"color: {ch.color}; font-weight: bold; font-size: 12px;")
        self._lbl_name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._lbl_name)

        # ── 파이프 선 (좌측) ──────────────
        layout.addWidget(self._make_pipe(ch.color, 30))

        # ── VA 밸브 ──────────────────────
        self._va = ValveWidget(f"VA{ch.idx + 1}")
        self._va.toggled.connect(lambda s: self.va_toggled.emit(ch.idx, s))
        layout.addWidget(self._va)

        # ── 파이프 선 ─────────────────────
        layout.addWidget(self._make_pipe(ch.color, 15))

        # ── MFC 위젯 ─────────────────────
        self._mfc = MfcWidget(
            ch_idx=ch.idx,
            name=ch.name,
            full_scale=ch.full_scale_sccm,
            color=ch.color,
        )
        self._mfc.max_changed.connect(self.max_changed)
        layout.addWidget(self._mfc)

        # ── 파이프 선 ─────────────────────
        layout.addWidget(self._make_pipe(ch.color, 15))

        # ── 솔밸브 ──────────────────────
        self._sol = SolenoidWidget(f"S{ch.idx + 1}")
        self._sol.toggled.connect(lambda s: self.sol_toggled.emit(ch.idx, s))
        layout.addWidget(self._sol)

        # ── 파이프 선 (우측, 4-way로 연결) ─
        layout.addWidget(self._make_pipe(ch.color, 40))
        layout.addStretch(1)

        # 비활성 시 전체 Row 흐리게
        if not ch.enabled:
            self._set_row_enabled(False)

    @staticmethod
    def _make_pipe(color: str, width: int) -> QLabel:
        lbl = QLabel()
        lbl.setFixedSize(width, 6)
        lbl.setStyleSheet(
            f"background-color: {color}; border-radius: 3px;")
        return lbl

    def _on_enable_changed(self, state):
        enabled = (state == Qt.CheckState.Checked.value)
        self._set_row_enabled(enabled)
        self.enabled_changed.emit(self._ch.idx, enabled)

    def _set_row_enabled(self, enabled: bool):
        for w in [self._lbl_name, self._va, self._mfc, self._sol]:
            w.setEnabled(enabled)
        opacity = "1.0" if enabled else "0.35"
        # VA, SOL 제어도 잠금
        self._va.set_control_enabled(enabled and self._control_enabled)
        self._sol.set_control_enabled(enabled and self._control_enabled)

    def lock_control(self, lock: bool):
        """레시피 실행 중 수동 조작 잠금"""
        self._control_enabled = not lock
        self._va.set_control_enabled(not lock and self._ch.enabled)
        self._sol.set_control_enabled(not lock and self._ch.enabled)

    # ── 데이터 업데이트 ────────────────────────────────

    def update_pv(self, pv_sccm: float):
        self._mfc.set_pv(pv_sccm)

    def update_sv(self, sv_sccm: float):
        self._mfc.set_sv(sv_sccm)

    def update_va_state(self, open_: bool):
        self._va.set_open(open_)

    def update_sol_state(self, open_: bool):
        self._sol.set_open(open_)

    def update_channel_config(self, ch: ChannelConfig):
        self._ch = ch
        self._lbl_name.setText(ch.name)
        self._mfc.set_name(ch.name)
        self._mfc.set_full_scale(ch.full_scale_sccm)


class FourWayWidget(QWidget):
    """4-way 밸브 표시 위젯"""

    toggled = Signal(str)  # "vent" | "chamber"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._position = FourWayPosition.VENT
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        frame = QGroupBox("4-way Valve")
        fl = QVBoxLayout(frame)

        self._btn_vent = QPushButton("● VENT")
        self._btn_vent.setCheckable(True)
        self._btn_vent.setChecked(True)
        self._btn_vent.clicked.connect(lambda: self._switch("vent"))

        self._btn_chamber = QPushButton("○ CHAMBER")
        self._btn_chamber.setCheckable(True)
        self._btn_chamber.clicked.connect(lambda: self._switch("chamber"))

        for btn in [self._btn_vent, self._btn_chamber]:
            btn.setStyleSheet(
                "QPushButton:checked { background-color: #196f3d; border: 2px solid #27ae60; "
                "color: #aaffaa; font-weight: bold; }"
            )
            fl.addWidget(btn)

        self._lbl_status = QLabel("현재: VENT")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setStyleSheet("color: #a0c0ff; font-size: 11px;")
        fl.addWidget(self._lbl_status)

        layout.addWidget(frame)
        self.setFixedWidth(140)

    def _switch(self, pos: str):
        self._btn_vent.setChecked(pos == "vent")
        self._btn_chamber.setChecked(pos == "chamber")
        self._btn_vent.setText("● VENT" if pos == "vent" else "○ VENT")
        self._btn_chamber.setText("● CHAMBER" if pos == "chamber" else "○ CHAMBER")
        self._lbl_status.setText(f"현재: {pos.upper()}")
        self._position = FourWayPosition.VENT if pos == "vent" else FourWayPosition.CHAMBER
        self.toggled.emit(pos)

    def set_position(self, pos: str):
        self._switch(pos)

    def lock_control(self, lock: bool):
        self._btn_vent.setEnabled(not lock)
        self._btn_chamber.setEnabled(not lock)


class HmiPanel(QWidget):
    """메인 HMI 패널"""

    # 수동 조작 시그널 → DeviceService로 전달
    va_toggle_requested   = Signal(int, bool)
    sol_toggle_requested  = Signal(int, bool)
    fourway_change_requested = Signal(str)
    channel_max_changed   = Signal(int, float)
    channel_enabled_changed = Signal(int, bool)

    def __init__(self, channels: list[ChannelConfig],
                 device: DeviceService, parent=None):
        super().__init__(parent)
        self._channels = channels
        self._device = device
        self._rows: dict[int, ChannelRow] = {}
        self._locked = False

        self._build_ui()
        self._start_pv_timer()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 제목 ─────────────────────────────────────
        title_row = QHBoxLayout()
        lbl_title = QLabel("GAS Control — HMI")
        lbl_title.setObjectName("label_title")
        title_row.addWidget(lbl_title)
        title_row.addStretch(1)

        self._led_hw = LedLabel("HW 연결", color="orange")
        self._led_hw.set_on(True)
        self._led_hw.set_color("orange")
        title_row.addWidget(self._led_hw)
        root.addLayout(title_row)

        # ── 채널 구분 라벨 ───────────────────────────
        lbl_air = QLabel("─── Air Lines ──────────────────────────────────────")
        lbl_air.setStyleSheet("color: #3498db; font-size: 10px;")
        root.addWidget(lbl_air)

        # ── Air 채널 (0-3) ───────────────────────────
        for ch in self._channels[:4]:
            row = ChannelRow(ch)
            row.va_toggled.connect(self._on_va_toggle)
            row.sol_toggled.connect(self._on_sol_toggle)
            row.max_changed.connect(self.channel_max_changed)
            row.enabled_changed.connect(self.channel_enabled_changed)
            self._rows[ch.idx] = row
            root.addWidget(row)

        lbl_gas = QLabel("─── Gas Lines ──────────────────────────────────────")
        lbl_gas.setStyleSheet("color: #e74c3c; font-size: 10px;")
        root.addWidget(lbl_gas)

        # ── Gas 채널 (4-7) ───────────────────────────
        for ch in self._channels[4:]:
            row = ChannelRow(ch)
            row.va_toggled.connect(self._on_va_toggle)
            row.sol_toggled.connect(self._on_sol_toggle)
            row.max_changed.connect(self.channel_max_changed)
            row.enabled_changed.connect(self.channel_enabled_changed)
            self._rows[ch.idx] = row
            root.addWidget(row)

        # ── 4-way 밸브 + 제어 버튼 ──────────────────
        bottom_row = QHBoxLayout()

        self._fourway = FourWayWidget()
        self._fourway.toggled.connect(self.fourway_change_requested)
        bottom_row.addWidget(self._fourway)

        bottom_row.addStretch(1)

        # 우측 빠른 버튼
        btn_panel = QVBoxLayout()
        self._btn_all_open = QPushButton("전체 VA Open")
        self._btn_all_open.clicked.connect(self._open_all_va)
        self._btn_all_close = QPushButton("전체 닫기")
        self._btn_all_close.clicked.connect(self._close_all)
        for btn in [self._btn_all_open, self._btn_all_close]:
            btn.setMaximumWidth(140)
            btn_panel.addWidget(btn)
        btn_panel.addStretch(1)
        bottom_row.addLayout(btn_panel)

        root.addLayout(bottom_row)
        root.addStretch(1)

    def _start_pv_timer(self):
        """주기적 PV 읽기 타이머"""
        self._pv_timer = QTimer(self)
        self._pv_timer.timeout.connect(self._refresh_pv)
        self._pv_timer.start(PV_UPDATE_INTERVAL_MS)

    def _refresh_pv(self):
        """DeviceService에서 PV 읽어서 UI 업데이트 (엔진 미실행 시)"""
        if self._locked:
            return   # 레시피 실행 중엔 엔진이 시그널로 업데이트
        try:
            pvs = self._device.read_all_pv()
            for ch_idx, pv in pvs.items():
                if ch_idx in self._rows:
                    self._rows[ch_idx].update_pv(pv)
            # 밸브 상태도 갱신
            for ch in self._channels:
                if ch.idx in self._rows:
                    self._rows[ch.idx].update_va_state(
                        self._device.get_va_state(ch.idx))
                    self._rows[ch.idx].update_sol_state(
                        self._device.get_sol_state(ch.idx))
            # 4-way
            fw = self._device.get_fourway()
            self._fourway.set_position(fw.value.lower())
        except Exception as e:
            logger.debug(f"PV 갱신 오류: {e}")

    # ── 수동 밸브 제어 ────────────────────────────────

    def _on_va_toggle(self, ch_idx: int, open_: bool):
        if self._locked:
            return
        try:
            actual = self._device.toggle_va_valve(ch_idx)
            if ch_idx in self._rows:
                self._rows[ch_idx].update_va_state(actual)
        except Exception as e:
            logger.error(f"VA 밸브 제어 오류: {e}")

    def _on_sol_toggle(self, ch_idx: int, open_: bool):
        if self._locked:
            return
        try:
            actual = self._device.toggle_sol_valve(ch_idx)
            if ch_idx in self._rows:
                self._rows[ch_idx].update_sol_state(actual)
        except Exception as e:
            logger.error(f"Sol 밸브 제어 오류: {e}")

    def _open_all_va(self):
        if self._locked:
            return
        for ch in self._channels:
            if ch.enabled:
                self._device.toggle_va_valve(ch.idx)

    def _close_all(self):
        if self._locked:
            return
        self._device.close_all_channels()

    # ── 엔진 시그널 수신 ──────────────────────────────

    def on_pv_updated(self, pv_dict: dict):
        """RecipeEngine에서 PV 업데이트"""
        for ch_idx, pv in pv_dict.items():
            if ch_idx in self._rows:
                self._rows[ch_idx].update_pv(pv)

    def on_sv_updated(self, sv_dict: dict):
        """RecipeEngine에서 SV 업데이트"""
        for ch_idx, sv in sv_dict.items():
            if ch_idx in self._rows:
                self._rows[ch_idx].update_sv(sv)

    def lock(self, lock: bool):
        """레시피 실행 중 수동 조작 잠금"""
        self._locked = lock
        for row in self._rows.values():
            row.lock_control(lock)
        self._fourway.lock_control(lock)
        self._btn_all_open.setEnabled(not lock)
        self._btn_all_close.setEnabled(not lock)

    def refresh_channels(self, channels: list[ChannelConfig]):
        """설정 변경 후 채널 목록 반영"""
        self._channels = channels
        for ch in channels:
            if ch.idx in self._rows:
                self._rows[ch.idx].update_channel_config(ch)

    def set_hw_connected(self, connected: bool):
        if connected:
            self._led_hw.set_color("green")
            self._led_hw.set_text("HW 연결됨")
        else:
            self._led_hw.set_color("red")
            self._led_hw.set_text("HW 미연결")
        self._led_hw.set_on(connected)
