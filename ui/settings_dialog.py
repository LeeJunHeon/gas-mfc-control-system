"""
ui/settings_dialog.py
설정 다이얼로그 - 채널 설정 / 하드웨어 설정
"""
from __future__ import annotations
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLabel, QLineEdit, QCheckBox, QComboBox,
    QGroupBox, QSpinBox, QDialogButtonBox, QFormLayout
)
from PySide6.QtCore import Signal

from app.config import AppConfig

logger = logging.getLogger(__name__)

C_NAME=0; C_GAS=1; C_SOURCE=2; C_FS=3; C_CF=4; C_BAL=5; C_COLOR=6; C_ENABLE=7


class SettingsDialog(QDialog):
    settings_applied = Signal(object)  # AppConfig

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._cfg = config
        self.setWindowTitle("설정")
        self.setMinimumSize(820, 520)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── 채널 탭 ──────────────────────────────────
        ch_tab = QWidget()
        ch_layout = QVBoxLayout(ch_tab)
        hint = QLabel("※ CF: HORIBA 공식 테이블 기준. 없는 가스는 제조사 문의 또는 실측 필요.")
        hint.setStyleSheet("color:#f39c12;font-size:10px;")
        ch_layout.addWidget(hint)

        self._ch_table = QTableWidget(8, 8)
        self._ch_table.setHorizontalHeaderLabels([
            "채널 이름", "가스 종류", "Source 농도\n(ppm, 0=pure)",
            "FS (sccm)", "CF", "Balance\nGas", "색상(hex)", "활성화"])
        hdr = self._ch_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        self._ch_table.setAlternatingRowColors(True)
        for col, w in [(C_NAME,110),(C_GAS,90),(C_SOURCE,110),
                       (C_FS,90),(C_CF,70),(C_BAL,65),(C_COLOR,80)]:
            self._ch_table.setColumnWidth(col, w)
        ch_layout.addWidget(self._ch_table)

        btn_row = QHBoxLayout()
        btn_auto_cf = QPushButton("선택 가스로 CF 자동 채우기")
        btn_auto_cf.clicked.connect(self._auto_fill_cf)
        btn_row.addWidget(btn_auto_cf)
        btn_row.addStretch(1)
        ch_layout.addLayout(btn_row)
        tabs.addTab(ch_tab, "채널 설정")

        # ── 하드웨어 탭 ──────────────────────────────
        hw_tab = QWidget()
        hw_layout = QVBoxLayout(hw_tab)

        drv_grp = QGroupBox("드라이버")
        dg = QFormLayout(drv_grp)
        self._cmb_driver = QComboBox()
        self._cmb_driver.addItems(["mock", "real"])
        dg.addRow("드라이버 타입:", self._cmb_driver)
        dg.addRow("", QLabel("mock=시뮬레이션 / real=실제 장비 (별도 드라이버 필요)"))
        hw_layout.addWidget(drv_grp)

        plc_grp = QGroupBox("PLC (Modbus TCP)")
        pg = QFormLayout(plc_grp)
        self._edit_host = QLineEdit()
        self._edit_host.setPlaceholderText("192.168.1.100")
        self._spin_port = QSpinBox(); self._spin_port.setRange(1, 65535)
        self._spin_timeout = QSpinBox(); self._spin_timeout.setRange(1,30); self._spin_timeout.setSuffix(" 초")
        pg.addRow("Host IP:", self._edit_host)
        pg.addRow("Port:", self._spin_port)
        pg.addRow("Timeout:", self._spin_timeout)
        hw_layout.addWidget(plc_grp)

        tim_grp = QGroupBox("타이밍")
        tg = QFormLayout(tim_grp)
        self._spin_warmup = QSpinBox(); self._spin_warmup.setRange(0,3600); self._spin_warmup.setSuffix(" 초")
        self._spin_purge  = QSpinBox(); self._spin_purge.setRange(0,600);   self._spin_purge.setSuffix(" 초")
        tg.addRow("워밍업 시간:", self._spin_warmup)
        tg.addRow("퍼지 시간:",   self._spin_purge)
        hw_layout.addWidget(tim_grp)
        hw_layout.addStretch(1)
        tabs.addTab(hw_tab, "하드웨어 설정")

        root.addWidget(tabs)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply)
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        root.addWidget(btn_box)

    def _load_values(self):
        for row, ch in enumerate(self._cfg.channels):
            self._ch_table.setItem(row, C_NAME,   QTableWidgetItem(ch.name))
            gas_c = QComboBox(); gas_c.addItems(self._cfg.gas_names())
            idx = gas_c.findText(ch.gas_name)
            if idx >= 0: gas_c.setCurrentIndex(idx)
            gas_c.setStyleSheet("background:#12122a;color:#e0e0e0;")
            self._ch_table.setCellWidget(row, C_GAS, gas_c)
            self._ch_table.setItem(row, C_SOURCE, QTableWidgetItem(str(ch.source_conc_ppm)))
            self._ch_table.setItem(row, C_FS,     QTableWidgetItem(str(ch.full_scale_sccm)))
            self._ch_table.setItem(row, C_CF,     QTableWidgetItem(str(ch.cf)))
            chk_bal = QCheckBox(); chk_bal.setChecked(ch.is_balance)
            chk_bal.setStyleSheet("margin-left:18px;")
            self._ch_table.setCellWidget(row, C_BAL, chk_bal)
            self._ch_table.setItem(row, C_COLOR,  QTableWidgetItem(ch.color))
            chk_en = QCheckBox(); chk_en.setChecked(ch.enabled)
            chk_en.setStyleSheet("margin-left:18px;")
            self._ch_table.setCellWidget(row, C_ENABLE, chk_en)

        hw = self._cfg.hardware
        self._cmb_driver.setCurrentText(hw.get("driver_type","mock"))
        plc = hw.get("plc", {})
        self._edit_host.setText(plc.get("host","192.168.1.100"))
        self._spin_port.setValue(plc.get("port",502))
        self._spin_timeout.setValue(plc.get("timeout_sec",3))
        self._spin_warmup.setValue(hw.get("warmup_sec",300))
        self._spin_purge.setValue(hw.get("purge_duration_sec",30))

    def _apply(self):
        for row, ch in enumerate(self._cfg.channels):
            item = self._ch_table.item(row, C_NAME)
            if item: ch.name = item.text()
            gas_w = self._ch_table.cellWidget(row, C_GAS)
            if gas_w: ch.gas_name = gas_w.currentText()
            for attr, col in [("source_conc_ppm", C_SOURCE),
                               ("full_scale_sccm", C_FS), ("cf", C_CF)]:
                item = self._ch_table.item(row, col)
                if item:
                    try: setattr(ch, attr, float(item.text()))
                    except ValueError: pass
            bal_w = self._ch_table.cellWidget(row, C_BAL)
            if bal_w: ch.is_balance = bal_w.isChecked()
            color_item = self._ch_table.item(row, C_COLOR)
            if color_item: ch.color = color_item.text()
            en_w = self._ch_table.cellWidget(row, C_ENABLE)
            if en_w: ch.enabled = en_w.isChecked()

        hw = self._cfg.hardware
        hw["driver_type"] = self._cmb_driver.currentText()
        hw["plc"]["host"] = self._edit_host.text()
        hw["plc"]["port"] = self._spin_port.value()
        hw["plc"]["timeout_sec"] = self._spin_timeout.value()
        hw["warmup_sec"] = self._spin_warmup.value()
        hw["purge_duration_sec"] = self._spin_purge.value()

        self._cfg.save_channel_config()
        self._cfg.save_hardware_config()
        self.settings_applied.emit(self._cfg)

    def _on_ok(self):
        self._apply()
        self.accept()

    def _auto_fill_cf(self):
        for row in range(self._ch_table.rowCount()):
            gas_w = self._ch_table.cellWidget(row, C_GAS)
            if gas_w:
                cf = self._cfg.get_cf(gas_w.currentText())
                self._ch_table.setItem(row, C_CF, QTableWidgetItem(str(cf)))
