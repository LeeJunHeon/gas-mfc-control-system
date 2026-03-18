"""
ui/hmi_panel.py
메인 HMI 패널 - 가스 라인 P&ID 다이어그램

레이아웃:
  [✓] [Gas] ─ [VA] ─ [MFC] ─ [SOL] ────┐
  [✓] [Gas] ─ [VA] ─ [MFC] ─ [SOL] ────┤  ← 세로 합류 파이프
  ...                                    ┤
  [✓] [Gas] ─ [VA] ─ [MFC] ─ [SOL] ────┘
                                         │
                                    [4-way Valve]
                                    [전체VA Open]
                                    [ 전체 닫기 ]
"""
from __future__ import annotations
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QCheckBox, QGroupBox, QPushButton,
    QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen

from app.models import ChannelConfig, FourWayPosition
from services.device_service import DeviceService
from ui.widgets.valve_widget import ValveWidget, SolenoidWidget
from ui.widgets.mfc_widget import MfcWidget
from ui.widgets.led_widget import LedLabel, LedIndicator

logger = logging.getLogger(__name__)

PV_UPDATE_INTERVAL_MS = 1000
CHANNEL_ROW_HEIGHT = 80


# ═══════════════════════════════════════════════════════
#  ChannelRow - 가스 채널 한 행
# ═══════════════════════════════════════════════════════

class ChannelRow(QWidget):
    """가스 채널 한 행: [체크] [이름] ─ [VA] ─ [MFC] ─ [SOL] ─ (파이프→)"""

    va_toggled       = Signal(int, bool)
    sol_toggled      = Signal(int, bool)
    max_changed      = Signal(int, float)
    enabled_changed  = Signal(int, bool)

    def __init__(self, ch: ChannelConfig, parent=None):
        super().__init__(parent)
        self._ch = ch
        self._control_enabled = True
        self.setFixedHeight(CHANNEL_ROW_HEIGHT)
        self._build_ui()

    def _build_ui(self):
        ch = self._ch
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 0, 2)
        layout.setSpacing(4)

        # ── 체크박스 ─────────────────────
        self._chk_enable = QCheckBox()
        self._chk_enable.setChecked(ch.enabled)
        self._chk_enable.setToolTip("채널 활성화/비활성화")
        self._chk_enable.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self._chk_enable)

        # ── 가스 이름 (50px) ─────────────
        self._lbl_name = QLabel(ch.name)
        self._lbl_name.setFixedWidth(50)
        self._lbl_name.setStyleSheet(
            f"color: {ch.color}; font-weight: bold; font-size: 12px;")
        self._lbl_name.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._lbl_name)

        # ── 수평 파이프 → VA ─────────────
        layout.addWidget(self._make_pipe(ch.color, 20))

        # ── VA 밸브 ──────────────────────
        self._va = ValveWidget(f"VA{ch.idx + 1}")
        self._va.toggled.connect(lambda s: self.va_toggled.emit(ch.idx, s))
        layout.addWidget(self._va)

        # ── 파이프 → MFC ─────────────────
        layout.addWidget(self._make_pipe(ch.color, 10))

        # ── MFC 위젯 ─────────────────────
        self._mfc = MfcWidget(
            ch_idx=ch.idx,
            name=ch.name,
            full_scale=ch.full_scale_sccm,
            color=ch.color,
            source_conc_ppm=ch.source_conc_ppm,
        )
        self._mfc.max_changed.connect(self.max_changed)
        layout.addWidget(self._mfc)

        # ── 파이프 → SOL ─────────────────
        layout.addWidget(self._make_pipe(ch.color, 10))

        # ── 솔밸브 ──────────────────────
        self._sol = SolenoidWidget(f"S{ch.idx + 1}")
        self._sol.toggled.connect(lambda s: self.sol_toggled.emit(ch.idx, s))
        layout.addWidget(self._sol)

        # ── 파이프 → 합류 (stretch으로 우측 끝까지) ─
        self._pipe_tail = self._make_pipe(ch.color, 0)
        self._pipe_tail.setMinimumWidth(16)
        layout.addWidget(self._pipe_tail, stretch=1)

        # opacity effect (비활성용)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        if not ch.enabled:
            self._set_row_enabled(False)

    @staticmethod
    def _make_pipe(color: str, width: int) -> QLabel:
        lbl = QLabel()
        if width > 0:
            lbl.setFixedSize(width, 4)
        else:
            lbl.setFixedHeight(4)
        lbl.setStyleSheet(
            f"background-color: {color}; border-radius: 2px;")
        return lbl

    def _on_enable_changed(self, state):
        enabled = (state == Qt.CheckState.Checked.value)
        self._set_row_enabled(enabled)
        self.enabled_changed.emit(self._ch.idx, enabled)

    def _set_row_enabled(self, enabled: bool):
        self._opacity.setOpacity(1.0 if enabled else 0.4)
        for w in [self._lbl_name, self._va, self._mfc, self._sol]:
            w.setEnabled(enabled)
        self._va.set_control_enabled(enabled and self._control_enabled)
        self._sol.set_control_enabled(enabled and self._control_enabled)

    def lock_control(self, lock: bool):
        self._control_enabled = not lock
        self._va.set_control_enabled(not lock and self._ch.enabled)
        self._sol.set_control_enabled(not lock and self._ch.enabled)

    # ── 데이터 업데이트 ───────────────────────────

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
        self._mfc.set_source_conc(ch.source_conc_ppm)
        self._mfc.set_full_scale(ch.full_scale_sccm)


