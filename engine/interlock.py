"""
engine/interlock.py
인터락 - 레시피 실행 전/중 안전 조건 확인

각 체크는 (ok: bool, message: str) 튜플 반환.
하나라도 실패 시 실행 불가.
"""
from __future__ import annotations
import logging
from app.models import RecipeStep, ChannelConfig
from calculation.flow_calculator import CalcResult

logger = logging.getLogger(__name__)


class InterlockError(Exception):
    pass


class Interlock:
    """인터락 체크 모음"""

    def __init__(self, channels: list[ChannelConfig]):
        self._channels = channels

    def check_before_run(self, steps: list[RecipeStep],
                         calc_results: list[CalcResult]) -> list[str]:
        """
        AUTO RUN 시작 전 전체 레시피 검증
        Returns: 오류 메시지 리스트. 빈 리스트 = 통과
        """
        errors = []

        if not steps:
            errors.append("레시피에 스텝이 없습니다.")
            return errors

        enabled = [c for c in self._channels if c.enabled]
        if not enabled:
            errors.append("활성화된 채널이 없습니다.")

        for i, (step, calc) in enumerate(zip(steps, calc_results)):
            prefix = f"[{step.step_id}]"

            # 계산 오류
            for e in calc.errors:
                errors.append(f"{prefix} {e}")

            # Total flow 양수 확인
            if step.total_flow_sccm <= 0:
                errors.append(f"{prefix} Total Flow가 0 이하입니다.")

            # 시간 설정 확인
            if step.prepare_sec < 0:
                errors.append(f"{prefix} 준비 시간이 음수입니다.")
            if step.measure_sec < 0:
                errors.append(f"{prefix} 측정 시간이 음수입니다.")
            if step.repeat < 1:
                errors.append(f"{prefix} 반복 횟수가 1 미만입니다.")

        return errors

    def check_step(self, step: RecipeStep, calc: CalcResult,
                   device_connected: bool) -> list[str]:
        """
        개별 스텝 실행 직전 체크
        Returns: 오류 메시지 리스트
        """
        errors = []

        if not device_connected:
            errors.append("하드웨어가 연결되어 있지 않습니다.")

        for e in calc.errors:
            errors.append(e)

        # balance 유량이 음수인지 재확인
        if calc.balance_flow_sccm < 0:
            errors.append(
                f"Balance(Air) 유량이 음수입니다. 가스 setpoint의 합이 Total Flow를 초과합니다.")

        return errors

    def update_channels(self, channels: list[ChannelConfig]):
        self._channels = channels
