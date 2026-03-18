"""
engine/alarm_manager.py
알람 생성/관리 + 파일 로깅

PySide6 제거 → 콜백 기반 이벤트 시스템
로그 파일: data/logs/YYYY-MM-DD_system.log
"""
from __future__ import annotations
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.models import Alarm, AlarmLevel

logger = logging.getLogger(__name__)


class AlarmManager:
    """알람 관리 + 콜백 기반 알림"""

    def __init__(self, log_dir: Path):
        self._log_dir = log_dir
        self._active_alarms: list[Alarm] = []
        self._history: list[Alarm] = []
        self._file_logger: logging.Logger | None = None
        self._callbacks: list[Callable] = []
        self._setup_file_logger()

    def _setup_file_logger(self):
        """날짜별 파일 로거 설정"""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_path = self._log_dir / f"{today}_system.log"

        self._file_logger = logging.getLogger("gas_control.events")
        self._file_logger.setLevel(logging.DEBUG)
        self._file_logger.propagate = False

        if not self._file_logger.handlers:
            handler = logging.handlers.TimedRotatingFileHandler(
                log_path, when="midnight", backupCount=30, encoding="utf-8"
            )
            fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(fmt)
            self._file_logger.addHandler(handler)

    # ── 콜백 등록 ────────────────────────────────────

    def on_alarm(self, callback: Callable[[Alarm], None]):
        """알람 발생 시 호출될 콜백 등록"""
        self._callbacks.append(callback)

    def _notify(self, alarm: Alarm):
        """등록된 콜백에 알람 전달"""
        for cb in self._callbacks:
            try:
                cb(alarm)
            except Exception as e:
                logger.error(f"알람 콜백 오류: {e}")

    # ── 알람 발생 ────────────────────────────────────

    def raise_alarm(self, level: AlarmLevel, message: str, source: str = "System"):
        """알람 발생"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alarm = Alarm(level=level, message=message, source=source, timestamp=ts)

        self._history.append(alarm)
        if level in (AlarmLevel.ERROR, AlarmLevel.CRITICAL):
            self._active_alarms.append(alarm)

        # 파일 로깅
        log_msg = f"[{source}] {message}"
        if level == AlarmLevel.INFO:
            self._file_logger.info(log_msg)
        elif level == AlarmLevel.WARNING:
            self._file_logger.warning(log_msg)
        elif level == AlarmLevel.ERROR:
            self._file_logger.error(log_msg)
        elif level == AlarmLevel.CRITICAL:
            self._file_logger.critical(log_msg)

        # 콜백 알림
        self._notify(alarm)
        logger.debug(f"알람: [{level.value}] {source}: {message}")

    def info(self, message: str, source: str = "System"):
        self.raise_alarm(AlarmLevel.INFO, message, source)

    def warning(self, message: str, source: str = "System"):
        self.raise_alarm(AlarmLevel.WARNING, message, source)

    def error(self, message: str, source: str = "System"):
        self.raise_alarm(AlarmLevel.ERROR, message, source)

    def critical(self, message: str, source: str = "System"):
        self.raise_alarm(AlarmLevel.CRITICAL, message, source)

    def clear_active(self):
        """활성 알람 해제"""
        self._active_alarms.clear()

    @property
    def has_active_alarm(self) -> bool:
        return len(self._active_alarms) > 0

    @property
    def history(self) -> list[Alarm]:
        return list(self._history)

    @property
    def active_alarms(self) -> list[Alarm]:
        return list(self._active_alarms)
