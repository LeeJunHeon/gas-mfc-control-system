"""
calculation/flow_calculator.py
레시피 스텝 → 각 채널 MFC setpoint 계산

계산 흐름:
  1. 각 가스 채널: target_ppm, source_conc → 필요 실제 유량(sccm)
  2. 습도 채널: RH% → wet_air 유량(sccm)
  3. Balance 채널(Air): 나머지 유량
  4. CF 보정: 실제 유량 / CF → N2-equivalent MFC setpoint
  5. 전압 변환: setpoint / FS × 5.0V → DAC 출력 전압
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from app.models import ChannelConfig, RecipeStep
from calculation.gas_correction import GasCorrection
from calculation.humidity_calculator import HumidityCalculator

logger = logging.getLogger(__name__)


@dataclass
class SetpointResult:
    """채널별 계산 결과"""
    ch_idx: int
    desired_flow_sccm: float     # 실제 원하는 유량
    mfc_setpoint_sccm: float     # N2 기준 MFC 설정값 (CF 보정 후)
    voltage_v: float             # DAC 출력 전압
    warning: str = ""            # 경고 메시지


@dataclass
class CalcResult:
    """전체 계산 결과"""
    setpoints: dict              # {ch_idx: SetpointResult}
    total_flow_sccm: float
    balance_flow_sccm: float
    humidity_flow_sccm: float
    errors: list                 # 오류 메시지 리스트
    warnings: list               # 경고 메시지 리스트

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class FlowCalculator:
    """유량 계산기"""

    DAC_V_MAX = 5.0   # DAC 최대 출력 전압 (MFC 설정 기준)

    def __init__(self, gas_correction: GasCorrection,
                 humidity_calc: HumidityCalculator):
        self.gc = gas_correction
        self.hc = humidity_calc

    def calculate(self, step: RecipeStep,
                  channels: list[ChannelConfig]) -> CalcResult:
        """
        레시피 스텝 + 채널 설정 → 각 채널 setpoint 계산

        Args:
            step: 현재 레시피 스텝
            channels: 전체 채널 설정 리스트 (비활성 포함)

        Returns:
            CalcResult: 계산 결과 (errors가 있으면 실행 불가)
        """
        errors = []
        warnings = []
        setpoints: dict[int, SetpointResult] = {}
        gas_flow_total = 0.0

        enabled = [c for c in channels if c.enabled]
        gas_chs = [c for c in enabled if not c.is_balance]
        balance_chs = [c for c in enabled if c.is_balance]

        # ── 1. 가스 채널 유량 계산 ─────────────────────
        for ch in gas_chs:
            target_ppm = step.gas_targets.get(ch.idx, 0.0)

            if target_ppm <= 0:
                desired = 0.0
            elif ch.source_conc_ppm > 0:
                # 표준가스(희석): 실제유량 = Total × (목표농도 / source농도)
                desired = step.total_flow_sccm * (target_ppm / ch.source_conc_ppm)
            else:
                # 순수 가스: target_ppm을 vol ratio로 해석 (ppm = 1e-6)
                desired = step.total_flow_sccm * (target_ppm / 1_000_000.0)

            gas_flow_total += desired

            # CF 보정
            try:
                sp = self.gc.desired_to_setpoint(desired, ch.gas_name)
            except ValueError as e:
                errors.append(str(e))
                sp = 0.0

            # FS 초과 체크
            if sp > ch.full_scale_sccm:
                errors.append(
                    f"CH{ch.idx+1}({ch.name}): setpoint {sp:.1f} sccm > FS {ch.full_scale_sccm:.0f} sccm")
                sp = ch.full_scale_sccm  # 클램프 (에러 플래그는 있음)
                warnings.append(f"CH{ch.idx+1} setpoint가 FS에 클램프됨")

            voltage = (sp / ch.full_scale_sccm) * self.DAC_V_MAX if ch.full_scale_sccm > 0 else 0.0
            setpoints[ch.idx] = SetpointResult(
                ch_idx=ch.idx,
                desired_flow_sccm=desired,
                mfc_setpoint_sccm=sp,
                voltage_v=min(voltage, self.DAC_V_MAX),
            )

        # ── 2. Humidity 계산 ──────────────────────────
        self.hc.update_conditions(
            step.__dict__.get("bubbler_temp_c", 25.0) if hasattr(step, "bubbler_temp_c") else 25.0,
            step.__dict__.get("system_pressure_kpa", 101.3) if hasattr(step, "system_pressure_kpa") else 101.3,
        )
        humidity_flow = self.hc.wet_air_flow(step.total_flow_sccm, step.humidity_pct)
        gas_flow_total += humidity_flow

        # ── 3. Balance(Air) 채널 ──────────────────────
        balance_flow = step.total_flow_sccm - gas_flow_total
        if balance_flow < 0:
            errors.append(
                f"가스 합계({gas_flow_total:.1f} sccm)가 Total Flow({step.total_flow_sccm:.1f} sccm) 초과")
            balance_flow = 0.0

        per_balance = balance_flow / len(balance_chs) if balance_chs else 0.0
        for ch in balance_chs:
            sp = per_balance / ch.cf if ch.cf > 0 else 0.0
            if sp > ch.full_scale_sccm:
                warnings.append(
                    f"Balance CH{ch.idx+1}: {sp:.1f} sccm > FS {ch.full_scale_sccm:.0f} sccm")
                sp = ch.full_scale_sccm
            voltage = (sp / ch.full_scale_sccm) * self.DAC_V_MAX if ch.full_scale_sccm > 0 else 0.0
            setpoints[ch.idx] = SetpointResult(
                ch_idx=ch.idx,
                desired_flow_sccm=per_balance,
                mfc_setpoint_sccm=sp,
                voltage_v=min(voltage, self.DAC_V_MAX),
            )

        # 비활성 채널은 setpoint=0
        for ch in channels:
            if not ch.enabled and ch.idx not in setpoints:
                setpoints[ch.idx] = SetpointResult(
                    ch_idx=ch.idx,
                    desired_flow_sccm=0.0,
                    mfc_setpoint_sccm=0.0,
                    voltage_v=0.0,
                )

        return CalcResult(
            setpoints=setpoints,
            total_flow_sccm=step.total_flow_sccm,
            balance_flow_sccm=balance_flow,
            humidity_flow_sccm=humidity_flow,
            errors=errors,
            warnings=warnings,
        )

    def sccm_to_voltage(self, sccm: float, full_scale: float) -> float:
        """sccm → DAC 전압 (0~5V)"""
        if full_scale <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, sccm / full_scale))
        return ratio * self.DAC_V_MAX

    def voltage_to_sccm(self, voltage: float, full_scale: float,
                        cf: float = 1.0) -> float:
        """ADC 전압 → 실제 유량 (sccm), CF 보정 포함"""
        ratio = max(0.0, min(1.0, voltage / self.DAC_V_MAX))
        setpoint_sccm = ratio * full_scale
        return setpoint_sccm * cf   # N2 기준 setpoint × CF = 실제 유량

    def preview_table(self, step: RecipeStep,
                      channels: list[ChannelConfig]) -> list[dict]:
        """
        UI 미리보기용: 각 채널의 계산 결과를 dict 리스트로 반환
        """
        result = self.calculate(step, channels)
        rows = []
        for ch in channels:
            sp = result.setpoints.get(ch.idx)
            rows.append({
                "채널": ch.name,
                "목표유량(sccm)": round(sp.desired_flow_sccm, 2) if sp else 0,
                "MFC설정(sccm)": round(sp.mfc_setpoint_sccm, 2) if sp else 0,
                "DAC전압(V)": round(sp.voltage_v, 3) if sp else 0,
                "CF": ch.cf,
                "FS(sccm)": ch.full_scale_sccm,
            })
        return rows
