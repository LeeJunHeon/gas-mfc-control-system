"""
ui/log_panel.py
로그 패널 - 실시간 이벤트 로그 + CSV 내보내기
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor

from app.models import Alarm, AlarmLevel

logger = logging.getLogger(__name__)

LEVEL_COLORS = {
    AlarmLevel.INFO:     "#a0c0e0",
    AlarmLevel.WARNING:  "#f39c12",
    AlarmLevel.ERROR:    "#e74c3c",
    AlarmLevel.CRITICAL: "#ff0000",
}

MAX_LINES = 2000


class LogPanel(QWidget):
    def __init__(self, log_dir: Path, parent=None):
        super().__init__(parent)
        self._log_dir = log_dir
        self._all_records: list[tuple[AlarmLevel, str]] = []
        self._filter_level = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 툴바
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("레벨 필터:"))
        self._cmb_filter = QComboBox()
        self._cmb_filter.addItems(["전체", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self._cmb_filter.setFixedWidth(110)
        self._cmb_filter.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self._cmb_filter)

        toolbar.addStretch(1)

        btn_clear = QPushButton("지우기")
        btn_clear.setMaximumWidth(70)
        btn_clear.clicked.connect(self._clear)
        toolbar.addWidget(btn_clear)

        btn_export = QPushButton("CSV 내보내기")
        btn_export.setMaximumWidth(110)
        btn_export.clicked.connect(self._export_csv)
        toolbar.addWidget(btn_export)

        root.addLayout(toolbar)

        # 로그 텍스트
        self._text = QPlainTextEdit()
        self._text.setObjectName("log_view")
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(MAX_LINES)
        root.addWidget(self._text)

    def on_alarm(self, alarm: Alarm):
        """AlarmManager 시그널 수신"""
        self._all_records.append((alarm.level, alarm.to_log_line()))
        self._append_line(alarm.level, alarm.to_log_line())

    def _append_line(self, level: AlarmLevel, line: str):
        # 현재 필터 적용
        if self._filter_level and level != self._filter_level:
            return
        color = LEVEL_COLORS.get(level, "#a0a0c0")
        # HTML 컬러로 추가
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(line + "\n")
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def _apply_filter(self, text: str):
        level_map = {
            "INFO": AlarmLevel.INFO,
            "WARNING": AlarmLevel.WARNING,
            "ERROR": AlarmLevel.ERROR,
            "CRITICAL": AlarmLevel.CRITICAL,
        }
        self._filter_level = level_map.get(text)
        self._text.clear()
        for lvl, line in self._all_records:
            self._append_line(lvl, line)

    def _clear(self):
        self._text.clear()
        self._all_records.clear()

    def _export_csv(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default = str(self._log_dir / f"log_export_{ts}.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "로그 내보내기", default, "CSV (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write("레벨,메시지\n")
                    for lvl, line in self._all_records:
                        f.write(f"{lvl.value},{line}\n")
                logger.info(f"로그 내보내기 완료: {path}")
            except Exception as e:
                logger.error(f"로그 내보내기 실패: {e}")
