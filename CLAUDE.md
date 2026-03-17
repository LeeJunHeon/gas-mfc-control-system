# GAS Control System

## 구조
- main.py: 진입점
- app/: 데이터 모델, 설정
- calculation/: 유량/CF/습도 계산
- drivers/: mock_driver(현재), real_driver(추후)
- services/: device_service, data_logger
- engine/: recipe_engine(QThread), interlock, alarm_manager
- ui/: PySide6 화면들

## 현재 상태
- Mock Driver로 시뮬레이션 동작 확인 완료
- 실제 하드웨어 연결 시 hardware.json에서 driver_type을 "real"로 변경

## 실행
python main.py