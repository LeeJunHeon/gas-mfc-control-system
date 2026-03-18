"""
ui/main_window.py
메인 윈도우 - 모든 패널 조합 + 엔진 Signal 연결
"""
from __future__ import annotations
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QStatusBar, QMessageBox, QPushButton
)
from PySide6.QtCore import Qt, QTimer, Slot

from app.config import AppConfig
from app.models import EngineState, AlarmLevel, Recipe
from engine.recipe_engine import RecipeEngine
from engine.alarm_manager import AlarmManager
from services.device_service import DeviceService
from ui.hmi_panel import HmiPanel
from ui.recipe_panel import RecipePanel
from ui.process_panel import ProcessPanel
from ui.log_panel import LogPanel
from ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self, config: AppConfig, device: DeviceService,
                 engine: RecipeEngine, alarm: AlarmManager, flow_calc):
        super().__init__()
        self._config    = config
        self._device    = device
        self._engine    = engine
        self._alarm     = alarm
        self._flow_calc = flow_calc

        self.setWindowTitle("GAS Control System v1.0")
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._connect_signals()
        self._startup()

    # ── UI 구성 ───────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-height: 36px; font-size: 14px; }")


        # HMI
        self._hmi = HmiPanel(channels=self._config.channels, device=self._device)
        self._tabs.addTab(self._hmi, "HMI")

        # 레시피 편집
        self._recipe_panel = RecipePanel(
            channels=self._config.channels,
            flow_calc=self._flow_calc,
            recipe_dir=self._config.recipe_dir,
        )
        self._tabs.addTab(self._recipe_panel, "레시피")

        # 공정 실행
        self._process = ProcessPanel(channels=self._config.channels)
        self._tabs.addTab(self._process, "공정 실행")

        # 로그
        self._log = LogPanel(log_dir=self._config.log_dir)
        self._tabs.addTab(self._log, "로그")

        root.addWidget(self._tabs)

        # 상태바
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._lbl_sb_state  = QLabel("상태: 대기")
        self._lbl_sb_recipe = QLabel("레시피: —")
        self._lbl_sb_time   = QLabel("")

        # 드라이버 모드 배지 (눈에 띄게)
        self._lbl_sb_hw = QLabel("SIM")
        self._lbl_sb_hw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_sb_hw.setFixedWidth(120)
        self._lbl_sb_hw.setStyleSheet(
            "background:#e67e22;color:#ffffff;font-weight:bold;"
            "font-size:11px;border-radius:3px;padding:2px 8px;")

        for w in [self._lbl_sb_state, self._sep(),
                  self._lbl_sb_recipe, self._sep()]:
            sb.addWidget(w)
        sb.addPermanentWidget(self._lbl_sb_hw)
        sb.addPermanentWidget(self._sep())
        sb.addPermanentWidget(self._lbl_sb_time)

        self._clock = QTimer(self)
        self._clock.timeout.connect(
            lambda: self._lbl_sb_time.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self._clock.start(1000)

    def _make_header(self) -> QWidget:
        h = QWidget()
        h.setFixedHeight(48)
        h.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #2c3e50,stop:1 #34495e);"
            "border-bottom:2px solid #2980b9;")
        l = QHBoxLayout(h)
        l.setContentsMargins(14, 2, 14, 2)

        title = QLabel("⬡  GAS Control System")
        title.setStyleSheet(
            "color:#ffffff;font-size:19px;font-weight:bold;background:transparent;")
        l.addWidget(title)
        l.addStretch(1)

        self._lbl_alarm_badge = QLabel("")
        self._lbl_alarm_badge.setStyleSheet(
            "background:transparent;color:#e74c3c;font-size:13px;font-weight:bold;")
        l.addWidget(self._lbl_alarm_badge)

        btn_set = QPushButton("⚙  설정")
        btn_set.setFixedWidth(80)
        btn_set.setStyleSheet(
            "background:rgba(255,255,255,0.15);color:#ecf0f1;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px;font-size:12px;font-weight:bold;")
        btn_set.clicked.connect(self._open_settings)
        l.addWidget(btn_set)
        return h

    @staticmethod
    def _sep() -> QLabel:
        s = QLabel("|")
        s.setStyleSheet("color:#95a5a6;padding:0 4px;")
        return s

    # ── Signal 연결 ───────────────────────────────────

    def _connect_signals(self):
        # 엔진 → UI
        self._engine.state_changed.connect(self._on_engine_state)
        self._engine.step_started.connect(self._process.on_step_started)
        self._engine.prepare_tick.connect(self._process.on_prepare_tick)
        self._engine.measure_tick.connect(self._process.on_measure_tick)
        self._engine.pv_updated.connect(self._process.on_pv_updated)
        self._engine.pv_updated.connect(self._hmi.on_pv_updated)
        self._engine.sv_updated.connect(self._process.on_sv_updated)
        self._engine.sv_updated.connect(self._hmi.on_sv_updated)
        self._engine.loop_updated.connect(self._process.on_loop_updated)
        self._engine.recipe_finished.connect(self._on_recipe_finished)
        self._engine.recipe_stopped.connect(self._on_recipe_stopped)
        self._engine.error_occurred.connect(self._on_engine_error)

        # 공정 패널 → 엔진
        self._process.run_requested.connect(self._on_run_requested)
        self._process.stop_requested.connect(self._engine.request_stop)
        self._process.emergency_requested.connect(self._engine.request_emergency)
        self._process.purge_requested.connect(self._on_purge_requested)
        self._process.alarm_ack_requested.connect(self._on_alarm_ack)

        # 알람 → 로그 + UI
        self._alarm.alarm_raised.connect(self._log.on_alarm)
        self._alarm.alarm_raised.connect(self._process.on_alarm)
        self._alarm.alarm_raised.connect(self._on_alarm_badge)

        # 레시피 로드
        self._recipe_panel.recipe_loaded.connect(self._on_recipe_loaded)

    # ── 슬롯 ──────────────────────────────────────────

    def _startup(self):
        self._device.connect()
        drv = self._config.hardware.get("driver_type", "mock")
        if drv == "mock":
            self._lbl_sb_hw.setText("⚠ SIMULATION")
            self._lbl_sb_hw.setStyleSheet(
                "background:#e67e22;color:#ffffff;font-weight:bold;"
                "font-size:11px;border-radius:3px;padding:2px 8px;")
            self._hmi.set_hw_connected(False)
            self._alarm.info("시뮬레이션 모드 시작 (Mock Driver)", "System")
        else:
            self._lbl_sb_hw.setText("● CONNECTED")
            self._lbl_sb_hw.setStyleSheet(
                "background:#27ae60;color:#ffffff;font-weight:bold;"
                "font-size:11px;border-radius:3px;padding:2px 8px;")
            self._hmi.set_hw_connected(True)
            self._alarm.info("실제 장비 연결됨", "System")
        self._alarm.info("프로그램 시작", "System")

    @Slot(object)
    def _on_engine_state(self, state: EngineState):
        self._lbl_sb_state.setText(f"상태: {state.value}")
        self._process.on_state_changed(state)
        running = state not in (EngineState.IDLE, EngineState.EMERGENCY)
        self._hmi.lock(running)

    def _on_run_requested(self):
        recipe = self._recipe_panel.get_current_recipe()
        if not recipe.steps:
            QMessageBox.warning(self, "경고", "레시피 스텝이 없습니다.")
            return
        self._tabs.setCurrentWidget(self._process)
        self._process.set_recipe_name(recipe.name)
        self._engine.load_recipe(recipe, self._config.channels)
        self._engine.start_recipe()
        self._lbl_sb_recipe.setText(f"레시피: {recipe.name}")

    def _on_purge_requested(self):
        self._alarm.info("퍼지 시작", "System")
        self._device.close_all_channels()
        for ch in self._config.channels:
            if ch.is_balance and ch.enabled:
                self._device.open_channel(ch.idx)
                self._device.set_mfc_setpoint_sccm(ch.idx, ch.full_scale_sccm * 0.5)

    def _on_recipe_finished(self):
        self._alarm.info("레시피 완료", "System")
        QMessageBox.information(self, "완료", "레시피가 정상 완료되었습니다.")

    def _on_recipe_stopped(self):
        self._alarm.info("레시피 정지됨", "System")

    def _on_engine_error(self, msg: str):
        self._alarm.error(msg, "Engine")
        QMessageBox.critical(self, "실행 오류", msg)

    @Slot(object)
    def _on_alarm_badge(self, alarm):
        if alarm.level in (AlarmLevel.ERROR, AlarmLevel.CRITICAL):
            self._lbl_alarm_badge.setText(f"⚠ {alarm.message[:45]}")
        elif alarm.level == AlarmLevel.INFO:
            self._lbl_alarm_badge.setText("")

    def _on_alarm_ack(self):
        self._alarm.clear_active()
        self._process.on_alarm_ack()
        self._lbl_alarm_badge.setText("")

    def _on_recipe_loaded(self, recipe: Recipe):
        self._lbl_sb_recipe.setText(f"레시피: {recipe.name}")
        self._process.set_recipe_name(recipe.name)

    def _open_settings(self):
        dlg = SettingsDialog(self._config, self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self, cfg: AppConfig):
        self._device.update_channels(cfg.channels)
        self._hmi.refresh_channels(cfg.channels)
        self._recipe_panel.update_channels(cfg.channels)
        self._process.refresh_channels(cfg.channels)
        self._alarm.info("설정 적용됨", "System")

    def closeEvent(self, event):
        if self._engine.isRunning():
            r = QMessageBox.question(
                self, "종료 확인",
                "레시피 실행 중입니다. 종료하시겠습니까?\n(안전 정지 후 종료됩니다)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._engine.request_stop()
            self._engine.wait(4000)
        self._device.emergency_stop()
        self._device.disconnect()
        self._alarm.info("프로그램 종료", "System")
        event.accept()
