"""
services/data_logger.py
PV 데이터 CSV 로거

공정 실행 중 각 채널의 실측값(PV)과 설정값(SV)을 1초 간격으로 CSV에 저장.
파일명: data/logs/YYYYMMDD_HHMMSS_{레시피명}.csv

CSV 포맷:
  timestamp, step_id, loop, ch0_pv, ch0_sv, ch1_pv, ch1_sv, ..., humidity_pct

납품 후 데이터 분석에 필수 - 실험 재현성 확보용
"""
from __future__ import annotations
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DataLogger:
    """PV/SV 시계열 CSV 로거"""

    def __init__(self, log_dir: Path, n_channels: int = 8):
        self._log_dir = log_dir
        self._n_ch = n_channels
        self._file: Optional[open] = None
        self._writer: Optional[csv.DictWriter] = None
        self._path: Optional[Path] = None
        self._row_count = 0

        # 현재 공정 컨텍스트
        self._current_step: str = "-"
        self._current_loop: int = 0
        self._current_sv: dict[int, float] = {}

    # ── 공개 API ──────────────────────────────────────

    def start(self, recipe_name: str):
        """로깅 시작 - 새 CSV 파일 열기"""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = recipe_name.replace(" ", "_").replace("/", "-")[:40]
        self._path = self._log_dir / f"{ts}_{safe_name}.csv"

        self._file = open(self._path, "w", newline="", encoding="utf-8-sig")
        fieldnames = self._make_fieldnames()
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        self._writer.writeheader()
        self._file.flush()
        self._row_count = 0
        logger.info(f"데이터 로깅 시작: {self._path}")

    def stop(self):
        """로깅 종료"""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
            logger.info(f"데이터 로깅 완료: {self._row_count}행, {self._path}")

    def log_row(self, pv_dict: dict[int, float]):
        """
        PV 딕셔너리 한 행 기록.
        RecipeEngine의 pv_updated 시그널 수신 시 호출.
        """
        if self._writer is None:
            return
        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "step_id":   self._current_step,
            "loop":      self._current_loop,
        }
        for i in range(self._n_ch):
            row[f"ch{i}_pv"] = f"{pv_dict.get(i, 0.0):.2f}"
            row[f"ch{i}_sv"] = f"{self._current_sv.get(i, 0.0):.2f}"

        try:
            self._writer.writerow(row)
            self._row_count += 1
            # 10행마다 플러시 (성능 vs 안전성 균형)
            if self._row_count % 10 == 0:
                self._file.flush()
        except Exception as e:
            logger.error(f"데이터 로깅 오류: {e}")

    def update_step(self, step_id: str, loop: int):
        """현재 스텝/루프 컨텍스트 업데이트"""
        self._current_step = step_id
        self._current_loop = loop

    def update_sv(self, sv_dict: dict[int, float]):
        """현재 SV 업데이트"""
        self._current_sv = dict(sv_dict)

    @property
    def is_logging(self) -> bool:
        return self._file is not None

    @property
    def current_path(self) -> Optional[Path]:
        return self._path

    @property
    def row_count(self) -> int:
        return self._row_count

    # ── 내부 ──────────────────────────────────────────

    def _make_fieldnames(self) -> list[str]:
        fields = ["timestamp", "step_id", "loop"]
        for i in range(self._n_ch):
            fields += [f"ch{i}_pv", f"ch{i}_sv"]
        return fields

    # ── 오래된 로그 정리 ──────────────────────────────

    def cleanup_old_logs(self, keep_days: int = 30):
        """지정 일수 이상 된 CSV 파일 삭제"""
        import time
        cutoff = time.time() - keep_days * 86400
        deleted = 0
        for f in self._log_dir.glob("*.csv"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        if deleted:
            logger.info(f"오래된 로그 {deleted}개 삭제 (>{keep_days}일)")
