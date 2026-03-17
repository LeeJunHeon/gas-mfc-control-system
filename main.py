"""
main.py
애플리케이션 진입점

실행:
    python main.py

PyInstaller 단일 exe 패키징:
    pyinstaller --onefile --windowed --add-data "data;data" --add-data "ui/style.qss;ui" main.py
"""
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import AppConfig, LOG_DIR
from calculation.gas_correction import GasCorrection
from calculation.humidity_calculator import HumidityCalculator
from calculation.flow_calculator import FlowCalculator
from services.device_service import DeviceService
from services.data_logger import DataLogger
from engine.recipe_engine import RecipeEngine
from engine.interlock import Interlock
from engine.alarm_manager import AlarmManager
from ui.main_window import MainWindow


def setup_logging():
    """콘솔 + 파일 로깅"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now():%Y-%m-%d}_app.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(fh)


def _make_driver(config: AppConfig):
    """드라이버 선택 (Mock or Real). 실패 시 Mock으로 폴백."""
    drv_type = config.hardware.get("driver_type", "mock")
    full_scales = [ch.full_scale_sccm for ch in config.channels]

    if drv_type == "real":
        try:
            from drivers.real_driver import RealDriver
            drv = RealDriver(config.hardware)
            if drv.connect():
                logging.getLogger(__name__).info("실제 드라이버 연결 성공")
                return drv
            logging.getLogger(__name__).warning(
                "실제 드라이버 연결 실패 → Mock으로 폴백")
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"실제 드라이버 오류: {e} → Mock으로 폴백")

    from drivers.mock_driver import MockDriver
    drv = MockDriver(full_scales=full_scales)
    return drv


def build_app():
    """의존성 주입 + 객체 조립"""
    config = AppConfig()

    # 계산 모듈
    gas_correction = GasCorrection(config.gas_library)
    humidity_calc  = HumidityCalculator(bubbler_temp_c=25.0, system_pressure_kpa=101.3)
    flow_calc      = FlowCalculator(gas_correction, humidity_calc)

    # 드라이버
    driver = _make_driver(config)

    # 서비스
    device = DeviceService(driver=driver, channels=config.channels, hw_config=config.hardware)

    # 데이터 로거 (PV CSV)
    data_logger = DataLogger(log_dir=config.log_dir, n_channels=len(config.channels))
    data_logger.cleanup_old_logs(keep_days=30)

    # 알람, 인터락, 엔진
    alarm    = AlarmManager(log_dir=config.log_dir)
    interlock = Interlock(channels=config.channels)
    engine   = RecipeEngine(
        device=device, calculator=flow_calc,
        interlock=interlock, alarm=alarm,
        data_logger=data_logger,
    )

    return config, device, engine, alarm, flow_calc, data_logger


def main():
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("=" * 60)
    log.info("GAS Control System 시작")
    log.info("=" * 60)

    app = QApplication(sys.argv)
    app.setApplicationName("GAS Control System")
    app.setOrganizationName("GCS")

    # QSS 스타일 로드
    qss_path = ROOT / "ui" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    else:
        log.warning(f"스타일시트 없음: {qss_path}")

    # 객체 조립
    try:
        config, device, engine, alarm, flow_calc, data_logger = build_app()
    except Exception as e:
        QMessageBox.critical(None, "초기화 오류",
                             f"프로그램 초기화 중 오류:\n{e}")
        log.critical(f"초기화 실패: {e}", exc_info=True)
        sys.exit(1)

    # 메인 윈도우
    window = MainWindow(
        config=config, device=device,
        engine=engine, alarm=alarm, flow_calc=flow_calc,
    )
    window.show()

    log.info("UI 시작됨")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
