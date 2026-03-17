"""
drivers/real_driver.py
실제 하드웨어 드라이버 (Modbus TCP + NI-DAQ)

사용 방법:
  1. pip install pymodbus nidaqmx
  2. hardware.json에서 driver_type = "real"로 변경
  3. main.py build_app()에서 RealDriver 주석 해제

구조:
  - PLC (Modbus TCP): 솔밸브 ON/OFF, 4-way 밸브 제어
  - NI-DAQ (or 유사 DAQ): ADC(MFC PV 읽기), DAC(MFC setpoint 쓰기)
  - MFC 밸브 강제 Open/Close: PLC 디지털 출력으로 Pin1 제어

주의:
  - pymodbus, nidaqmx가 설치되지 않으면 임포트 오류 발생
  - 하드웨어가 없으면 connect() 실패 → MockDriver로 자동 폴백 처리 권장
"""
from __future__ import annotations
import logging
import threading
from typing import Optional

from drivers.base_driver import BaseDriver

logger = logging.getLogger(__name__)

NUM_CH = 8
NUM_COILS = 32


class RealDriver(BaseDriver):
    """
    실제 하드웨어 드라이버

    hw_config 예시 (hardware.json):
    {
      "plc": {"host": "192.168.1.100", "port": 502, "timeout_sec": 3},
      "adc": {"device": "Dev1", "channels": ["ai0",...], "v_min": 0, "v_max": 5},
      "dac": {"device": "Dev1", "channels": ["ao0",...], "v_min": 0, "v_max": 5}
    }
    """

    def __init__(self, hw_config: dict):
        self._cfg = hw_config
        self._lock = threading.Lock()
        self._connected = False

        # Modbus 클라이언트 (pymodbus)
        self._modbus = None

        # NI-DAQ 태스크 (nidaqmx)
        self._adc_task = None
        self._dac_task = None

        # 채널 캐시 (마지막 쓴 값)
        self._dac_cache = [0.0] * NUM_CH
        self._coil_cache = [False] * NUM_COILS

    # ── 연결 ──────────────────────────────────────────

    def connect(self) -> bool:
        try:
            ok_plc = self._connect_plc()
            ok_daq = self._connect_daq()
            self._connected = ok_plc and ok_daq
            if self._connected:
                logger.info("[RealDriver] 연결 성공 (PLC + DAQ)")
            else:
                logger.error("[RealDriver] 연결 실패")
            return self._connected
        except Exception as e:
            logger.error(f"[RealDriver] 연결 오류: {e}")
            return False

    def _connect_plc(self) -> bool:
        """Modbus TCP PLC 연결"""
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError:
            logger.warning("pymodbus 미설치. 'pip install pymodbus'")
            return False

        plc_cfg = self._cfg.get("plc", {})
        host    = plc_cfg.get("host", "192.168.1.100")
        port    = plc_cfg.get("port", 502)
        timeout = plc_cfg.get("timeout_sec", 3)

        try:
            self._modbus = ModbusTcpClient(host=host, port=port, timeout=timeout)
            if not self._modbus.connect():
                logger.error(f"PLC 연결 실패: {host}:{port}")
                return False
            logger.info(f"PLC 연결: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"PLC 연결 오류: {e}")
            return False

    def _connect_daq(self) -> bool:
        """NI-DAQ ADC/DAC 초기화"""
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, TerminalConfiguration
        except ImportError:
            logger.warning("nidaqmx 미설치. 'pip install nidaqmx'")
            return False

        adc_cfg = self._cfg.get("adc", {})
        dac_cfg = self._cfg.get("dac", {})
        device  = adc_cfg.get("device", "Dev1")
        adc_chs = adc_cfg.get("channels", [f"ai{i}" for i in range(NUM_CH)])
        dac_chs = dac_cfg.get("channels", [f"ao{i}" for i in range(NUM_CH)])
        v_min   = adc_cfg.get("v_min", 0.0)
        v_max   = adc_cfg.get("v_max", 5.0)

        try:
            # ADC 태스크
            self._adc_task = nidaqmx.Task("MFC_ADC")
            for ch in adc_chs:
                self._adc_task.ai_channels.add_ai_voltage_chan(
                    f"{device}/{ch}", min_val=v_min, max_val=v_max)
            self._adc_task.timing.cfg_samp_clk_timing(
                rate=10, sample_mode=AcquisitionType.FINITE, samps_per_chan=1)

            # DAC 태스크
            self._dac_task = nidaqmx.Task("MFC_DAC")
            for ch in dac_chs:
                self._dac_task.ao_channels.add_ao_voltage_chan(
                    f"{device}/{ch}", min_val=0.0, max_val=v_max)

            logger.info(f"NI-DAQ 연결: {device}, ADC {len(adc_chs)}ch, DAC {len(dac_chs)}ch")
            return True
        except Exception as e:
            logger.error(f"NI-DAQ 초기화 오류: {e}")
            return False

    def disconnect(self):
        if self._modbus:
            try:
                self._modbus.close()
            except Exception:
                pass
        if self._adc_task:
            try:
                self._adc_task.close()
            except Exception:
                pass
        if self._dac_task:
            try:
                self._dac_task.close()
            except Exception:
                pass
        self._connected = False
        logger.info("[RealDriver] 연결 해제")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── DAC ───────────────────────────────────────────

    def write_dac(self, ch: int, voltage: float):
        if not 0 <= ch < NUM_CH:
            raise IndexError(f"DAC 채널 범위 초과: {ch}")
        v = max(0.0, min(5.0, voltage))
        with self._lock:
            self._dac_cache[ch] = v
            if self._dac_task:
                try:
                    self._dac_task.write(self._dac_cache[:NUM_CH])
                except Exception as e:
                    logger.error(f"DAC 쓰기 오류 ch{ch}: {e}")

    def write_dac_all(self, voltages: list[float]):
        with self._lock:
            for i, v in enumerate(voltages[:NUM_CH]):
                self._dac_cache[i] = max(0.0, min(5.0, v))
            if self._dac_task:
                try:
                    self._dac_task.write(self._dac_cache[:NUM_CH])
                except Exception as e:
                    logger.error(f"DAC 전체 쓰기 오류: {e}")

    # ── ADC ───────────────────────────────────────────

    def read_adc(self, ch: int) -> float:
        if not 0 <= ch < NUM_CH:
            raise IndexError(f"ADC 채널 범위 초과: {ch}")
        values = self.read_adc_all()
        return values[ch] if ch < len(values) else 0.0

    def read_adc_all(self) -> list[float]:
        if self._adc_task is None:
            return [0.0] * NUM_CH
        with self._lock:
            try:
                data = self._adc_task.read(number_of_samples_per_channel=1)
                # nidaqmx returns list of lists for multi-channel
                if isinstance(data[0], list):
                    return [float(ch_data[0]) for ch_data in data]
                return [float(v) for v in data]
            except Exception as e:
                logger.error(f"ADC 읽기 오류: {e}")
                return [0.0] * NUM_CH

    # ── 코일 ──────────────────────────────────────────

    def write_coil(self, addr: int, value: bool):
        if not 0 <= addr < NUM_COILS:
            raise IndexError(f"코일 주소 범위 초과: {addr}")
        with self._lock:
            self._coil_cache[addr] = value
            if self._modbus:
                try:
                    self._modbus.write_coil(addr, value)
                except Exception as e:
                    logger.error(f"코일 쓰기 오류 addr{addr}: {e}")

    def read_coil(self, addr: int) -> bool:
        if not 0 <= addr < NUM_COILS:
            raise IndexError(f"코일 주소 범위 초과: {addr}")
        if self._modbus:
            try:
                with self._lock:
                    result = self._modbus.read_coils(addr, 1)
                    if result and not result.isError():
                        return bool(result.bits[0])
            except Exception as e:
                logger.error(f"코일 읽기 오류 addr{addr}: {e}")
        # fallback: 캐시
        return self._coil_cache[addr]

    def read_coils(self, addr: int, count: int) -> list[bool]:
        if self._modbus:
            try:
                with self._lock:
                    result = self._modbus.read_coils(addr, count)
                    if result and not result.isError():
                        return [bool(b) for b in result.bits[:count]]
            except Exception as e:
                logger.error(f"코일 다중 읽기 오류: {e}")
        return list(self._coil_cache[addr:addr + count])