# ═══════════════════════════════════════════════════════
#  MergePipe - 세로 합류 파이프 커스텀 위젯
# ═══════════════════════════════════════════════════════

class MergePipeWidget(QWidget):
    """
    채널 Row 우측에서 세로로 합류하는 파이프를 그리는 위젯.
    각 Row의 Y 중앙에서 가지(branch)가 들어오고,
    맨 아래에서 수평으로 빠져나가는 구조.
    """
    PIPE_COLOR = QColor("#7f8c8d")
    PIPE_WIDTH = 4

    def __init__(self, n_branches: int, row_height: int,
                 section_header_height: int = 22, parent=None):
        super().__init__(parent)
        self._n_branches = n_branches
        self._row_height = row_height
        self._section_hdr_h = section_header_height
        self.setFixedWidth(20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.PIPE_COLOR, self.PIPE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        w = self.width()
        cx = w // 2   # 세로 파이프 x 위치

        # 각 branch의 Y 좌표 계산
        branch_ys = []
        y = 0
        for i in range(self._n_branches):
            # Air Lines 헤더 후 4개, Gas Lines 헤더 후 나머지
            if i == 0:
                y += self._section_hdr_h   # "Air Lines" 헤더
            elif i == 4:
                y += self._section_hdr_h   # "Gas Lines" 헤더
            row_center_y = y + self._row_height // 2
            branch_ys.append(row_center_y)
            y += self._row_height

        if not branch_ys:
            painter.end()
            return

        y_top = branch_ys[0]
        y_bot = branch_ys[-1]

        # 세로 메인 파이프
        painter.drawLine(cx, y_top, cx, y_bot + 30)

        # 각 branch → 세로 파이프 (왼쪽에서 들어옴)
        for by in branch_ys:
            painter.drawLine(0, by, cx, by)

        # 아래쪽으로 나가는 수평 파이프 (4-way 연결)
        bottom_y = y_bot + 30
        painter.drawLine(cx, bottom_y, cx, bottom_y + 16)

        painter.end()


# ═══════════════════════════════════════════════════════
#  FourWayWidget - 4-way 밸브
# ═══════════════════════════════════════════════════════

class FourWayWidget(QWidget):
    """4-way 밸브 표시 위젯"""

    toggled = Signal(str)  # "vent" | "chamber"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._position = FourWayPosition.VENT
        self.setFixedWidth(150)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        frame = QGroupBox("4-way Valve")
        frame.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 11px; }")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(6, 18, 6, 6)
        fl.setSpacing(6)

        self._btn_vent = QPushButton("● VENT")
        self._btn_vent.setCheckable(True)
        self._btn_vent.setChecked(True)
        self._btn_vent.setFixedHeight(34)
        self._btn_vent.clicked.connect(lambda: self._switch("vent"))

        self._btn_chamber = QPushButton("○ CHAMBER")
        self._btn_chamber.setCheckable(True)
        self._btn_chamber.setFixedHeight(34)
        self._btn_chamber.clicked.connect(lambda: self._switch("chamber"))

        for btn in [self._btn_vent, self._btn_chamber]:
            btn.setStyleSheet(
                "QPushButton { font-weight: bold; font-size: 11px; }"
                "QPushButton:checked { background-color: #27ae60; "
                "border: 2px solid #229954; color: white; }"
            )
            fl.addWidget(btn)

        self._lbl_status = QLabel("현재: VENT")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setStyleSheet(
            "color: #2980b9; font-size: 11px; font-weight: bold;")
        fl.addWidget(self._lbl_status)

        layout.addWidget(frame)

    def _switch(self, pos: str):
        self._btn_vent.setChecked(pos == "vent")
        self._btn_chamber.setChecked(pos == "chamber")
        self._btn_vent.setText("● VENT" if pos == "vent" else "○ VENT")
        self._btn_chamber.setText(
            "● CHAMBER" if pos == "chamber" else "○ CHAMBER")
        self._lbl_status.setText(f"현재: {pos.upper()}")
        self._position = (FourWayPosition.VENT
                          if pos == "vent" else FourWayPosition.CHAMBER)
        self.toggled.emit(pos)

    def set_position(self, pos: str):
        self._switch(pos)

    def lock_control(self, lock: bool):
        self._btn_vent.setEnabled(not lock)
        self._btn_chamber.setEnabled(not lock)


