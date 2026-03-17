"""
services/device_service.py
하드웨어 추상화 레이어 - 채널 설정 + 드라이버를 조합하여
상위 레이어(RecipeEngine, HMI)에 고수준 API 제공

핵심 책임:
- sccm/전압 변환
- 밸브 ON/OFF 순서 제어
- PV 읽기 (ADC → sccm 변환)
- 비상정지
"""
from __future__ import annotations
import logging
import time
from typing import Optional

from app.models import ChannelConfig, ChannelState, FourWayPosition
from drivers.base_driver import BaseDriver

logger = logging.getLogger(__name__)

DAC_V_MAX = 5.0
SOL_DELAY = 0.15   # 솔밸브 열린 후 MFC setpoint 까지 딜레이(초)
MFC_ZERO_DELAY = 0.20  # MFC 0 설정 후 솔밸브 닫기 전 딜레이(초)


class DeviceService:
    """장치 제어 서비스"""

    def __init__(self, driver: BaseDriver,
                 channels: list[ChannelConfig],
                 hw_config: dict):
        """
        driver: BaseDriver 구현체 (MockDriver 또는 실제 드라이버)
        channels: 전체 8채널 설정
        hw_config: hardware.json 내용
        """
        self._drv = driver
        self._channels = channels
        self._cfg = hw_config
        self._pins = hw_config.get("channel_pins", {})
        self._fourway_coil: int = hw_config.get("fourway_coil", 16)

    # ── 연결 ──────────────────────────────────────────

    def connect(self) -> bool:
        return self._drv.connect()

    def disconnect(self):
        self._drv.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._drv.is_connected

    # ── MFC 제어 ──────────────────────────────────────

    def set_mfc_setpoint_sccm(self, ch_idx: int, setpoint_sccm: float):
        """
        채널 ch_idx의 MFC setpoint 설정 (N2 기준 sccm → 전압 → DAC)
        """
        ch = self._get_ch(ch_idx)
        if ch is None or not ch.enabled:
            return
        voltage = (setpoint_sccm / ch.full_scale_sccm) * DAC_V_MAX
        voltage = max(0.0, min(DAC_V_MAX, voltage))
        dac_ch = int(self._pins.get(str(ch_idx), {}).get("dac_ch", ch_idx))
        self._drv.write_dac(dac_ch, voltage)

    def set_all_mfc_setpoints(self, setpoints: dict[int, float]):
        """
        {ch_idx: setpoint_sccm} 딕셔너리로 전체 채널 일괄 설정
        """
        for ch_idx, sp in setpoints.items():
            self.set_mfc_setpoint_sccm(ch_idx, sp)

    def set_all_mfc_zero(self):
        """모든 채널 MFC setpoint를 0으로"""
        for ch in self._channels:
            if ch.enabled:
                dac_ch = int(self._pins.get(str(ch.idx), {}).get("dac_ch", ch.idx))
                self._drv.write_dac(dac_ch, 0.0)

    def read_pv_sccm(self, ch_idx: int) -> float:
        """
        채널 ch_idx의 MFC PV 읽기 (ADC 전압 → 실제 sccm, CF 보정 포함)
        """
        ch = self._get_ch(ch_idx)
        if ch is None or not ch.enabled:
            return 0.0
        adc_ch = int(self._pins.get(str(ch_idx), {}).get("adc_ch", ch_idx))
        voltage = self._drv.read_adc(adc_ch)
        # ADC → N2 기준 sccm → 실제 sccm (CF 보정)
        n2_sccm = (voltage / DAC_V_MAX) * ch.full_scale_sccm
        actual_sccm = n2_sccm * ch.cf
        return max(0.0, actual_sccm)

    def read_all_pv(self) -> dict[int, float]:
        """전체 활성 채널 PV 읽기"""
        result = {}
        for ch in self._channels:
            if ch.enabled:
                result[ch.idx] = self.read_pv_sccm(ch.idx)
        return result

    # ── 밸브 제어 (안전 순서 포함) ───────────────────

    def open_channel(self, ch_idx: int):
        """
        채널 가스 ON: VA밸브 → 딜레이 → 솔밸브 순서
        (MFC setpoint는 별도로 set_mfc_setpoint_sccm으로 설정)
        """
        ch = self._get_ch(ch_idx)
        if ch is None:
            return
        pin = self._pins.get(str(ch_idx), {})
        va_coil = int(pin.get("va_coil", ch_idx))
        sol_coil = int(pin.get("sol_coil", ch_idx + 8))
        self._drv.write_coil(va_coil, True)
        time.sleep(SOL_DELAY)
        self._drv.write_coil(sol_coil, True)
        logger.debug(f"CH{ch_idx+1} 열기: VA={va_coil}, Sol={sol_coil}")

    def close_channel(self, ch_idx: int):
        """
        채널 가스 OFF: MFC=0 → 딜레이 → 솔밸브 → VA밸브 순서
        """
        pin = self._pins.get(str(ch_idx), {})
        dac_ch = int(pin.get("dac_ch", ch_idx))
        sol_coil = int(pin.get("sol_coil", ch_idx + 8))
        va_coil = int(pin.get("va_coil", ch_idx))
        self._drv.write_dac(dac_ch, 0.0)
        time.sleep(MFC_ZERO_DELAY)
        self._drv.write_coil(sol_coil, False)
        self._drv.write_coil(va_coil, False)
        logger.debug(f"CH{ch_idx+1} 닫기")

    def open_channels_for_step(self, active_ch_indices: list[int]):
        """스텝 실행을 위한 채널들 열기"""
        for idx in active_ch_indices:
            self.open_channel(idx)

    def close_all_channels(self):
        """모든 채널 안전하게 닫기 (MFC→딜레이→밸브)"""
        self.set_all_mfc_zero()
        time.sleep(MFC_ZERO_DELAY)
        for ch in self._channels:
            pin = self._pins.get(str(ch.idx), {})
            sol_coil = int(pin.get("sol_coil", ch.idx + 8))
            va_coil = int(pin.get("va_coil", ch.idx))
            self._drv.write_coil(sol_coil, False)
            self._drv.write_coil(va_coil, False)

    # ── 4-way 밸브 ───────────────────────────────────

    def set_fourway(self, position: str):
        """
        4-way 밸브 설정
        position: "vent" | "chamber"
        """
        value = (position.lower() == "chamber")
        self._drv.write_coil(self._fourway_coil, value)
        logger.debug(f"4-way 밸브: {'Chamber' if value else 'Vent'}")

    def get_fourway(self) -> FourWayPosition:
        state = self._drv.read_coil(self._fourway_coil)
        return FourWayPosition.CHAMBER if state else FourWayPosition.VENT

    # ── 개별 밸브 수동 제어 (HMI에서 클릭 시) ───────

    def toggle_va_valve(self, ch_idx: int) -> bool:
        """VA 밸브 토글. 새 상태 반환."""
        pin = self._pins.get(str(ch_idx), {})
        coil = int(pin.get("va_coil", ch_idx))
        current = self._drv.read_coil(coil)
        new_state = not current
        self._drv.write_coil(coil, new_state)
        return new_state

    def toggle_sol_valve(self, ch_idx: int) -> bool:
        """솔밸브 토글. 새 상태 반환."""
        pin = self._pins.get(str(ch_idx), {})
        coil = int(pin.get("sol_coil", ch_idx + 8))
        current = self._drv.read_coil(coil)
        new_state = not current
        self._drv.write_coil(coil, new_state)
        return new_state

    def get_va_state(self, ch_idx: int) -> bool:
        pin = self._pins.get(str(ch_idx), {})
        coil = int(pin.get("va_coil", ch_idx))
        return self._drv.read_coil(coil)

    def get_sol_state(self, ch_idx: int) -> bool:
        pin = self._pins.get(str(ch_idx), {})
        coil = int(pin.get("sol_coil", ch_idx + 8))
        return self._drv.read_coil(coil)

    # ── 비상 정지 ─────────────────────────────────────

    def emergency_stop(self):
        """즉시 모든 것 닫기 (순서 무시, 속도 우선)"""
        logger.critical("비상 정지 실행")
        # DAC 전부 0
        for i in range(8):
            try:
                self._drv.write_dac(i, 0.0)
            except Exception:
                pass
        # 코일 전부 OFF
        for addr in range(32):
            try:
                self._drv.write_coil(addr, False)
            except Exception:
                pass

    # ── 채널 상태 스냅샷 ──────────────────────────────

    def snapshot_channel_states(self) -> dict[int, ChannelState]:
        """현재 모든 채널 상태 읽기 (UI 업데이트용)"""
        result = {}
        pvs = self.read_all_pv()
        for ch in self._channels:
            va = self.get_va_state(ch.idx)
            sol = self.get_sol_state(ch.idx)
            result[ch.idx] = ChannelState(
                pv_sccm=pvs.get(ch.idx, 0.0),
                sv_sccm=0.0,   # sv는 engine이 별도 관리
                va_open=va,
                sol_open=sol,
            )
        return result

    # ── 내부 유틸 ─────────────────────────────────────

    def _get_ch(self, ch_idx: int) -> Optional[ChannelConfig]:
        for ch in self._channels:
            if ch.idx == ch_idx:
                return ch
        return None

    def update_channels(self, channels: list[ChannelConfig]):
        """설정 변경 시 채널 목록 업데이트"""
        self._channels = channels
