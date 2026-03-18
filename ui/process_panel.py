"""
ui/process_panel.py
공정 실행 패널 - 실시간 레시피 진행 표시 + 제어 버튼
"""
from __future__ import annotations
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox, QMessageBox, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal

from app.models import EngineState, ChannelConfig, Alarm, AlarmLevel
from ui.widgets.led_widget import LedIndicator

logger = logging.getLogger(__name__)


class PvBarWidget(QWidget):
    """채널 1개의 PV/SV 가로 막대 표시"""

    def __init__(self, ch: ChannelConfig, parent=None):
        super().__init__(parent)
        self._ch = ch
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        self._lbl_name = QLabel(self._ch.name)
        self._lbl_name.setFixedWidth(62)
        self._lbl_name.setStyleSheet(
            f"color:{self._ch.color};font-size:12px;font-weight:bold;")

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(20)
        self._bar.setStyleSheet(
            f"QProgressBar{{background:#e8eaed;border:1px solid #bdc3c7;border-radius:4px;}}"
            f"QProgressBar::chunk{{background:{self._ch.color};border-radius:3px;}}")

        self._lbl_pv = QLabel("0.0")
        self._lbl_pv.setFixedWidth(68)
        self._lbl_pv.setObjectName("label_pv")
        self._lbl_pv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._lbl_sv = QLabel("/ 0.0")
        self._lbl_sv.setFixedWidth(70)
        self._lbl_sv.setObjectName("label_sv")

        self._lbl_unit = QLabel("sccm")
        self._lbl_unit.setFixedWidth(36)
        self._lbl_unit.setStyleSheet("color:#7f8c8d;font-size:10px;")

        layout.addWidget(self._lbl_name)
        layout.addWidget(self._bar, stretch=1)
        layout.addWidget(self._lbl_pv)
        layout.addWidget(self._lbl_sv)
        layout.addWidget(self._lbl_unit)

    def update_pv(self, pv: float):
        self._lbl_pv.setText(f"{pv:.1f}")
        fs = self._ch.full_scale_sccm
        self._bar.setValue(min(1000, int((pv / fs * 1000) if fs > 0 else 0)))

    def update_sv(self, sv: float):
        self._lbl_sv.setText(f"/ {sv:.1f}")

    def update_channel(self, ch: ChannelConfig):
        self._ch = ch
        self._lbl_name.setText(ch.name)


