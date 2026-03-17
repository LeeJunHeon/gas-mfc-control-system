"""
tests/test_flow_calculator.py  -  FlowCalculator / GasCorrection / HumidityCalculator 단위 테스트
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import ChannelConfig, RecipeStep
from calculation.gas_correction import GasCorrection
from calculation.humidity_calculator import HumidityCalculator, sat_pressure_kpa
from calculation.flow_calculator import FlowCalculator

GAS_LIB = {"N2":1.000,"Air":1.000,"O2":0.980,"H2":1.400,"NO2":1.010,"CO2":0.740}

def _chs():
    return [
        ChannelConfig(idx=0,name="Air1",gas_name="Air",source_conc_ppm=0,  full_scale_sccm=2000,cf=1.00,is_balance=True, enabled=True, color="#3498db"),
        ChannelConfig(idx=1,name="Air2",gas_name="Air",source_conc_ppm=0,  full_scale_sccm=2000,cf=1.00,is_balance=True, enabled=True, color="#3498db"),
        ChannelConfig(idx=2,name="Gas1",gas_name="NO2",source_conc_ppm=10, full_scale_sccm=2000,cf=1.01,is_balance=False,enabled=True, color="#e74c3c"),
        ChannelConfig(idx=3,name="Gas2",gas_name="N2", source_conc_ppm=0,  full_scale_sccm=200, cf=1.00,is_balance=False,enabled=False,color="#9b59b6"),
    ]

def _calc():
    return FlowCalculator(GasCorrection(GAS_LIB), HumidityCalculator(25.0, 101.3))


# ── FlowCalculator 테스트 ─────────────────────────────

def test_basic_no2():
    """NO2 5ppm(source=10ppm), Total=1000sccm, 습도 없음"""
    step = RecipeStep(total_flow_sccm=1000, humidity_pct=0,
                      gas_targets={2: 5.0}, prepare_sec=10, measure_sec=10)
    r = _calc().calculate(step, _chs())
    assert r.is_valid, f"오류: {r.errors}"
    # desired = 1000 * (5/10) = 500
    assert abs(r.setpoints[2].desired_flow_sccm - 500.0) < 0.01
    # setpoint = 500 / CF(NO2=1.01) ≈ 495.05
    assert abs(r.setpoints[2].mfc_setpoint_sccm - 500/1.01) < 0.1
    # balance = 1000 - 500 = 500 (Air 2채널에 250씩)
    assert abs(r.balance_flow_sccm - 500.0) < 0.01
    print("✓ test_basic_no2")


def test_with_humidity():
    """Humidity=40% → wet_flow=400, balance=600 - 가스 없음"""
    step = RecipeStep(total_flow_sccm=1000, humidity_pct=40, gas_targets={})
    r = _calc().calculate(step, _chs())
    assert r.is_valid, f"오류: {r.errors}"
    assert abs(r.humidity_flow_sccm - 400.0) < 0.1   # 1000 * 40/100
    assert abs(r.balance_flow_sccm - 600.0) < 0.1
    print(f"✓ test_with_humidity (wet={r.humidity_flow_sccm:.1f}, balance={r.balance_flow_sccm:.1f})")


def test_gas_plus_humidity():
    """NO2 5ppm + Humidity 40%: 500 + 400 = 900 → balance 100"""
    step = RecipeStep(total_flow_sccm=1000, humidity_pct=40, gas_targets={2: 5.0})
    r = _calc().calculate(step, _chs())
    assert r.is_valid, f"오류: {r.errors}"
    assert abs(r.setpoints[2].desired_flow_sccm - 500.0) < 0.1
    assert abs(r.humidity_flow_sccm - 400.0) < 0.1
    assert abs(r.balance_flow_sccm - 100.0) < 0.1
    print(f"✓ test_gas_plus_humidity (gas=500, wet=400, balance={r.balance_flow_sccm:.1f})")


def test_all_air():
    """가스 없음, 습도 없음 → 전부 Air"""
    r = _calc().calculate(
        RecipeStep(total_flow_sccm=1000, humidity_pct=0, gas_targets={}), _chs())
    assert r.is_valid
    assert abs(r.balance_flow_sccm - 1000.0) < 0.01
    print("✓ test_all_air")


def test_overflow_detection():
    """가스 합계 > Total Flow → 오류"""
    step = RecipeStep(total_flow_sccm=1000, humidity_pct=0, gas_targets={2: 20.0})
    r = _calc().calculate(step, _chs())
    assert not r.is_valid
    assert any("초과" in e for e in r.errors)
    print("✓ test_overflow_detection")


def test_disabled_channel_ignored():
    """비활성 채널(idx=3)은 gas_targets에 있어도 무시"""
    step = RecipeStep(total_flow_sccm=500, humidity_pct=0, gas_targets={3: 100.0})
    r = _calc().calculate(step, _chs())
    assert r.is_valid
    assert abs(r.balance_flow_sccm - 500.0) < 0.01
    print("✓ test_disabled_channel_ignored")


def test_voltage_conversion():
    """sccm ↔ 전압 변환"""
    calc = _calc()
    assert abs(calc.sccm_to_voltage(1000.0, 2000.0) - 2.5) < 0.001
    assert abs(calc.voltage_to_sccm(2.5, 2000.0, cf=1.0) - 1000.0) < 0.1
    print("✓ test_voltage_conversion")


def test_preview_table():
    """preview_table 반환 형식"""
    step = RecipeStep(total_flow_sccm=1000, humidity_pct=0, gas_targets={2: 5.0})
    rows = _calc().preview_table(step, _chs())
    assert len(rows) == 4
    assert "MFC설정(sccm)" in rows[0]
    print("✓ test_preview_table")


# ── GasCorrection 테스트 ─────────────────────────────

def test_cf_manual_example():
    """HORIBA 매뉴얼 Example 1: H2 140sccm = N2 기준 100sccm"""
    gc = GasCorrection({"N2": 1.000, "H2": 1.400})
    assert abs(gc.desired_to_setpoint(140.0, "H2") - 100.0) < 0.1
    assert abs(gc.setpoint_to_actual(100.0, "H2") - 140.0) < 0.1
    print("✓ test_cf_manual_example (HORIBA 매뉴얼 Example 1 검증)")


def test_cf_unknown_gas_returns_1():
    """CF 테이블에 없는 가스는 1.0 반환"""
    gc = GasCorrection({"N2": 1.0})
    cf = gc.get_cf("UNKNOWN_GAS")
    assert cf == 1.0
    print("✓ test_cf_unknown_gas_returns_1")


# ── HumidityCalculator 테스트 ────────────────────────

def test_sat_pressure_25c():
    """Antoine 방정식: 25°C ≈ 3.1~3.2 kPa"""
    p = sat_pressure_kpa(25.0)
    assert 3.0 < p < 3.4, f"25°C P_sat={p:.3f} kPa"
    print(f"✓ test_sat_pressure_25c (P_sat={p:.3f} kPa)")


def test_wet_flow_formula():
    """wet_flow = total × RH/100 (버블러 비율 방식)"""
    hc = HumidityCalculator(25.0, 101.3)
    assert abs(hc.wet_air_flow(1000.0, 40.0) - 400.0) < 0.01
    assert abs(hc.wet_air_flow(1000.0, 0.0)  - 0.0)   < 0.01
    assert abs(hc.wet_air_flow(1000.0, 100.0)- 1000.0) < 0.01
    print("✓ test_wet_flow_formula")


def test_actual_rh_inverse():
    """actual_rh_pct는 wet_air_flow의 역산"""
    hc = HumidityCalculator(25.0, 101.3)
    wet = hc.wet_air_flow(1000.0, 40.0)
    actual = hc.actual_rh_pct(wet, 1000.0)
    # 25°C 버블러에서 달성 가능한 최대 RH ≈ 3.1%
    assert 0 < actual < 5.0
    print(f"✓ test_actual_rh_inverse (설정=40%, 실제 챔버 RH≈{actual:.2f}%)")


if __name__ == "__main__":
    print("=== FlowCalculator ===")
    test_basic_no2()
    test_with_humidity()
    test_gas_plus_humidity()
    test_all_air()
    test_overflow_detection()
    test_disabled_channel_ignored()
    test_voltage_conversion()
    test_preview_table()

    print("\n=== GasCorrection ===")
    test_cf_manual_example()
    test_cf_unknown_gas_returns_1()

    print("\n=== HumidityCalculator ===")
    test_sat_pressure_25c()
    test_wet_flow_formula()
    test_actual_rh_inverse()

    print("\n✅ 전체 테스트 통과!")
