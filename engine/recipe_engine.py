"""
engine/recipe_engine.py
레시피 실행 상태머신 (QThread)

상태:
  IDLE → STEP_PREPARE → STEP_MEASURE → [반복] → LOOP_CHECK → IDLE
              ↓ stop/emergency
         STOPPING → IDLE
         EMERGENCY (즉시)

UI와의 통신은 Signal 전용. 직접 UI 접근 금지.
"""
from __future__ import annotations
import time
import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal

from app.models import EngineState, Recipe, RecipeStep, ChannelConfig, AlarmLevel
from calculation.flow_calculator import FlowCalculator, CalcResult
from services.device_service import DeviceService
from engine.interlock import Interlock
from engine.alarm_manager import AlarmManager

logger = logging.getLogger(__name__)


class RecipeEngine(QThread):
    """레시피 실행 엔진 (별도 QThread)"""

    # ── Signals ──────────────────────────────────────
    state_changed   = Signal(object)       # EngineState
    step_started    = Signal(int, str)     # (step_idx, step_id)
    step_finished   = Signal(int, str)     # (step_idx, step_id)
    prepare_tick    = Signal(int, int)     # (elapsed_sec, total_sec)
    measure_tick    = Signal(int, int)
    pv_updated      = Signal(object)       # dict {ch_idx: pv_sccm}
    sv_updated      = Signal(object)       # dict {ch_idx: sv_sccm}
    loop_updated    = Signal(int, int)     # (current_loop, total_loops)
    recipe_finished = Signal()
    recipe_stopped  = Signal()
    error_occurred  = Signal(str)

    def __init__(self,
                 device: DeviceService,
                 calculator: FlowCalculator,
                 interlock: Interlock,
                 alarm: AlarmManager,
                 data_logger=None):
        super().__init__()
        self._device     = device
        self._calc       = calculator
        self._interlock  = interlock
        self._alarm      = alarm
        self._data_logger = data_logger   # optional DataLogger

        self._recipe: Optional[Recipe] = None
        self._channels: list[ChannelConfig] = []
        self._state = EngineState.IDLE
        self._stop_requested    = False
        self._emergency_requested = False

        # 읽기용 퍼블릭 상태
        self.current_loop     = 0
        self.current_step_idx = 0
        self.current_sv: dict[int, float] = {}

    # ── 공개 API ─────────────────────────────────────

    def load_recipe(self, recipe: Recipe, channels: list[ChannelConfig]):
        if self.isRunning():
            self._alarm.warning("실행 중에는 레시피를 변경할 수 없습니다.", "Engine")
            return
        self._recipe   = recipe
        self._channels = channels
        self._alarm.info(f"레시피 로드: {recipe.name}", "Engine")

    def start_recipe(self):
        if self.isRunning():
            self._alarm.warning("이미 실행 중입니다.", "Engine")
            return
        if self._recipe is None:
            self._alarm.error("레시피가 로드되지 않았습니다.", "Engine")
            return
        self._stop_requested      = False
        self._emergency_requested = False
        self.start()

    def request_stop(self):
        self._stop_requested = True
        self._alarm.info("정지 요청됨", "Engine")

    def request_emergency(self):
        self._emergency_requested = True
        self._alarm.critical("비상 정지 요청됨", "Engine")

    @property
    def state(self) -> EngineState:
        return self._state

    def set_data_logger(self, dl):
        """DataLogger 주입 (옵션)"""
        self._data_logger = dl

    # ── QThread.run() ─────────────────────────────────

    def run(self):
        recipe   = self._recipe
        channels = self._channels

        # 1. 전체 사전 계산
        calc_results = [self._calc.calculate(step, channels) for step in recipe.steps]

        # 2. 인터락 전체 검사
        errors = self._interlock.check_before_run(recipe.steps, calc_results)
        if errors:
            for e in errors:
                self._alarm.error(e, "Interlock")
            self.error_occurred.emit("\n".join(errors))
            return

        # 3. 데이터 로거 시작
        if self._data_logger:
            self._data_logger.start(recipe.name)

        self._alarm.info(f"레시피 시작: {recipe.name}", "Engine")

        for loop_idx in range(recipe.loop_count):
            self.current_loop = loop_idx + 1
            self.loop_updated.emit(loop_idx + 1, recipe.loop_count)

            for step_idx, (step, calc) in enumerate(zip(recipe.steps, calc_results)):
                if self._check_stop():
                    return
                self.current_step_idx = step_idx
                if self._data_logger:
                    self._data_logger.update_step(step.step_id, loop_idx + 1)
                self._run_step(step_idx, step, calc, channels)
                if self._check_stop():
                    return

            # 루프 간 인터벌
            if loop_idx < recipe.loop_count - 1 and recipe.interval_sec > 0:
                self._alarm.info(
                    f"루프 {loop_idx+1}/{recipe.loop_count} 완료. "
                    f"인터벌 {recipe.interval_sec}초 대기", "Engine")
                self._do_stop_gases()
                self._wait_seconds(recipe.interval_sec)
                if self._check_stop():
                    return

        # 정상 완료
        self._do_safe_stop()
        if self._data_logger:
            self._data_logger.stop()
        self._alarm.info("레시피 완료", "Engine")
        self.recipe_finished.emit()

    # ── 내부 메서드 ──────────────────────────────────

    def _run_step(self, step_idx: int, step: RecipeStep,
                  calc: CalcResult, channels: list[ChannelConfig]):
        """단일 스텝 실행 (repeat 포함)"""
        for rep in range(step.repeat):
            if self._check_stop():
                return

            self.step_started.emit(step_idx, step.step_id)
            self._alarm.info(
                f"{step.step_id} 시작 (반복 {rep+1}/{step.repeat})", "Engine")

            # PREPARE 단계
            self._set_state(EngineState.STEP_PREPARE)
            self._apply_step(step, calc, channels)
            if step.prepare_sec > 0:
                self._wait_seconds(step.prepare_sec, phase="prepare",
                                   total=step.prepare_sec)
            if self._check_stop():
                return

            # MEASURE 단계
            self._set_state(EngineState.STEP_MEASURE)
            if step.measure_sec > 0:
                self._wait_seconds(step.measure_sec, phase="measure",
                                   total=step.measure_sec)
            if self._check_stop():
                return

            self.step_finished.emit(step_idx, step.step_id)
            self._alarm.info(f"{step.step_id} 완료", "Engine")

    def _apply_step(self, step: RecipeStep, calc: CalcResult,
                    channels: list[ChannelConfig]):
        """스텝 가스 설정 적용"""
        self._device.set_fourway(step.fourway)

        # 활성 채널 열기
        for ch in channels:
            if ch.enabled:
                self._device.open_channel(ch.idx)

        # MFC setpoint 설정
        sv_dict: dict[int, float] = {}
        for ch_idx, sp in calc.setpoints.items():
            self._device.set_mfc_setpoint_sccm(ch_idx, sp.mfc_setpoint_sccm)
            sv_dict[ch_idx] = sp.desired_flow_sccm

        self.current_sv = sv_dict
        self.sv_updated.emit(sv_dict)
        if self._data_logger:
            self._data_logger.update_sv(sv_dict)

    def _wait_seconds(self, seconds: int, phase: str = "idle", total: int = 0):
        """초 단위 대기 + 1초마다 PV 업데이트 시그널"""
        total = total or seconds
        for elapsed in range(seconds):
            if self._check_stop():
                return
            time.sleep(1)

            # PV 읽기
            try:
                pv = self._device.read_all_pv()
                self.pv_updated.emit(pv)
                if self._data_logger:
                    self._data_logger.log_row(pv)
            except Exception as e:
                self._alarm.warning(f"PV 읽기 오류: {e}", "Engine")

            if phase == "prepare":
                self.prepare_tick.emit(elapsed + 1, total)
            elif phase == "measure":
                self.measure_tick.emit(elapsed + 1, total)

    def _check_stop(self) -> bool:
        """정지/비상정지 체크. True이면 이미 처리됨."""
        if self._emergency_requested:
            self._do_emergency()
            return True
        if self._stop_requested:
            self._do_safe_stop()
            self.recipe_stopped.emit()
            return True
        return False

    def _do_safe_stop(self):
        """안전 정지: MFC→0 → 딜레이 → 밸브 닫기"""
        self._set_state(EngineState.STOPPING)
        self._alarm.info("안전 정지 실행", "Engine")
        self._do_stop_gases()
        if self._data_logger and self._data_logger.is_logging:
            self._data_logger.stop()
        self._set_state(EngineState.IDLE)

    def _do_stop_gases(self):
        """가스 공급 중단"""
        self._device.close_all_channels()

    def _do_emergency(self):
        """비상 정지: 즉시 차단"""
        self._set_state(EngineState.EMERGENCY)
        self._alarm.critical("비상 정지 실행", "Engine")
        self._device.emergency_stop()
        if self._data_logger and self._data_logger.is_logging:
            self._data_logger.stop()

    def _set_state(self, state: EngineState):
        self._state = state
        self.state_changed.emit(state)
        logger.debug(f"엔진 상태: {state.value}")
