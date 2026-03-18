"""
ui/api.py
Python ↔ JavaScript 브릿지 클래스 (pywebview js_api)

JS에서 호출: pywebview.api.method_name(args)
Python→JS 푸시: window.evaluate_js("window.onXxx(data)")
"""
from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from typing import Optional

from app.config import AppConfig
from app.models import (
    EngineState, Recipe, RecipeStep, Alarm, AlarmLevel,
)
from engine.recipe_engine import RecipeEngine
from engine.alarm_manager import AlarmManager
from services.device_service import DeviceService
from calculation.flow_calculator import FlowCalculator

logger = logging.getLogger(__name__)


class GasControlApi:
    """pywebview JS API 브릿지 — 모든 public 메서드가 JS에 노출됨"""

    def __init__(self,
                 device_service: DeviceService,
                 recipe_engine: RecipeEngine,
                 alarm_manager: AlarmManager,
                 flow_calculator: FlowCalculator,
                 config: AppConfig,
                 data_logger=None):
        self._device  = device_service
        self._engine  = recipe_engine
        self._alarm   = alarm_manager
        self._calc    = flow_calculator
        self._config  = config
        self._data_logger = data_logger
        self._window  = None          # webview.Window (set_window 으로 주입)
        self._locked  = False         # 레시피 실행 중 수동 조작 잠금

        # PV 폴링 타이머
        self._pv_timer: Optional[threading.Timer] = None
        self._pv_running = False

        # ── 엔진 콜백 등록 ────────────────────────
        self._engine.on("state_changed",   self._on_state_changed)
        self._engine.on("step_started",    self._on_step_started)
        self._engine.on("step_finished",   self._on_step_finished)
        self._engine.on("prepare_tick",    self._on_prepare_tick)
        self._engine.on("measure_tick",    self._on_measure_tick)
        self._engine.on("pv_updated",      self._on_pv_updated)
        self._engine.on("sv_updated",      self._on_sv_updated)
        self._engine.on("loop_updated",    self._on_loop_updated)
        self._engine.on("recipe_finished", self._on_recipe_finished)
        self._engine.on("recipe_stopped",  self._on_recipe_stopped)
        self._engine.on("error_occurred",  self._on_error_occurred)

        # 알람 콜백
        self._alarm.on_alarm(self._on_alarm)

    # ── pywebview window 주입 ──────────────────────

    def set_window(self, window):
        self._window = window

    def _js(self, fn_call: str):
        """evaluate_js 래퍼 (스레드 안전, 윈도우 닫힘 무시)"""
        if self._window:
            try:
                self._window.evaluate_js(fn_call)
            except Exception:
                pass

    # ═══════════════════════════════════════════════════
    #  JS → Python  (pywebview.api.xxx)
    # ═══════════════════════════════════════════════════

    # ── 시스템 / 채널 정보 ────────────────────────

    def get_channels(self) -> list:
        """채널 설정 목록을 dict 리스트로 반환"""
        return [ch.to_dict() for ch in self._config.channels]

    def get_driver_mode(self) -> str:
        """현재 드라이버 타입 ("mock" | "real")"""
        return self._config.hardware.get("driver_type", "mock")

    def get_engine_state(self) -> str:
        """현재 엔진 상태 문자열"""
        return self._engine.state.value

    # ── PV / MFC ─────────────────────────────────

    def get_all_pv(self) -> dict:
        """모든 채널의 현재 PV(sccm) 읽기"""
        try:
            return self._device.read_all_pv()
        except Exception as e:
            logger.error(f"PV 읽기 오류: {e}")
            return {}

    def set_mfc(self, ch_idx: int, sccm: float):
        """지정 채널 MFC setpoint 설정"""
        if self._locked:
            return
        try:
            self._device.set_mfc_setpoint_sccm(ch_idx, sccm)
        except Exception as e:
            logger.error(f"MFC 설정 오류 (ch{ch_idx}): {e}")

    # ── 밸브 제어 ─────────────────────────────────

    def toggle_va_valve(self, ch_idx: int) -> bool:
        """VA 밸브 토글. 새 상태(open=True) 반환."""
        if self._locked:
            return False
        try:
            return self._device.toggle_va_valve(ch_idx)
        except Exception as e:
            logger.error(f"VA 토글 오류 (ch{ch_idx}): {e}")
            return False

    def toggle_sol_valve(self, ch_idx: int) -> bool:
        """솔밸브 토글. 새 상태(open=True) 반환."""
        if self._locked:
            return False
        try:
            return self._device.toggle_sol_valve(ch_idx)
        except Exception as e:
            logger.error(f"SOL 토글 오류 (ch{ch_idx}): {e}")
            return False

    def set_fourway(self, position: str):
        """4-way 밸브 위치 설정 ("vent" | "chamber")"""
        if self._locked:
            return
        self._device.set_fourway(position)

    def get_fourway(self) -> str:
        return self._device.get_fourway().value.lower()

    def get_valve_states(self) -> dict:
        """모든 채널 밸브 상태 {ch_idx: {va: bool, sol: bool}}"""
        states = {}
        for ch in self._config.channels:
            states[ch.idx] = {
                "va": self._device.get_va_state(ch.idx),
                "sol": self._device.get_sol_state(ch.idx),
            }
        return states

    def open_all_va(self):
        """활성 채널 전체 VA 열기"""
        if self._locked:
            return
        for ch in self._config.channels:
            if ch.enabled:
                self._device.toggle_va_valve(ch.idx)

    def close_all(self):
        """모든 채널 닫기"""
        if self._locked:
            return
        self._device.close_all_channels()

    # ── 레시피 파일 I/O ───────────────────────────

    def save_recipe(self, recipe_dict: dict, filename: str):
        """레시피를 JSON 파일로 저장"""
        try:
            path = self._config.recipe_dir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(recipe_dict, f, ensure_ascii=False, indent=2)
            logger.info(f"레시피 저장: {path}")
            return {"ok": True, "path": str(path)}
        except Exception as e:
            logger.error(f"레시피 저장 오류: {e}")
            return {"ok": False, "error": str(e)}

    def load_recipe(self, filename: str) -> dict:
        """JSON 파일에서 레시피 읽어 dict로 반환"""
        try:
            path = self._config.recipe_dir / filename
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # 유효성 검증 (from_dict → to_dict)
            recipe = Recipe.from_dict(data)
            logger.info(f"레시피 로드: {path}")
            return {"ok": True, "data": recipe.to_dict()}
        except Exception as e:
            logger.error(f"레시피 로드 오류: {e}")
            return {"ok": False, "error": str(e)}

    def save_recipe_dialog(self, recipe_json: str) -> dict:
        """OS 파일 저장 다이얼로그 → 저장"""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=str(self._config.recipe_dir),
                save_filename="recipe.json",
                file_types=("JSON Files (*.json)",),
            )
            if result:
                path = result if isinstance(result, str) else result[0]
                with open(path, "w", encoding="utf-8") as f:
                    f.write(recipe_json)
                return {"ok": True, "path": path}
            return {"ok": False, "error": "취소됨"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_recipe_dialog(self) -> dict:
        """OS 파일 열기 다이얼로그 → 레시피 dict 반환"""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=str(self._config.recipe_dir),
                file_types=("JSON Files (*.json)",),
            )
            if result and len(result) > 0:
                path = result[0]
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                recipe = Recipe.from_dict(data)
                return {"ok": True, "data": recipe.to_dict()}
            return {"ok": False, "error": "취소됨"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_recipes(self) -> list:
        """레시피 디렉토리의 JSON 파일 목록"""
        try:
            return sorted(
                p.name for p in self._config.recipe_dir.glob("*.json"))
        except Exception:
            return []

    # ── 공정 제어 ─────────────────────────────────

    def start_recipe(self, recipe_dict: dict) -> dict:
        """레시피 실행 시작"""
        try:
            recipe = Recipe.from_dict(recipe_dict)
            if not recipe.steps:
                return {"ok": False, "error": "스텝이 없습니다."}
            self._engine.load_recipe(recipe, self._config.channels)
            self._engine.start_recipe()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_recipe(self):
        """레시피 정상 정지 요청"""
        self._engine.request_stop()

    def emergency_stop(self):
        """비상 정지 (즉시 가스 차단)"""
        self._engine.request_emergency()

    def purge(self):
        """퍼지: balance 가스만 50% 유량으로 흘림"""
        self._alarm.info("퍼지 시작", "System")
        self._device.close_all_channels()
        for ch in self._config.channels:
            if ch.is_balance and ch.enabled:
                self._device.open_channel(ch.idx)
                self._device.set_mfc_setpoint_sccm(
                    ch.idx, ch.full_scale_sccm * 0.5)

    # ── 알람 ──────────────────────────────────────

    def get_alarm_history(self) -> list:
        """알람 이력을 dict 리스트로 반환"""
        return [
            {
                "level": a.level.value,
                "message": a.message,
                "source": a.source,
                "timestamp": a.timestamp,
            }
            for a in self._alarm.history
        ]

    def ack_alarm(self):
        """활성 알람 해제"""
        self._alarm.clear_active()
        self._js("window.onAlarmAck && window.onAlarmAck()")

    # ── Setpoint 미리보기 ─────────────────────────

    def calc_setpoints_preview(self, step_dict: dict) -> str:
        """스텝의 MFC setpoint 미리보기 계산 결과를 포맷된 텍스트로 반환"""
        try:
            step = RecipeStep.from_dict(step_dict)
            rows = self._calc.preview_table(step, self._config.channels)

            lines = [
                f"{'채널':<10} {'목표(sccm)':>12} {'설정(sccm)':>12} {'전압(V)':>8}"
            ]
            lines.append("─" * 46)
            for r in rows:
                lines.append(
                    f"{r['채널']:<10} {r['목표유량(sccm)']:>12.1f} "
                    f"{r['MFC설정(sccm)']:>12.1f} {r['DAC전압(V)']:>8.3f}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"계산 오류: {e}"

    # ═══════════════════════════════════════════════════
    #  PV 주기 폴링 (1초 간격)
    # ═══════════════════════════════════════════════════

    def start_pv_polling(self):
        """PV 주기 갱신 시작 (JS에서 초기화 시 호출)"""
        self._pv_running = True
        self._poll_pv()

    def stop_pv_polling(self):
        """PV 주기 갱신 중지"""
        self._pv_running = False

    def _poll_pv(self):
        if not self._pv_running:
            return
        if not self._locked:
            try:
                # PV
                pvs = self._device.read_all_pv()
                pv_json = json.dumps({str(k): v for k, v in pvs.items()})
                self._js(f"window.onPvUpdate && window.onPvUpdate({pv_json})")

                # 밸브 상태
                vs = {}
                for ch in self._config.channels:
                    vs[str(ch.idx)] = {
                        "va": self._device.get_va_state(ch.idx),
                        "sol": self._device.get_sol_state(ch.idx),
                    }
                vs_json = json.dumps(vs)
                self._js(f"window.onValveUpdate && window.onValveUpdate({vs_json})")

                # 4-way
                fw = self._device.get_fourway().value.lower()
                self._js(f'window.onFourwayUpdate && window.onFourwayUpdate("{fw}")')
            except Exception as e:
                logger.debug(f"PV 폴링 오류: {e}")

        # 다음 타이머
        self._pv_timer = threading.Timer(1.0, self._poll_pv)
        self._pv_timer.daemon = True
        self._pv_timer.start()

    # ═══════════════════════════════════════════════════
    #  엔진 콜백 → JS 이벤트 푸시
    # ═══════════════════════════════════════════════════

    def _on_state_changed(self, state: EngineState):
        self._locked = state not in (EngineState.IDLE,)
        self._js(f'window.onStateChanged && window.onStateChanged("{state.value}")')

    def _on_step_started(self, step_idx: int, step_id: str):
        self._js(f'window.onStepStarted && window.onStepStarted({step_idx}, "{step_id}")')

    def _on_step_finished(self, step_idx: int, step_id: str):
        self._js(f'window.onStepFinished && window.onStepFinished({step_idx}, "{step_id}")')

    def _on_prepare_tick(self, elapsed: int, total: int):
        self._js(f"window.onPrepareTick && window.onPrepareTick({elapsed}, {total})")

    def _on_measure_tick(self, elapsed: int, total: int):
        self._js(f"window.onMeasureTick && window.onMeasureTick({elapsed}, {total})")

    def _on_pv_updated(self, pv_dict: dict):
        pv_json = json.dumps({str(k): v for k, v in pv_dict.items()})
        self._js(f"window.onPvUpdate && window.onPvUpdate({pv_json})")

    def _on_sv_updated(self, sv_dict: dict):
        sv_json = json.dumps({str(k): v for k, v in sv_dict.items()})
        self._js(f"window.onSvUpdate && window.onSvUpdate({sv_json})")

    def _on_loop_updated(self, current: int, total: int):
        self._js(f"window.onLoopUpdated && window.onLoopUpdated({current}, {total})")

    def _on_recipe_finished(self):
        self._js("window.onRecipeFinished && window.onRecipeFinished()")

    def _on_recipe_stopped(self):
        self._js("window.onRecipeStopped && window.onRecipeStopped()")

    def _on_error_occurred(self, msg: str):
        safe = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        self._js(f'window.onError && window.onError("{safe}")')

    def _on_alarm(self, alarm: Alarm):
        data = json.dumps({
            "level": alarm.level.value,
            "message": alarm.message,
            "source": alarm.source,
            "timestamp": alarm.timestamp,
        }, ensure_ascii=False)
        self._js(f"window.onAlarm && window.onAlarm({data})")

    # ═══════════════════════════════════════════════════
    #  종료
    # ═══════════════════════════════════════════════════

    def shutdown(self):
        """앱 종료 시 호출 — 타이머 정리 + 안전 정지"""
        self._pv_running = False
        if self._pv_timer:
            self._pv_timer.cancel()
        if self._engine.isRunning():
            self._engine.request_stop()
            self._engine.wait(4000)
        self._device.emergency_stop()
        self._device.disconnect()
        self._alarm.info("프로그램 종료", "System")
