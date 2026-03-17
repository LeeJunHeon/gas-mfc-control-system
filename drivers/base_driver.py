"""
drivers/base_driver.py
하드웨어 드라이버 추상 베이스 클래스

실제 드라이버 구현 시 이 클래스를 상속해서 만들면 됨.
(pymodbus, nidaqmx 등)
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseDriver(ABC):
    """
    드라이버 인터페이스
    모든 메서드는 스레드 안전(thread-safe)하게 구현해야 함.
    """

    @abstractmethod
    def connect(self) -> bool:
        """연결. 성공 시 True."""
        ...

    @abstractmethod
    def disconnect(self):
        """연결 해제."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """연결 상태."""
        ...

    # ── DAC (MFC setpoint 쓰기) ───────────────────────

    @abstractmethod
    def write_dac(self, ch: int, voltage: float):
        """
        DAC 채널에 전압 출력 (0~5V)
        ch: 0-based 채널 인덱스
        voltage: 출력 전압 (V)
        """
        ...

    @abstractmethod
    def write_dac_all(self, voltages: list[float]):
        """전체 DAC 채널 한번에 쓰기"""
        ...

    # ── ADC (MFC PV 읽기) ─────────────────────────────

    @abstractmethod
    def read_adc(self, ch: int) -> float:
        """
        ADC 채널 전압 읽기 (0~5V)
        Returns: 전압값 (V)
        """
        ...

    @abstractmethod
    def read_adc_all(self) -> list[float]:
        """전체 ADC 채널 읽기"""
        ...

    # ── PLC 디지털 출력 (밸브 제어) ──────────────────

    @abstractmethod
    def write_coil(self, addr: int, value: bool):
        """
        PLC 코일(디지털 출력) 쓰기
        addr: Modbus 코일 주소
        value: True=ON, False=OFF
        """
        ...

    @abstractmethod
    def read_coil(self, addr: int) -> bool:
        """PLC 코일 상태 읽기"""
        ...

    @abstractmethod
    def read_coils(self, addr: int, count: int) -> list[bool]:
        """여러 코일 한번에 읽기"""
        ...
