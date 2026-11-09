"""Unit tests for the pure analysis functions.

Run with:  python -m pytest -q
These need no network and no Earth Engine credentials.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C  # noqa: E402
from src import metrics as M  # noqa: E402


# --- buffer_radius_m -------------------------------------------------------


def test_buffer_radius_scales_with_capacity():
    small = M.buffer_radius_m(50)
    large = M.buffer_radius_m(500)
    assert large > small


def test_buffer_radius_matches_land_use_assumption():
    # 1000 MW at 22,000 m2/MW = 2.2e7 m2 -> r = sqrt(2.2e7/pi) ~= 2646 m
    r = M.buffer_radius_m(1000)
    assert math.isclose(r, math.sqrt(1000 * C.LAND_USE_M2_PER_MW / math.pi), rel_tol=1e-6)


def test_buffer_radius_clamped():
    assert M.buffer_radius_m(0.001) == C.BUFFER_MIN_M
    assert M.buffer_radius_m(10_000_000) == C.BUFFER_MAX_M


def test_buffer_radius_handles_missing_capacity():
    assert M.buffer_radius_m(None) == C.BUFFER_MIN_M
    assert M.buffer_radius_m(float("nan")) == C.BUFFER_MIN_M


# --- build detection -------------------------------------------------------


def test_observed_build_month_finds_half_of_final_level():
    months = [f"2019-{m:02d}" for m in range(1, 13)] + [f"2020-{m:02d}" for m in range(1, 13)]
    # ramps from 0.0 to 0.8 over the first year, then flat
    frac = [i * 0.8 / 11 for i in range(12)] + [0.8] * 12
    got = M.observed_build_month(months, frac)
    # final level 0.8, threshold 0.4 -> first month at or above 0.4
    assert got is not None and got.startswith("2019-")


def test_observed_build_month_needs_enough_data():
    assert M.observed_build_month(["2020-01"], [0.5]) is None


def test_observed_build_month_handles_all_zero():
    months = [f"2020-{m:02d}" for m in range(1, 13)]
    assert M.observed_build_month(months, [0.0] * 12) is None


def test_build_delay_positive_when_built_after_claim():
    # claimed commissioned 2019, observed substantial build mid-2021
    delay = M.build_delay_months("2021-06", 2019)
    assert delay is not None and delay > 12


def test_build_delay_negative_when_built_before_claim():
    delay = M.build_delay_months("2018-06", 2019)
    assert delay is not None and delay < 0


def test_build_delay_none_on_missing_input():
    assert M.build_delay_months(None, 2019) is None
    assert M.build_delay_months("2021-06", None) is None
    assert M.build_delay_months("2021-06", float("nan")) is None


# --- resource --------------------------------------------------------------


def test_resource_anomaly_sign_and_magnitude():
    assert M.resource_anomaly_pct(1900, 2000) == -5.0
    assert M.resource_anomaly_pct(2100, 2000) == 5.0


def test_resource_anomaly_guards():
    assert M.resource_anomaly_pct(None, 2000) is None
    assert M.resource_anomaly_pct(1900, 0) is None


def test_mean_or_none_skips_nan():
    assert M.mean_or_none([1.0, float("nan"), 3.0]) == 2.0
    assert M.mean_or_none([None, float("nan")]) is None


# --- thermal ---------------------------------------------------------------


def test_cell_temperature_above_air_temperature():
    assert M.cell_temperature_c(30.0, 1000.0) > 30.0


def test_thermal_derate_increases_with_heat():
    cool = M.thermal_derate_pct(20.0)
    hot = M.thermal_derate_pct(45.0)
    assert hot > cool >= 0.0


def test_thermal_derate_never_negative():
    # a very cold day would imply a performance *gain*; we clamp at zero
    assert M.thermal_derate_pct(-20.0, 200.0) == 0.0


# --- trend -----------------------------------------------------------------


def test_linear_trend_recovers_known_slope():
    years = [2019.0, 2020.0, 2021.0, 2022.0, 2023.0]
    values = [0.10, 0.12, 0.14, 0.16, 0.18]
    assert math.isclose(M.linear_trend_per_year(years, values), 0.02, rel_tol=1e-6)


def test_linear_trend_needs_four_points():
    assert M.linear_trend_per_year([1.0, 2.0], [1.0, 2.0]) is None


def test_linear_trend_flat_is_zero():
    years = [2019.0, 2020.0, 2021.0, 2022.0]
    assert M.linear_trend_per_year(years, [0.1] * 4) == 0.0


# --- flags and score -------------------------------------------------------


def _clean_inputs(**overrides):
    base = dict(
        build_delay_m=0.0,
        mean_resource_anomaly_pct=0.0,
        heat_days_per_year=0.0,
        ndvi_trend_per_year=0.0,
        gsw_occurrence_pct=0.0,
        hand_m=50.0,
    )
    base.update(overrides)
    return base


def test_clean_asset_raises_no_flags():
    flags = M.evaluate_flags(**_clean_inputs())
    assert M.flag_score(flags) == 0.0
    assert M.traffic_light(0.0) == "green"


def test_each_flag_fires_independently():
    assert M.evaluate_flags(**_clean_inputs(build_delay_m=24)).build_delay
    assert M.evaluate_flags(**_clean_inputs(mean_resource_anomaly_pct=-9)).resource_shortfall
    assert M.evaluate_flags(**_clean_inputs(heat_days_per_year=120)).thermal_derating
    assert M.evaluate_flags(**_clean_inputs(ndvi_trend_per_year=0.05)).vegetation_encroachment
    assert M.evaluate_flags(**_clean_inputs(gsw_occurrence_pct=40)).flood_exposure
    assert M.evaluate_flags(**_clean_inputs(hand_m=1.0)).flood_exposure


def test_missing_evidence_never_flags():
    flags = M.evaluate_flags(
        build_delay_m=None,
        mean_resource_anomaly_pct=None,
        heat_days_per_year=None,
        ndvi_trend_per_year=None,
        gsw_occurrence_pct=None,
        hand_m=None,
    )
    assert M.flag_score(flags) == 0.0


def test_weights_sum_to_one_hundred():
    assert math.isclose(sum(C.FLAG_WEIGHTS.values()), 100.0)


def test_all_flags_scores_one_hundred():
    flags = M.evaluate_flags(
        **_clean_inputs(
            build_delay_m=36,
            mean_resource_anomaly_pct=-10,
            heat_days_per_year=150,
            ndvi_trend_per_year=0.06,
            gsw_occurrence_pct=60,
        )
    )
    assert M.flag_score(flags) == 100.0
    assert M.traffic_light(100.0) == "red"


def test_traffic_light_bands_are_contiguous():
    assert M.traffic_light(0.0) == "green"
    assert M.traffic_light(24.9) == "green"
    assert M.traffic_light(25.0) == "amber"
    assert M.traffic_light(54.9) == "amber"
    assert M.traffic_light(55.0) == "red"


def test_evidence_completeness():
    assert M.evidence_completeness(_clean_inputs()) == 1.0
    assert M.evidence_completeness({}) == 0.0
    assert M.evidence_completeness({"hand_m": 3.0, "heat_days_per_year": 10}) == 0.33
