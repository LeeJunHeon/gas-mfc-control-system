"""
ui/recipe_panel.py
레시피 편집 패널

기능:
- P1, P2... 스텝 테이블 편집
- JSON 저장/불러오기
- MFC setpoint 미리보기
- 레시피 Loop Count / Interval 설정
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QGroupBox, QHeaderView, QComboBox,
    QFrame, QSplitter, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush

from app.models import ChannelConfig, Recipe, RecipeStep
from calculation.flow_calculator import FlowCalculator

logger = logging.getLogger(__name__)

# 테이블 고정 컬럼 (가스 컬럼은 동적으로 추가)
COL_STEP      = 0
COL_FLOW      = 1
COL_HUMID     = 2
COL_GAS_START = 3   # 가스 컬럼 시작 (채널 수에 따라 동적)
# COL_GAS_END = COL_GAS_START + n_gas_channels
# 이후: 준비, 측정, 반복, 4-way


class RecipePanel(QWidget):
    """레시피 편집 패널"""

    recipe_loaded = Signal(object)   # Recipe 객체 로드됨

    def __init__(self, channels: list[ChannelConfig],
                 flow_calc: FlowCalculator,
                 recipe_dir: Path,
                 parent=None):
        super().__init__(parent)
        self._channels = channels
        self._calc = flow_calc
        self._recipe_dir = recipe_dir
        self._current_path: Path | None = None
        self._recipe = Recipe()

        self._gas_channels = [c for c in channels if not c.is_balance and c.enabled]
        self._n_gas = len(self._gas_channels)

        self._build_ui()
        self._new_recipe()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 툴바 ─────────────────────────────────────
        toolbar = QHBoxLayout()

        self._lbl_recipe_name = QLineEdit("New Recipe")
        self._lbl_recipe_name.setPlaceholderText("레시피 이름...")
        self._lbl_recipe_name.setFixedWidth(220)
        toolbar.addWidget(QLabel("레시피:"))
        toolbar.addWidget(self._lbl_recipe_name)
        toolbar.addSpacing(10)

        self._btn_new    = QPushButton("New")
        self._btn_open   = QPushButton("Open...")
        self._btn_save   = QPushButton("Save")
        self._btn_saveas = QPushButton("Save As...")
        for btn in [self._btn_new, self._btn_open, self._btn_save, self._btn_saveas]:
            btn.setMaximumWidth(90)
            toolbar.addWidget(btn)

        self._btn_new.clicked.connect(self._new_recipe)
        self._btn_open.clicked.connect(self._open_recipe)
        self._btn_save.clicked.connect(self._save_recipe)
        self._btn_saveas.clicked.connect(self._saveas_recipe)

        toolbar.addStretch(1)
        root.addLayout(toolbar)

        # ── 레시피 설정 (컴팩트) ───────────────────────
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(6)

        cfg_row.addWidget(QLabel("Loop:"))
        self._spin_loop = QSpinBox()
        self._spin_loop.setRange(1, 999)
        self._spin_loop.setValue(1)
        self._spin_loop.setFixedWidth(60)
        cfg_row.addWidget(self._spin_loop)

        cfg_row.addSpacing(8)
        cfg_row.addWidget(QLabel("Interval(s):"))
        self._spin_interval = QSpinBox()
        self._spin_interval.setRange(0, 99999)
        self._spin_interval.setValue(0)
        self._spin_interval.setFixedWidth(70)
        cfg_row.addWidget(self._spin_interval)

        cfg_row.addSpacing(8)
        cfg_row.addWidget(QLabel("버블러(°C):"))
        self._spin_bubbler = QDoubleSpinBox()
        self._spin_bubbler.setRange(0, 80)
        self._spin_bubbler.setValue(25.0)
        self._spin_bubbler.setFixedWidth(65)
        cfg_row.addWidget(self._spin_bubbler)

        cfg_row.addStretch(1)
        root.addLayout(cfg_row)

        # ── 스텝 테이블 ──────────────────────────────
        self._build_table()
        root.addWidget(self._table)

        # ── 테이블 제어 버튼 ─────────────────────────
        table_btns = QHBoxLayout()
        self._btn_add_row    = QPushButton("+ 스텝 추가")
        self._btn_del_row    = QPushButton("- 스텝 삭제")
        self._btn_move_up    = QPushButton("▲ 위로")
        self._btn_move_down  = QPushButton("▼ 아래로")

        for btn in [self._btn_add_row, self._btn_del_row,
                    self._btn_move_up, self._btn_move_down]:
            btn.setMaximumWidth(110)
            table_btns.addWidget(btn)

        self._btn_add_row.clicked.connect(self._add_step)
        self._btn_del_row.clicked.connect(self._delete_step)
        self._btn_move_up.clicked.connect(self._move_up)
        self._btn_move_down.clicked.connect(self._move_down)
        table_btns.addStretch(1)
        root.addLayout(table_btns)

        # ── Setpoint 미리보기 ─────────────────────────
        preview_group = QGroupBox("MFC Setpoint 미리보기 (선택된 스텝)")
        pv_layout = QVBoxLayout(preview_group)
        pv_layout.setContentsMargins(6, 14, 6, 6)
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setFixedHeight(130)
        self._preview_text.setStyleSheet(
            "background: #fafbfc; color: #2c3e50;"
            "font-family: Consolas, monospace; font-size: 11px;"
            "border: 1px solid #bdc3c7; border-radius: 3px;")
        pv_layout.addWidget(self._preview_text)
        root.addWidget(preview_group)

        self._table.currentCellChanged.connect(self._on_selection_changed)

    def _build_table(self):
        """동적 컬럼 테이블 생성"""
        gas_cols = [c.name for c in self._gas_channels]
        headers = (["스텝", "Total Flow\n(sccm)", "Humidity\n(%)"]
                   + [f"{c.name}\n({int(c.source_conc_ppm) if c.source_conc_ppm else 'pure'})"
                      for c in self._gas_channels]
                   + ["준비(s)", "측정(s)", "반복", "4-way"])
        self._n_cols = len(headers)

        self._table = QTableWidget(0, self._n_cols)
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setMinimumHeight(250)

        # 헤더 텍스트 줄바꿈 허용 + 높이 확보
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(40)

        # 선택 행 강조 스타일
        self._table.setStyleSheet(
            "QTableWidget::item:selected {"
            "  background-color: #2980b9;"
            "  color: #ffffff;"
            "}"
        )

        # 컬럼 너비 초기값
        self._table.setColumnWidth(COL_STEP, 50)
        self._table.setColumnWidth(COL_FLOW, 90)
        self._table.setColumnWidth(COL_HUMID, 80)
        for i, _ in enumerate(self._gas_channels):
            self._table.setColumnWidth(COL_GAS_START + i, 75)
        # 준비, 측정, 반복, 4-way 컬럼
        for off, w in enumerate([75, 75, 55, 70]):
            col = COL_GAS_START + self._n_gas + off
            self._table.setColumnWidth(col, w)

    # ── 스텝 테이블 편집 ──────────────────────────────

    def _add_step(self, step: RecipeStep | None = None):
        row = self._table.rowCount()
        self._table.insertRow(row)

        if step is None:
            step = RecipeStep(step_id=f"P{row + 1}")

        self._table.setItem(row, COL_STEP, QTableWidgetItem(step.step_id))
        self._table.setItem(row, COL_FLOW, QTableWidgetItem(str(step.total_flow_sccm)))
        self._table.setItem(row, COL_HUMID, QTableWidgetItem(str(step.humidity_pct)))

        for i, ch in enumerate(self._gas_channels):
            val = step.gas_targets.get(ch.idx, 0.0)
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, COL_GAS_START + i, item)

        tail = COL_GAS_START + self._n_gas
        self._table.setItem(row, tail,     QTableWidgetItem(str(step.prepare_sec)))
        self._table.setItem(row, tail + 1, QTableWidgetItem(str(step.measure_sec)))
        self._table.setItem(row, tail + 2, QTableWidgetItem(str(step.repeat)))

        # 4-way 콤보박스
        combo = QComboBox()
        combo.addItems(["vent", "chamber"])
        combo.setCurrentText(step.fourway)
        combo.setStyleSheet("background: #ffffff; color: #2c3e50;")
        self._table.setCellWidget(row, tail + 3, combo)

    def _delete_step(self):
        rows = sorted(set(i.row() for i in self._table.selectedItems()), reverse=True)
        for r in rows:
            self._table.removeRow(r)
        self._renumber_steps()

    def _move_up(self):
        row = self._table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self._table.setCurrentCell(row - 1, 0)

    def _move_down(self):
        row = self._table.currentRow()
        if row < self._table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self._table.setCurrentCell(row + 1, 0)

    def _swap_rows(self, r1: int, r2: int):
        for col in range(self._n_cols):
            item1 = self._table.item(r1, col)
            item2 = self._table.item(r2, col)
            t1 = item1.text() if item1 else ""
            t2 = item2.text() if item2 else ""
            self._table.setItem(r1, col, QTableWidgetItem(t2))
            self._table.setItem(r2, col, QTableWidgetItem(t1))
        # 4-way 콤보박스 처리
        tail = COL_GAS_START + self._n_gas + 3
        w1 = self._table.cellWidget(r1, tail)
        w2 = self._table.cellWidget(r2, tail)
        v1 = w1.currentText() if w1 else "vent"
        v2 = w2.currentText() if w2 else "vent"
        c1 = self._make_combo(v1)
        c2 = self._make_combo(v2)
        self._table.setCellWidget(r1, tail, c2)
        self._table.setCellWidget(r2, tail, c1)

    @staticmethod
    def _make_combo(value: str) -> QComboBox:
        c = QComboBox()
        c.addItems(["vent", "chamber"])
        c.setCurrentText(value)
        c.setStyleSheet("background: #ffffff; color: #2c3e50;")
        return c

    def _renumber_steps(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_STEP)
            if item:
                item.setText(f"P{row + 1}")

    # ── 레시피 ↔ 테이블 변환 ──────────────────────────

    def _table_to_recipe(self) -> Recipe:
        recipe = Recipe(
            name=self._lbl_recipe_name.text(),
            loop_count=self._spin_loop.value(),
            interval_sec=self._spin_interval.value(),
            bubbler_temp_c=self._spin_bubbler.value(),
        )
        tail = COL_GAS_START + self._n_gas
        for row in range(self._table.rowCount()):
            def cell(c):
                item = self._table.item(row, c)
                return item.text() if item else "0"

            targets = {}
            for i, ch in enumerate(self._gas_channels):
                try:
                    targets[ch.idx] = float(cell(COL_GAS_START + i))
                except ValueError:
                    targets[ch.idx] = 0.0

            fourway_widget = self._table.cellWidget(row, tail + 3)
            fourway = fourway_widget.currentText() if fourway_widget else "vent"

            try:
                step = RecipeStep(
                    step_id=cell(COL_STEP),
                    total_flow_sccm=float(cell(COL_FLOW)),
                    humidity_pct=float(cell(COL_HUMID)),
                    gas_targets=targets,
                    prepare_sec=int(float(cell(tail))),
                    measure_sec=int(float(cell(tail + 1))),
                    repeat=max(1, int(float(cell(tail + 2)))),
                    fourway=fourway,
                )
                recipe.steps.append(step)
            except ValueError as e:
                logger.warning(f"Row {row} 변환 오류: {e}")

        return recipe

    def _load_recipe_to_table(self, recipe: Recipe):
        self._table.setRowCount(0)
        self._lbl_recipe_name.setText(recipe.name)
        self._spin_loop.setValue(recipe.loop_count)
        self._spin_interval.setValue(recipe.interval_sec)
        self._spin_bubbler.setValue(recipe.bubbler_temp_c)
        for step in recipe.steps:
            self._add_step(step)
        self._recipe = recipe

    # ── 파일 I/O ──────────────────────────────────────

    def _new_recipe(self):
        recipe = Recipe(name="New Recipe")
        recipe.steps = [RecipeStep()]
        self._load_recipe_to_table(recipe)
        self._current_path = None

    def _open_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "레시피 열기", str(self._recipe_dir), "JSON (*.json)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                recipe = Recipe.from_dict(data)
                self._load_recipe_to_table(recipe)
                self._current_path = Path(path)
                self.recipe_loaded.emit(recipe)
                logger.info(f"레시피 로드: {path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"파일을 열 수 없습니다:\n{e}")

    def _save_recipe(self):
        if self._current_path is None:
            self._saveas_recipe()
        else:
            self._write_recipe(self._current_path)

    def _saveas_recipe(self):
        name = self._lbl_recipe_name.text().replace(" ", "_")
        default = str(self._recipe_dir / f"{name}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "레시피 저장", default, "JSON (*.json)")
        if path:
            self._current_path = Path(path)
            self._write_recipe(self._current_path)

    def _write_recipe(self, path: Path):
        try:
            recipe = self._table_to_recipe()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(recipe.to_dict(), f, ensure_ascii=False, indent=2)
            self._recipe = recipe
            logger.info(f"레시피 저장: {path}")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", str(e))

    # ── Setpoint 미리보기 ─────────────────────────────

    def _on_selection_changed(self, row, col, prev_row, prev_col):
        if row < 0:
            return
        recipe = self._table_to_recipe()
        if row >= len(recipe.steps):
            return
        step = recipe.steps[row]
        try:
            rows = self._calc.preview_table(step, self._channels)
            lines = [f"{'채널':<10} {'목표(sccm)':>12} {'설정(sccm)':>12} {'전압(V)':>8}"]
            lines.append("─" * 46)
            for r in rows:
                lines.append(
                    f"{r['채널']:<10} {r['목표유량(sccm)']:>12.1f} "
                    f"{r['MFC설정(sccm)']:>12.1f} {r['DAC전압(V)']:>8.3f}")
            self._preview_text.setPlainText("\n".join(lines))
        except Exception as e:
            self._preview_text.setPlainText(f"계산 오류: {e}")

    # ── 공개 API ──────────────────────────────────────

    def get_current_recipe(self) -> Recipe:
        return self._table_to_recipe()

    def update_channels(self, channels: list[ChannelConfig]):
        """설정 변경 후 채널 목록 갱신 (테이블 재구성)"""
        self._channels = channels
        self._gas_channels = [c for c in channels if not c.is_balance and c.enabled]
        self._n_gas = len(self._gas_channels)