class ProcessPanel(QWidget):
    """공정 실행 패널"""

    run_requested       = Signal()
    stop_requested      = Signal()
    emergency_requested = Signal()
    purge_requested     = Signal()
    alarm_ack_requested = Signal()

    def __init__(self, channels: list[ChannelConfig] = None, parent=None):
        super().__init__(parent)
        self._channels = channels or []
        self._recipe_name = ""
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # ══════════════════════════════════════════════════
        # 1행: 공정 상태 (컴팩트 한 줄) + 레시피명
        # ══════════════════════════════════════════════════
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self._led_state = LedIndicator("gray", size=22)
        self._lbl_state = QLabel("대기")
        self._lbl_state.setStyleSheet(
            "color:#2c3e50;font-size:17px;font-weight:bold;")

        sep1 = self._make_vsep()

        self._lbl_loop = QLabel("루프: -/-")
        self._lbl_loop.setStyleSheet("color:#5d6d7e;font-size:12px;font-weight:bold;")
        self._lbl_step = QLabel("스텝: -")
        self._lbl_step.setStyleSheet("color:#5d6d7e;font-size:12px;font-weight:bold;")

        sep2 = self._make_vsep()

        self._lbl_recipe = QLabel("")
        self._lbl_recipe.setStyleSheet("color:#2980b9;font-size:12px;font-weight:bold;")

        status_row.addWidget(self._led_state)
        status_row.addWidget(self._lbl_state)
        status_row.addWidget(sep1)
        status_row.addWidget(self._lbl_loop)
        status_row.addWidget(self._lbl_step)
        status_row.addWidget(sep2)
        status_row.addWidget(self._lbl_recipe)
        status_row.addStretch(1)

        root.addLayout(status_row)

        # ══════════════════════════════════════════════════
        # 2행: 제어 버튼 (가로 2줄)
        # ══════════════════════════════════════════════════
        ctrl_grp = QGroupBox("제어")
        ctrl_root = QVBoxLayout(ctrl_grp)
        ctrl_root.setContentsMargins(8, 14, 8, 8)
        ctrl_root.setSpacing(6)

        # 1줄: AUTO RUN + STOP (크게)
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._btn_run = QPushButton("▶  AUTO RUN")
        self._btn_run.setObjectName("btn_autorun")
        self._btn_run.setFixedHeight(50)
        self._btn_run.setStyleSheet(
            self._btn_run.styleSheet() + "font-size:15px;")
        self._btn_run.clicked.connect(self.run_requested)

        self._btn_stop = QPushButton("■  STOP")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setFixedHeight(50)
        self._btn_stop.setStyleSheet(
            self._btn_stop.styleSheet() + "font-size:15px;")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop_clicked)

        row1.addWidget(self._btn_run, stretch=1)
        row1.addWidget(self._btn_stop, stretch=1)
        ctrl_root.addLayout(row1)

        # 2줄: PURGE + 비상정지 (보통 크기)
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self._btn_purge = QPushButton("PURGE")
        self._btn_purge.setObjectName("btn_purge")
        self._btn_purge.setFixedHeight(36)
        self._btn_purge.clicked.connect(self.purge_requested)

        self._btn_emergency = QPushButton("⚠  비상 정지")
        self._btn_emergency.setObjectName("btn_emergency")
        self._btn_emergency.setFixedHeight(40)
        self._btn_emergency.clicked.connect(self._on_emergency_clicked)

        row2.addWidget(self._btn_purge, stretch=1)
        row2.addWidget(self._btn_emergency, stretch=1)
        ctrl_root.addLayout(row2)

        root.addWidget(ctrl_grp)

        # ══════════════════════════════════════════════════
        # 3행: 공정 타이머 (프로그레스바 + 큰 카운트다운)
        # ══════════════════════════════════════════════════
        tg = QGroupBox("공정 타이머")
        tl = QVBoxLayout(tg)
        tl.setContentsMargins(8, 14, 8, 8)
        tl.setSpacing(4)

        for tag, color, name in [("prepare", "#e67e22", "준비"),
                                  ("measure", "#27ae60", "측정")]:
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl = QLabel(name)
            lbl.setFixedWidth(36)
            lbl.setStyleSheet(f"color:{color};font-weight:bold;font-size:12px;")

            pb = QProgressBar()
            pb.setObjectName(f"pb_{tag}")
            pb.setFormat("0 / 0 s")
            pb.setFixedHeight(22)

            cd = QLabel("--:--")
            cd.setFixedWidth(72)
            cd.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cd.setStyleSheet(
                f"color:{color};font-size:18px;font-weight:bold;"
                f"background:#ffffff;border:1px solid #bdc3c7;"
                f"border-radius:4px;padding:2px;")

            row.addWidget(lbl)
            row.addWidget(pb, stretch=1)
            row.addWidget(cd)
            tl.addLayout(row)
            setattr(self, f"_pb_{tag}", pb)
            setattr(self, f"_cd_{tag}", cd)
        root.addWidget(tg)

        # ══════════════════════════════════════════════════
        # 4행: PV 바 그래프 (stretch 확보)
        # ══════════════════════════════════════════════════
        pv_grp = QGroupBox("MFC 실시간 유량  ( PV / SV )")
        pv_layout = QVBoxLayout(pv_grp)
        pv_layout.setContentsMargins(6, 14, 6, 6)
        pv_layout.setSpacing(2)
        self._pv_bars: dict[int, PvBarWidget] = {}
        for ch in self._channels:
            if ch.enabled:
                bar = PvBarWidget(ch)
                self._pv_bars[ch.idx] = bar
                pv_layout.addWidget(bar)
        if not self._pv_bars:
            pv_layout.addWidget(QLabel("(활성 채널 없음)"))
        pv_layout.addStretch(1)
        pv_grp.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(pv_grp, stretch=1)

        # ══════════════════════════════════════════════════
        # 5행: 알람 (컴팩트)
        # ══════════════════════════════════════════════════
        alarm_grp = QGroupBox("알람")
        al = QHBoxLayout(alarm_grp)
        al.setContentsMargins(8, 14, 8, 8)
        self._led_alarm = LedIndicator("gray", size=18)
        self._lbl_alarm = QLabel("정상")
        self._lbl_alarm.setStyleSheet("color:#5d6d7e;")
        self._lbl_alarm.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._btn_ack = QPushButton("알람 확인")
        self._btn_ack.setMaximumWidth(90)
        self._btn_ack.clicked.connect(self.alarm_ack_requested)
        al.addWidget(self._led_alarm)
        al.addWidget(self._lbl_alarm)
        al.addWidget(self._btn_ack)
        root.addWidget(alarm_grp)

    # ── 유틸리티 ──────────────────────────────────────

    @staticmethod
    def _make_vsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:#bdc3c7;")
        sep.setFixedHeight(22)
        return sep

    # ── 버튼 핸들러 ──────────────────────────────────

    def _on_stop_clicked(self):
        reply = QMessageBox.question(
            self, "정지 확인",
            "공정을 정지하시겠습니까?\n(현재 측정 완료 후 안전하게 종료됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_requested.emit()

    def _on_emergency_clicked(self):
        reply = QMessageBox.critical(
            self, "⚠ 비상 정지",
            "즉시 모든 가스를 차단합니다!\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.emergency_requested.emit()

    # ── 엔진 Signal 수신 ─────────────────────────────

    def on_state_changed(self, state: EngineState):
        _map = {
            EngineState.IDLE:         ("gray",   "대기"),
            EngineState.STEP_PREPARE: ("orange", "준비 중"),
            EngineState.STEP_MEASURE: ("green",  "측정 중"),
            EngineState.STOPPING:     ("yellow", "정지 중"),
            EngineState.EMERGENCY:    ("red",    "비상 정지"),
            EngineState.PURGING:      ("blue",   "퍼지 중"),
        }
        color, text = _map.get(state, ("gray", state.value))
        self._led_state.set_color(color)
        self._led_state.set_on(state != EngineState.IDLE)
        self._lbl_state.setText(text)
        running = state not in (EngineState.IDLE,)
        self._btn_run.setEnabled(not running)
        self._btn_stop.setEnabled(running)

    def on_step_started(self, step_idx: int, step_id: str):
        self._lbl_step.setText(f"스텝: {step_id}")
        self._pb_prepare.setValue(0)
        self._pb_prepare.setFormat("0 / 0 s")
        self._pb_measure.setValue(0)
        self._pb_measure.setFormat("0 / 0 s")
        self._cd_prepare.setText("--:--")
        self._cd_measure.setText("--:--")

    def on_loop_updated(self, current: int, total: int):
        self._lbl_loop.setText(f"루프: {current}/{total}")

    def on_prepare_tick(self, elapsed: int, total: int):
        pct = int(elapsed / total * 100) if total > 0 else 0
        self._pb_prepare.setValue(pct)
        self._pb_prepare.setFormat(f"{elapsed} / {total} s")
        self._cd_prepare.setText(self._fmt(total - elapsed))

    def on_measure_tick(self, elapsed: int, total: int):
        pct = int(elapsed / total * 100) if total > 0 else 0
        self._pb_measure.setValue(pct)
        self._pb_measure.setFormat(f"{elapsed} / {total} s")
        self._cd_measure.setText(self._fmt(total - elapsed))

    def on_pv_updated(self, pv_dict: dict):
        for ch_idx, pv in pv_dict.items():
            if ch_idx in self._pv_bars:
                self._pv_bars[ch_idx].update_pv(pv)

    def on_sv_updated(self, sv_dict: dict):
        for ch_idx, sv in sv_dict.items():
            if ch_idx in self._pv_bars:
                self._pv_bars[ch_idx].update_sv(sv)

    def on_alarm(self, alarm: Alarm):
        _cmap = {
            AlarmLevel.INFO:     ("blue",   "#2980b9"),
            AlarmLevel.WARNING:  ("orange", "#e67e22"),
            AlarmLevel.ERROR:    ("red",    "#e74c3c"),
            AlarmLevel.CRITICAL: ("red",    "#c0392b"),
        }
        color, tc = _cmap.get(alarm.level, ("gray", "#5d6d7e"))
        self._led_alarm.set_color(color)
        self._led_alarm.set_on(True)
        self._lbl_alarm.setText(f"[{alarm.level.value}] {alarm.message}")
        self._lbl_alarm.setStyleSheet(f"color:{tc};font-weight:bold;")

    def on_alarm_ack(self):
        self._led_alarm.set_on(False)
        self._lbl_alarm.setText("정상")
        self._lbl_alarm.setStyleSheet("color:#5d6d7e;")

    def set_recipe_name(self, name: str):
        self._lbl_recipe.setText(name)

    def refresh_channels(self, channels: list[ChannelConfig]):
        self._channels = channels
        # PV 바 존재하는 것만 업데이트 (재구성은 재시작 시)
        for ch in channels:
            if ch.idx in self._pv_bars:
                self._pv_bars[ch.idx].update_channel(ch)

    @staticmethod
    def _fmt(sec: int) -> str:
        m, s = divmod(max(0, sec), 60)
        return f"{m:02d}:{s:02d}"