# ═══════════════════════════════════════════════════════
#  HmiPanel - 메인 HMI 패널
# ═══════════════════════════════════════════════════════

class HmiPanel(QWidget):
    """메인 HMI 패널 - P&ID 구조 + QScrollArea"""

    va_toggle_requested      = Signal(int, bool)
    sol_toggle_requested     = Signal(int, bool)
    fourway_change_requested = Signal(str)
    channel_max_changed      = Signal(int, float)
    channel_enabled_changed  = Signal(int, bool)

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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        # ── 제목 행 ─────────────────────────────────
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
        root.addSpacing(6)

        # ═══════════════════════════════════════════════
        # P&ID 메인 영역: [채널 Rows] [합류파이프] [우측 패널]
        # ═══════════════════════════════════════════════
        main_h = QHBoxLayout()
        main_h.setSpacing(0)

        # ── 좌측: 채널 Row 목록 ────────────────────
        ch_panel = QWidget()
        ch_layout = QVBoxLayout(ch_panel)
        ch_layout.setContentsMargins(0, 0, 0, 0)
        ch_layout.setSpacing(0)

        # Section header 높이 (파이프 Y 계산에도 사용)
        SECTION_HDR_H = 22

        # Air Lines 헤더
        lbl_air = self._make_section_label(
            "── Air Lines ──", "#2980b9", SECTION_HDR_H)
        ch_layout.addWidget(lbl_air)

        for ch in self._channels[:4]:
            row = self._make_channel_row(ch)
            ch_layout.addWidget(row)

        # Gas Lines 헤더
        lbl_gas = self._make_section_label(
            "── Gas Lines ──", "#e74c3c", SECTION_HDR_H)
        ch_layout.addWidget(lbl_gas)

        for ch in self._channels[4:]:
            row = self._make_channel_row(ch)
            ch_layout.addWidget(row)

        ch_layout.addStretch(1)
        main_h.addWidget(ch_panel, stretch=1)

        # ── 중앙: 세로 합류 파이프 ────────────────
        n_ch = len(self._channels)
        self._merge_pipe = MergePipeWidget(
            n_branches=n_ch,
            row_height=CHANNEL_ROW_HEIGHT,
            section_header_height=SECTION_HDR_H,
        )
        main_h.addWidget(self._merge_pipe)

        # ── 우측: 4-way + 컨트롤 ──────────────────
        right_panel = QWidget()
        right_panel.setFixedWidth(160)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        # 세로 파이프가 끝나는 지점까지 spacer로 정렬
        # (Air헤더 + 4 rows + Gas헤더 + 4 rows = 약 전체 높이의 끝)
        pipe_visual_height = (
            SECTION_HDR_H + CHANNEL_ROW_HEIGHT * 4
            + SECTION_HDR_H + CHANNEL_ROW_HEIGHT * (n_ch - 4)
        )
        right_layout.addSpacing(pipe_visual_height - 30)

        # 수평 연결 라벨
        pipe_h_label = QLabel("─── →")
        pipe_h_label.setStyleSheet(
            "color: #7f8c8d; font-size: 14px; font-weight: bold;")
        pipe_h_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        right_layout.addWidget(pipe_h_label)

        # 4-way 밸브
        self._fourway = FourWayWidget()
        self._fourway.toggled.connect(self.fourway_change_requested)
        right_layout.addWidget(self._fourway)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #bdc3c7;")
        right_layout.addWidget(sep)

        # 빠른 버튼
        self._btn_all_open = QPushButton("전체 VA Open")
        self._btn_all_open.setFixedHeight(32)
        self._btn_all_open.setStyleSheet(
            "background: #ffffff; border: 1px solid #bdc3c7; "
            "border-radius: 4px; font-weight: bold;")
        self._btn_all_open.clicked.connect(self._open_all_va)

        self._btn_all_close = QPushButton("전체 닫기")
        self._btn_all_close.setFixedHeight(32)
        self._btn_all_close.setStyleSheet(
            "background: #ffffff; border: 1px solid #bdc3c7; "
            "border-radius: 4px; font-weight: bold;")
        self._btn_all_close.clicked.connect(self._close_all)

        right_layout.addWidget(self._btn_all_open)
        right_layout.addWidget(self._btn_all_close)
        right_layout.addStretch(1)
        main_h.addWidget(right_panel)

        root.addLayout(main_h, stretch=1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── 빌더 헬퍼 ──────────────────────────────────

    def _make_channel_row(self, ch: ChannelConfig) -> ChannelRow:
        row = ChannelRow(ch)
        row.va_toggled.connect(self._on_va_toggle)
        row.sol_toggled.connect(self._on_sol_toggle)
        row.max_changed.connect(self.channel_max_changed)
        row.enabled_changed.connect(self.channel_enabled_changed)
        self._rows[ch.idx] = row
        return row

    @staticmethod
    def _make_section_label(text: str, color: str, height: int) -> QLabel:
        lbl = QLabel(text)
        lbl.setFixedHeight(height)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold; "
            f"padding-left: 6px;")
        return lbl

    # ── 타이머 ──────────────────────────────────────

    def _start_pv_timer(self):
        self._pv_timer = QTimer(self)
        self._pv_timer.timeout.connect(self._refresh_pv)
        self._pv_timer.start(PV_UPDATE_INTERVAL_MS)

    def _refresh_pv(self):
        if self._locked:
            return
        try:
            pvs = self._device.read_all_pv()
            for ch_idx, pv in pvs.items():
                if ch_idx in self._rows:
                    self._rows[ch_idx].update_pv(pv)
            for ch in self._channels:
                if ch.idx in self._rows:
                    self._rows[ch.idx].update_va_state(
                        self._device.get_va_state(ch.idx))
                    self._rows[ch.idx].update_sol_state(
                        self._device.get_sol_state(ch.idx))
            fw = self._device.get_fourway()
            self._fourway.set_position(fw.value.lower())
        except Exception as e:
            logger.debug(f"PV 갱신 오류: {e}")

    # ── 수동 밸브 제어 ─────────────────────────────

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

    # ── 엔진 시그널 수신 ──────────────────────────

    def on_pv_updated(self, pv_dict: dict):
        for ch_idx, pv in pv_dict.items():
            if ch_idx in self._rows:
                self._rows[ch_idx].update_pv(pv)

    def on_sv_updated(self, sv_dict: dict):
        for ch_idx, sv in sv_dict.items():
            if ch_idx in self._rows:
                self._rows[ch_idx].update_sv(sv)

    def lock(self, lock: bool):
        self._locked = lock
        for row in self._rows.values():
            row.lock_control(lock)
        self._fourway.lock_control(lock)
        self._btn_all_open.setEnabled(not lock)
        self._btn_all_close.setEnabled(not lock)

    def refresh_channels(self, channels: list[ChannelConfig]):
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
