"""
app/config.py
설정 파일 로드/저장 관리 (channel_config.json, hardware.json 등)
"""
from __future__ import annotations
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.models import ChannelConfig

logger = logging.getLogger(__name__)

# 프로젝트 루트 = 이 파일의 2단계 상위
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
RECIPE_DIR = DATA_DIR / "recipes"
LOG_DIR = DATA_DIR / "logs"


class AppConfig:
    """앱 전체 설정 관리"""

    def __init__(self):
        # 디렉터리 보장
        for d in [CONFIG_DIR, RECIPE_DIR, LOG_DIR]:
            d.mkdir(parents=True, exist_ok=True)

        self.channels: list[ChannelConfig] = []
        self.gas_library: dict[str, float] = {}   # {가스명: CF}
        self.hardware: dict = {}

        self._load_gas_library()
        self._load_channel_config()
        self._load_hardware_config()

    # ── 가스 라이브러리 ──────────────────────────────

    def _load_gas_library(self):
        path = CONFIG_DIR / "gas_library.json"
        if not path.exists():
            self._create_default_gas_library(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.gas_library = {g["name"]: g["cf"] for g in data.get("gases", [])}
        logger.info(f"가스 라이브러리 로드: {len(self.gas_library)}종")

    def _create_default_gas_library(self, path: Path):
        default = {
            "gases": [
                {"name": "N2",   "cf": 1.000, "mol_weight": 28.0,  "note": "기준 가스"},
                {"name": "Air",  "cf": 1.000, "mol_weight": 28.9,  "note": ""},
                {"name": "O2",   "cf": 0.980, "mol_weight": 32.0,  "note": ""},
                {"name": "H2",   "cf": 1.400, "mol_weight": 2.0,   "note": ""},
                {"name": "He",   "cf": 1.454, "mol_weight": 4.0,   "note": ""},
                {"name": "Ar",   "cf": 1.415, "mol_weight": 39.9,  "note": ""},
                {"name": "CO2",  "cf": 0.740, "mol_weight": 44.0,  "note": ""},
                {"name": "CO",   "cf": 1.000, "mol_weight": 28.0,  "note": ""},
                {"name": "CH4",  "cf": 0.717, "mol_weight": 16.0,  "note": ""},
                {"name": "NO",   "cf": 1.010, "mol_weight": 30.0,  "note": ""},
                {"name": "NO2",  "cf": 1.010, "mol_weight": 46.0,  "note": "실측 보정 권장"},
                {"name": "NH3",  "cf": 0.730, "mol_weight": 17.0,  "note": ""},
                {"name": "H2S",  "cf": 0.840, "mol_weight": 34.1,  "note": ""},
                {"name": "SO2",  "cf": 0.690, "mol_weight": 64.1,  "note": ""},
                {"name": "SF6",  "cf": 0.270, "mol_weight": 146.1, "note": ""},
                {"name": "C3H8", "cf": 0.640, "mol_weight": 44.1,  "note": "프로판"},
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        logger.info("기본 가스 라이브러리 생성")

    def get_cf(self, gas_name: str) -> float:
        return self.gas_library.get(gas_name, 1.0)

    def gas_names(self) -> list[str]:
        return list(self.gas_library.keys())

    # ── 채널 설정 ─────────────────────────────────────

    def _load_channel_config(self):
        path = CONFIG_DIR / "channel_config.json"
        if not path.exists():
            self._create_default_channel_config(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.channels = [ChannelConfig.from_dict(c) for c in data.get("channels", [])]
        logger.info(f"채널 설정 로드: {len(self.channels)}채널")

    def _create_default_channel_config(self, path: Path):
        default_channels = [
            {"idx": 0, "name": "Air 1",  "gas_name": "Air",  "source_conc_ppm": 0,    "full_scale_sccm": 2000, "cf": 1.000, "is_balance": True,  "enabled": True,  "color": "#3498db"},
            {"idx": 1, "name": "Air 2",  "gas_name": "Air",  "source_conc_ppm": 0,    "full_scale_sccm": 2000, "cf": 1.000, "is_balance": True,  "enabled": True,  "color": "#3498db"},
            {"idx": 2, "name": "Air 3",  "gas_name": "Air",  "source_conc_ppm": 0,    "full_scale_sccm": 2000, "cf": 1.000, "is_balance": False, "enabled": True,  "color": "#2980b9"},
            {"idx": 3, "name": "Air 4",  "gas_name": "Air",  "source_conc_ppm": 0,    "full_scale_sccm": 2000, "cf": 1.000, "is_balance": False, "enabled": True,  "color": "#2980b9"},
            {"idx": 4, "name": "Gas 1",  "gas_name": "NO2",  "source_conc_ppm": 10,   "full_scale_sccm": 2000, "cf": 1.010, "is_balance": False, "enabled": True,  "color": "#e74c3c"},
            {"idx": 5, "name": "Gas 2",  "gas_name": "NO",   "source_conc_ppm": 100,  "full_scale_sccm": 200,  "cf": 1.010, "is_balance": False, "enabled": True,  "color": "#e67e22"},
            {"idx": 6, "name": "Gas 3",  "gas_name": "N2",   "source_conc_ppm": 0,    "full_scale_sccm": 100,  "cf": 1.000, "is_balance": False, "enabled": False, "color": "#9b59b6"},
            {"idx": 7, "name": "Gas 4",  "gas_name": "N2",   "source_conc_ppm": 0,    "full_scale_sccm": 2000, "cf": 1.000, "is_balance": False, "enabled": False, "color": "#1abc9c"},
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"channels": default_channels}, f, ensure_ascii=False, indent=2)
        logger.info("기본 채널 설정 생성")

    def save_channel_config(self):
        path = CONFIG_DIR / "channel_config.json"
        self._backup(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"channels": [c.to_dict() for c in self.channels]}, f,
                      ensure_ascii=False, indent=2)
        logger.info("채널 설정 저장 완료")

    # ── 하드웨어 설정 ─────────────────────────────────

    def _load_hardware_config(self):
        path = CONFIG_DIR / "hardware.json"
        if not path.exists():
            self._create_default_hardware_config(path)
        with open(path, encoding="utf-8") as f:
            self.hardware = json.load(f)

    def _create_default_hardware_config(self, path: Path):
        default = {
            "driver_type": "mock",   # "mock" | "real" (추후 전환)
            "plc": {
                "type": "modbus_tcp",
                "host": "192.168.1.100",
                "port": 502,
                "timeout_sec": 3
            },
            "adc": {
                "type": "ni_daq",
                "device": "Dev1",
                "channels": ["ai0","ai1","ai2","ai3","ai4","ai5","ai6","ai7"],
                "v_min": 0.0,
                "v_max": 5.0
            },
            "dac": {
                "type": "ni_daq",
                "device": "Dev1",
                "channels": ["ao0","ao1","ao2","ao3","ao4","ao5","ao6","ao7"],
                "v_min": 0.0,
                "v_max": 5.0
            },
            "channel_pins": {
                "0": {"dac_ch": 0, "adc_ch": 0, "va_coil": 0,  "sol_coil": 8},
                "1": {"dac_ch": 1, "adc_ch": 1, "va_coil": 1,  "sol_coil": 9},
                "2": {"dac_ch": 2, "adc_ch": 2, "va_coil": 2,  "sol_coil": 10},
                "3": {"dac_ch": 3, "adc_ch": 3, "va_coil": 3,  "sol_coil": 11},
                "4": {"dac_ch": 4, "adc_ch": 4, "va_coil": 4,  "sol_coil": 12},
                "5": {"dac_ch": 5, "adc_ch": 5, "va_coil": 5,  "sol_coil": 13},
                "6": {"dac_ch": 6, "adc_ch": 6, "va_coil": 6,  "sol_coil": 14},
                "7": {"dac_ch": 7, "adc_ch": 7, "va_coil": 7,  "sol_coil": 15},
            },
            "fourway_coil": 16,
            "purge_duration_sec": 30,
            "warmup_sec": 300,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

    def save_hardware_config(self):
        path = CONFIG_DIR / "hardware.json"
        self._backup(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.hardware, f, ensure_ascii=False, indent=2)
        logger.info("하드웨어 설정 저장 완료")

    # ── 유틸 ──────────────────────────────────────────

    def _backup(self, path: Path):
        if path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = path.with_suffix(f".bak_{ts}")
            shutil.copy(path, bak)

    @property
    def enabled_channels(self) -> list[ChannelConfig]:
        return [c for c in self.channels if c.enabled]

    @property
    def recipe_dir(self) -> Path:
        return RECIPE_DIR

    @property
    def log_dir(self) -> Path:
        return LOG_DIR
