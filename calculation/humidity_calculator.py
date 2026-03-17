"""
calculation/humidity_calculator.py
습도(Humidity) 관련 유량 계산

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
버블러(Bubbler) 방식 시스템 구성:
  [Dry Air MFC] ─────────────┐
                              ├──→ [혼합] → 챔버
  [Wet Air MFC] → [버블러] ──┘

버블러: 특정 온도(T)의 물 통을 통과한 Air
       → 출구에서 수증기 포화 상태 (몰분율 = x_sat = P_sat(T)/P_total)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[설정값 Humidity(%) 의 의미]

프로그램에서 설정하는 Humidity(%)는 **Wet Air 비율**을 의미합니다.
  wet_flow = total_flow × Humidity(%) / 100

실제 챔버 내 RH(%)는 버블러 온도와 시스템 압력에 따라:
  actual_RH(%) = (wet_flow / total_flow) × (P_sat(T_bubbler) / P_total) × 100

→ 따라서 현장에서 반드시 RH 센서로 실측값과 교정이 필요합니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations
import math
import logging

logger = logging.getLogger(__name__)


def sat_pressure_kpa(T_celsius: float) -> float:
    """
    물의 포화 수증기압 (kPa), Antoine 방정식
    log10(P_mmHg) = A - B / (C + T)   [0~100°C 유효]
    """
    if not (0 <= T_celsius <= 100):
        logger.warning(f"온도 {T_celsius}°C가 Antoine 유효 범위(0~100°C) 밖")
    A, B, C = 8.07131, 1730.63, 233.426
    log_p_mmhg = A - B / (C + T_celsius)
    p_mmhg = 10 ** log_p_mmhg
    return p_mmhg * 0.133322   # mmHg → kPa


class HumidityCalculator:
    """
    버블러 방식 Wet Air 유량 계산기

    설정값 Humidity(%) = Wet Air가 전체 유량에서 차지하는 비율
      wet_flow = total_flow × humidity_pct / 100
    """

    def __init__(self, bubbler_temp_c: float = 25.0,
                 system_pressure_kpa: float = 101.3):
        self.bubbler_temp_c      = bubbler_temp_c
        self.system_pressure_kpa = system_pressure_kpa

    # ── 공개 API ──────────────────────────────────────

    def wet_air_flow(self, total_flow_sccm: float, humidity_pct: float) -> float:
        """
        Wet Air MFC 설정 유량 계산

        Args:
            total_flow_sccm: 전체 혼합 유량 (sccm)
            humidity_pct   : 설정 습도 (%). Wet Air 비율을 의미.

        Returns:
            wet_air_flow (sccm): Wet Air MFC에 설정할 유량
        """
        if humidity_pct <= 0:
            return 0.0
        if humidity_pct > 100:
            logger.warning(f"Humidity {humidity_pct}% > 100% → 100%로 클램프")
            humidity_pct = 100.0

        # wet_flow = total × (RH%) / 100
        wet_flow = total_flow_sccm * (humidity_pct / 100.0)
        return min(wet_flow, total_flow_sccm)

    def actual_rh_pct(self, wet_flow_sccm: float, total_flow_sccm: float) -> float:
        """
        실제 챔버 내 RH(%) 역산 (버블러 온도 기준)

        actual_RH = (wet_flow / total_flow) × (P_sat(T) / P_total) × 100
        """
        if total_flow_sccm <= 0:
            return 0.0
        p_sat  = sat_pressure_kpa(self.bubbler_temp_c)
        x_sat  = p_sat / self.system_pressure_kpa
        ratio  = wet_flow_sccm / total_flow_sccm
        return ratio * x_sat * 100.0

    def required_wet_flow_for_rh(self, total_flow_sccm: float,
                                  target_rh_pct: float) -> float:
        """
        챔버 내 실제 RH(%)를 목표로 할 때 필요한 wet_flow 계산
        (버블러 온도/압력 조건 사용)

        target_rh / 100 = wet_flow/total × P_sat/P_total
        → wet_flow = total × (target_rh/100) / (P_sat/P_total)

        주의: 이 모드에서는 total_flow가 고정일 때만 정확
        """
        if target_rh_pct <= 0:
            return 0.0
        p_sat = sat_pressure_kpa(self.bubbler_temp_c)
        x_sat = p_sat / self.system_pressure_kpa
        if x_sat <= 0:
            return 0.0
        wet_flow = total_flow_sccm * (target_rh_pct / 100.0) / x_sat
        return min(wet_flow, total_flow_sccm)

    def update_conditions(self, bubbler_temp_c: float, pressure_kpa: float):
        """운전 조건 업데이트"""
        self.bubbler_temp_c      = bubbler_temp_c
        self.system_pressure_kpa = pressure_kpa
        p_sat = sat_pressure_kpa(bubbler_temp_c)
        logger.info(
            f"습도 조건: 버블러 {bubbler_temp_c}°C, "
            f"P_sat={p_sat:.3f}kPa, 압력={pressure_kpa}kPa")

    @property
    def x_sat(self) -> float:
        """현재 조건의 포화 수증기 몰분율"""
        return sat_pressure_kpa(self.bubbler_temp_c) / self.system_pressure_kpa

    @property
    def max_achievable_rh_pct(self) -> float:
        """현재 버블러 온도/압력에서 이론적 최대 RH(%)"""
        return self.x_sat * 100.0
