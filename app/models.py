"""
app/models.py
프로그램 전체에서 사용하는 데이터 모델 (dataclass, enum)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ──────────────────────────────────────────
# 상태 열거형
# ──────────────────────────────────────────

class EngineState(Enum):
    IDLE = "대기"
    STEP_PREPARE = "준비 중"
    STEP_MEASURE = "측정 중"
    STOPPING = "정지 중"
    EMERGENCY = "비상 정지"
    PURGING = "퍼지 중"


class AlarmLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class FourWayPosition(Enum):
    VENT = "Vent"
    CHAMBER = "Chamber"


# ──────────────────────────────────────────
# 채널 설정
# ──────────────────────────────────────────

@dataclass
class ChannelConfig:
    """MFC 채널 1개의 설정값"""
    idx: int                        # 0-based 채널 인덱스
    name: str = "CH1"               # 표시 이름 (Air, Gas1, NO2 등)
    gas_name: str = "N2"            # 가스 종류 (CF 조회용)
    source_conc_ppm: float = 0.0    # 실린더 농도 (ppm). 0=pure gas
    full_scale_sccm: float = 2000.0 # MFC 최대 유량 (sccm)
    cf: float = 1.0                 # Correction Factor
    is_balance: bool = False        # True = Air/N2 등 balance gas
    enabled: bool = True            # 채널 활성화 여부
    color: str = "#e74c3c"          # UI 색상 (hex)

    @property
    def is_pure_gas(self) -> bool:
        """source 농도가 0이면 순수 가스 (ppm이 아닌 ratio로 설정)"""
        return self.source_conc_ppm <= 0

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "name": self.name,
            "gas_name": self.gas_name,
            "source_conc_ppm": self.source_conc_ppm,
            "full_scale_sccm": self.full_scale_sccm,
            "cf": self.cf,
            "is_balance": self.is_balance,
            "enabled": self.enabled,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChannelConfig:
        return cls(**d)


# ──────────────────────────────────────────
# 레시피 스텝
# ──────────────────────────────────────────

@dataclass
class RecipeStep:
    """레시피의 한 스텝 (P1, P2, ...)"""
    step_id: str = "P1"
    total_flow_sccm: float = 1000.0
    humidity_pct: float = 0.0
    # {채널 idx: 목표 농도 ppm}. balance 채널은 여기 안 넣음
    gas_targets: dict = field(default_factory=dict)
    prepare_sec: int = 600
    measure_sec: int = 300
    repeat: int = 1
    fourway: str = "vent"           # "vent" | "chamber"

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "total_flow_sccm": self.total_flow_sccm,
            "humidity_pct": self.humidity_pct,
            "gas_targets": {str(k): v for k, v in self.gas_targets.items()},
            "prepare_sec": self.prepare_sec,
            "measure_sec": self.measure_sec,
            "repeat": self.repeat,
            "fourway": self.fourway,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RecipeStep:
        obj = cls(
            step_id=d.get("step_id", "P1"),
            total_flow_sccm=d.get("total_flow_sccm", 1000.0),
            humidity_pct=d.get("humidity_pct", 0.0),
            gas_targets={int(k): v for k, v in d.get("gas_targets", {}).items()},
            prepare_sec=d.get("prepare_sec", 600),
            measure_sec=d.get("measure_sec", 300),
            repeat=d.get("repeat", 1),
            fourway=d.get("fourway", "vent"),
        )
        return obj


# ──────────────────────────────────────────
# 레시피
# ──────────────────────────────────────────

@dataclass
class Recipe:
    """전체 레시피"""
    name: str = "New Recipe"
    schema_version: str = "1.0"
    loop_count: int = 1
    interval_sec: int = 0
    bubbler_temp_c: float = 25.0
    system_pressure_kpa: float = 101.3
    steps: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "loop_count": self.loop_count,
            "interval_sec": self.interval_sec,
            "bubbler_temp_c": self.bubbler_temp_c,
            "system_pressure_kpa": self.system_pressure_kpa,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Recipe:
        r = cls(
            name=d.get("name", "Recipe"),
            schema_version=d.get("schema_version", "1.0"),
            loop_count=d.get("loop_count", 1),
            interval_sec=d.get("interval_sec", 0),
            bubbler_temp_c=d.get("bubbler_temp_c", 25.0),
            system_pressure_kpa=d.get("system_pressure_kpa", 101.3),
        )
        r.steps = [RecipeStep.from_dict(s) for s in d.get("steps", [])]
        return r


# ──────────────────────────────────────────
# 알람
# ──────────────────────────────────────────

@dataclass
class Alarm:
    level: AlarmLevel
    message: str
    source: str = ""
    timestamp: str = ""

    def to_log_line(self) -> str:
        return f"[{self.timestamp}] [{self.level.value}] {self.source}: {self.message}"


# ──────────────────────────────────────────
# 실시간 채널 상태 (런타임용)
# ──────────────────────────────────────────

@dataclass
class ChannelState:
    """런타임 채널 상태 (UI 표시용)"""
    pv_sccm: float = 0.0        # 현재 측정값
    sv_sccm: float = 0.0        # 설정값
    va_open: bool = False       # VA 밸브 상태
    sol_open: bool = False      # 솔밸브 상태


@dataclass
class SystemState:
    """전체 시스템 상태 스냅샷"""
    engine_state: EngineState = EngineState.IDLE
    channels: dict = field(default_factory=dict)  # {idx: ChannelState}
    fourway: FourWayPosition = FourWayPosition.VENT
    current_step: Optional[str] = None
    current_loop: int = 0
    total_loops: int = 1
    elapsed_prepare: int = 0
    total_prepare: int = 0
    elapsed_measure: int = 0
    total_measure: int = 0
