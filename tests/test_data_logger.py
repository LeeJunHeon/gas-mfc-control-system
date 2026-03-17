"""
tests/test_data_logger.py  - DataLogger 단위 테스트
"""
import sys, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.data_logger import DataLogger


def test_basic_logging():
    """기본 로깅: start → log_row × N → stop → CSV 확인"""
    with tempfile.TemporaryDirectory() as tmp:
        dl = DataLogger(Path(tmp), n_channels=4)
        dl.start("TestRecipe")
        assert dl.is_logging
        assert dl.current_path is not None

        dl.update_step("P1", 1)
        dl.update_sv({0: 100.0, 1: 200.0, 2: 50.0, 3: 0.0})
        for i in range(5):
            dl.log_row({0: 98.0 + i*0.1, 1: 199.0, 2: 49.5, 3: 0.0})

        assert dl.row_count == 5
        dl.stop()
        assert not dl.is_logging

        # CSV 파일 검증
        csv_path = dl.current_path
        assert csv_path.exists()
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5
        assert rows[0]["step_id"] == "P1"
        assert rows[0]["loop"] == "1"
        assert float(rows[0]["ch0_pv"]) == 98.0
        assert float(rows[0]["ch0_sv"]) == 100.0
        print(f"✓ test_basic_logging ({len(rows)}행 검증)")


def test_no_start():
    """start() 없이 log_row 호출해도 오류 없음"""
    with tempfile.TemporaryDirectory() as tmp:
        dl = DataLogger(Path(tmp), n_channels=4)
        dl.log_row({0: 100.0})  # 무시됨
        assert dl.row_count == 0
        print("✓ test_no_start")


def test_multiple_steps():
    """여러 스텝에 걸쳐 step_id 변경 확인"""
    with tempfile.TemporaryDirectory() as tmp:
        dl = DataLogger(Path(tmp), n_channels=2)
        dl.start("MultiStep")
        dl.update_step("P1", 1); dl.log_row({0: 10.0, 1: 20.0})
        dl.update_step("P2", 1); dl.log_row({0: 30.0, 1: 40.0})
        dl.stop()
        with open(dl.current_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["step_id"] == "P1"
        assert rows[1]["step_id"] == "P2"
        print("✓ test_multiple_steps")


if __name__ == "__main__":
    test_basic_logging()
    test_no_start()
    test_multiple_steps()
    print("\n✅ DataLogger 테스트 모두 통과!")
