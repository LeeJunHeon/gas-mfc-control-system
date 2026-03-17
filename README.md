# GAS Control System v1.0

PLC + ADC + DAC 기반 가스 공급 자동화 시스템  
**Python 3.10+ / PySide6**

---

## 빠른 시작

```bash
# 의존성 설치
pip install PySide6

# 실행
python main.py
```

Windows: `run.bat` 더블클릭  
Linux/macOS: `bash run.sh`

---

## 폴더 구조

```
gas_control/
├── main.py                       # 진입점 (의존성 조립)
│
├── app/
│   ├── models.py                 # 데이터 모델 (dataclass, Enum)
│   └── config.py                 # JSON 설정 로드/저장
│
├── calculation/
│   ├── gas_correction.py         # CF 보정 (HORIBA 매뉴얼 기준)
│   ├── humidity_calculator.py    # 습도 유량 계산 (버블러 방식)
│   └── flow_calculator.py        # MFC setpoint 통합 계산
│
├── drivers/
│   ├── base_driver.py            # 추상 드라이버 인터페이스
│   ├── mock_driver.py            # 시뮬레이션 드라이버 (1차 지연 응답 포함)
│   └── real_driver.py            # 실제 HW 드라이버 (Modbus TCP + NI-DAQ)
│
├── services/
│   ├── device_service.py         # 하드웨어 추상화 레이어
│   └── data_logger.py            # PV/SV CSV 로거 (공정 중 자동 기록)
│
├── engine/
│   ├── recipe_engine.py          # 레시피 실행 상태머신 (QThread)
│   ├── interlock.py              # 인터락 안전 체크
│   └── alarm_manager.py          # 알람 관리 + 파일 로깅
│
├── ui/
│   ├── style.qss                 # 다크 산업용 HMI 테마
│   ├── main_window.py            # 메인 윈도우 (Signal 배선)
│   ├── hmi_panel.py              # P&ID 스타일 가스 라인 다이어그램
│   ├── recipe_panel.py           # 레시피 테이블 편집 + setpoint 미리보기
│   ├── process_panel.py          # 공정 실행 + 타이머 + PV 바
│   ├── log_panel.py              # 이벤트 로그 뷰어 + CSV 내보내기
│   ├── settings_dialog.py        # 채널/하드웨어 설정 다이얼로그
│   └── widgets/
│       ├── valve_widget.py       # P&ID 나비 밸브 / 다이아몬드 솔밸브
│       ├── mfc_widget.py         # MFC PV/SV/MAX 표시 위젯
│       └── led_widget.py         # LED 상태 표시 위젯
│
├── data/
│   ├── config/                   # 자동 생성 JSON 설정
│   │   ├── channel_config.json   # 채널별 이름/가스/FS/CF/활성화
│   │   ├── gas_library.json      # CF 테이블 (HORIBA S48 기준)
│   │   └── hardware.json         # 드라이버/PLC/DAQ/타이밍 설정
│   ├── recipes/                  # 레시피 JSON 파일
│   └── logs/                     # 이벤트 로그 + PV CSV
│
└── tests/
    ├── test_flow_calculator.py   # 유량 계산 단위 테스트
    └── test_data_logger.py       # 데이터 로거 단위 테스트
```

---

## 실제 하드웨어 연결

### 1단계: 드라이버 타입 변경
`data/config/hardware.json`에서:
```json
"driver_type": "real"
```

### 2단계: 패키지 설치
```bash
pip install pymodbus        # PLC (Modbus TCP)
pip install nidaqmx         # NI-DAQ ADC/DAC
```

### 3단계: 핀 매핑 확인
`hardware.json`의 `channel_pins`에서 각 채널의  
`dac_ch` (MFC setpoint), `adc_ch` (MFC PV), `va_coil`, `sol_coil` 주소 설정

---

## MFC 유량 계산 원리 (HORIBA S48)

```
# 실제 원하는 유량 → N2 기준 MFC setpoint
MFC_setpoint = desired_flow / CF(gas)

# setpoint → DAC 전압
DAC_voltage = (setpoint / full_scale) × 5.0 V

# ADC 전압 → 실제 유량 (PV)
actual_flow = (ADC_voltage / 5.0) × full_scale × CF(gas)
```

**표준가스(희석) 경우:**
```
gas_flow = total_flow × (target_ppm / source_ppm)
```

CF 테이블: `data/config/gas_library.json`  
(없는 가스는 HORIBA에 문의 또는 실측 보정)

---

## 단위 테스트

```bash
python tests/test_flow_calculator.py
python tests/test_data_logger.py
```

---

## 주요 설계 원칙

| 원칙 | 구현 |
|---|---|
| **드라이버 교체 가능** | `BaseDriver` 상속, `hardware.json`에서 `mock`↔`real` 전환 |
| **UI-로직 분리** | Qt Signal/Slot 전용, UI에서 직접 장치 접근 금지 |
| **계산 독립** | `calculation/` 패키지는 하드웨어/UI와 완전 분리 |
| **설정 외부화** | 가스명, CF, 채널 매핑 모두 JSON, 코드 수정 없이 현장 조정 |
| **데이터 보존** | 설정 저장 시 자동 `.bak` 백업, PV CSV 30일 자동 정리 |
| **확장 포인트** | `MeasurementService` + 레시피 엔진 훅으로 측정장비 연동 |

---

## PyInstaller 패키징 (단일 exe)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
  --add-data "data;data" \
  --add-data "ui/style.qss;ui" \
  main.py
```
