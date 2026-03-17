"""
calculation/gas_correction.py
CF(Correction Factor) 조회 및 변환 유틸리티

HORIBA S48 매뉴얼 기준:
  실제유량 = MFC설정값(N2기준) × CF(사용가스)
  MFC설정값 = 원하는유량 / CF(사용가스)   [N2 기준이므로]
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class GasCorrection:
    """CF 테이블 기반 유량 보정 계산기"""

    def __init__(self, gas_library: dict[str, float]):
        """
        gas_library: {가스명: CF값} dict (AppConfig.gas_library)
        """
        self._table = gas_library

    def get_cf(self, gas_name: str) -> float:
        """가스명으로 CF 조회. 없으면 1.0 반환하고 경고."""
        if gas_name not in self._table:
            logger.warning(f"CF 테이블에 없는 가스: '{gas_name}'. CF=1.0 사용 (부정확할 수 있음)")
            return 1.0
        return self._table[gas_name]

    def desired_to_setpoint(self, desired_flow_sccm: float, gas_name: str) -> float:
        """
        원하는 실제 유량(sccm) → N2 기준 MFC setpoint(sccm)

        예: NO2(CF=1.01) 5sccm 흘리려면 MFC에 4.95sccm 설정
        """
        cf = self.get_cf(gas_name)
        if cf <= 0:
            raise ValueError(f"{gas_name} CF가 0 이하: {cf}")
        return desired_flow_sccm / cf

    def setpoint_to_actual(self, setpoint_sccm: float, gas_name: str) -> float:
        """
        N2 기준 MFC setpoint → 실제 가스 유량(sccm) (역방향 계산)
        """
        cf = self.get_cf(gas_name)
        return setpoint_sccm * cf

    def cross_calibrate(self, desired_flow: float,
                        use_gas: str, cal_gas: str = "N2") -> float:
        """
        보정가스가 N2가 아닌 경우 환산
        MFC setpoint = desired_flow × CF(cal_gas) / CF(use_gas)
        """
        cf_cal = self.get_cf(cal_gas)
        cf_use = self.get_cf(use_gas)
        return desired_flow * cf_cal / cf_use

    def available_gases(self) -> list[str]:
        return list(self._table.keys())
