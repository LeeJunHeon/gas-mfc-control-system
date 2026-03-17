"""
drivers/mock_driver.py
시뮬레이션 드라이버 - 실제 하드웨어 없이 동작 테스트용

특징:
- MFC 1차 지연 응답 시뮬레이션 (τ=5초)
- ±0.3% FS 랜덤 노이즈
- 밸브 상태 논리 추적
- 백그라운드 스레드에서 100ms 주기로 상태 업데이트
"""
from __future__ import annotations
import math
import random
import threading
import time
import logging
from dataclasses import dataclass, field

from drivers.base_driver import BaseDriver

logger = logging.getLogger(__name__)

NUM_CH = 8          # 채널 수
NUM_COILS = 32      # 코일(디지털출력) 수


@dataclass
class _MfcState:
    """채널 1개의 시뮬레이션 상태"""
    setpoint_v: float = 0.0     # DAC 설정 전압
    current_v: float = 0.0      # 현재 시뮬레이션 전압
    full_scale_sccm: float = 2000.0
    tau: float = 5.0            # 1차 지연 시상수 (초)
    noise_pct: float = 0.003    # FS 대비 노이즈 비율

    def update(self, dt: float) -> float:
        """dt 초 경과 후 PV 업데이트. 반환값 = 현재 전압"""
        # 1차 지연 응답
        alpha = 1.0 - math.exp(-dt / self.tau)
        self.current_v += alpha * (self.setpoint_v - self.current_v)
        # 노이즈 추가 (0 근처에서는 노이즈 작게)
        noise_scale = self.noise_pct * 5.0 * max(0.1, self.setpoint_v / 5.0)
        noise = random.gauss(0, noise_scale)
        return max(0.0, self.current_v + noise)


class MockDriver(BaseDriver):
    """모의 드라이버 구현"""

    def __init__(self, full_scales: list[float] = None):
        """
        full_scales: 각 채널의 FS(sccm). None이면 모두 2000sccm.
        """
        n_fs = full_scales or [2000.0] * NUM_CH
        self._mfc: list[_MfcState] = [
            _MfcState(full_scale_sccm=fs) for fs in n_fs
        ]
        self._coils: list[bool] = [False] * NUM_COILS
        self._lock = threading.Lock()
        self._connected = False
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    # ── 연결 ──────────────────────────────────────────

    def connect(self) -> bool:
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._update_loop, daemon=True, name="MockDriverUpdate"
        )
        self._thread.start()
        self._connected = True
        logger.info("[MockDriver] 연결됨 (시뮬레이션 모드)")
        return True

    def disconnect(self):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._connected = False
        logger.info("[MockDriver] 연결 해제")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── 업데이트 루프 ─────────────────────────────────

    def _update_loop(self):
        """100ms마다 각 채널 PV 업데이트"""
        dt = 0.1
        while not self._stop_evt.wait(dt):
            with self._lock:
                for state in self._mfc:
                    state.update(dt)

    # ── DAC ───────────────────────────────────────────

    def write_dac(self, ch: int, voltage: float):
        if not 0 <= ch < NUM_CH:
            raise IndexError(f"DAC 채널 범위 초과: {ch}")
        v = max(0.0, min(5.0, voltage))
        with self._lock:
            self._mfc[ch].setpoint_v = v

    def write_dac_all(self, voltages: list[float]):
        for i, v in enumerate(voltages[:NUM_CH]):
            self.write_dac(i, v)

    # ── ADC ───────────────────────────────────────────

    def read_adc(self, ch: int) -> float:
        if not 0 <= ch < NUM_CH:
            raise IndexError(f"ADC 채널 범위 초과: {ch}")
        with self._lock:
            return self._mfc[ch].update(0)   # 현재 시뮬레이션 값 반환

    def read_adc_all(self) -> list[float]:
        with self._lock:
            return [s.update(0) for s in self._mfc]

    # ── 코일 (밸브) ───────────────────────────────────

    def write_coil(self, addr: int, value: bool):
        if not 0 <= addr < NUM_COILS:
            raise IndexError(f"코일 주소 범위 초과: {addr}")
        with self._lock:
            self._coils[addr] = value

    def read_coil(self, addr: int) -> bool:
        if not 0 <= addr < NUM_COILS:
            raise IndexError(f"코일 주소 범위 초과: {addr}")
        with self._lock:
            return self._coils[addr]

    def read_coils(self, addr: int, count: int) -> list[bool]:
        with self._lock:
            return list(self._coils[addr:addr + count])

    # ── 테스트용 유틸 ─────────────────────────────────

    def get_raw_state(self) -> dict:
        """디버그용 내부 상태 조회"""
        with self._lock:
            return {
                "mfc": [
                    {"setpoint_v": s.setpoint_v, "current_v": s.current_v}
                    for s in self._mfc
                ],
                "coils": list(self._coils),
            }
