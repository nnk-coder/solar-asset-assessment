"""Pure analysis functions. No Earth Engine, no network, fully unit-testable.

Everything here takes plain numbers or lists and returns plain numbers or
dicts. The Earth Engine layer in src/gee.py produces the inputs; this module
turns them into flags and a score. Keeping the judgement separate from the
data extraction is what makes the rubric arguable rather than opaque.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import date
from typing import Iterable, Sequence

from . import config as C


# --- Footprint -------------------------------------------------------------


def buffer_radius_m(capacity_mw: float) -> float:
    """Radius of a circular footprint proxy for a PV plant of this capacity.

    We do not attempt panel segmentation. A capacity-scaled circle is a crude
    but honest proxy: it over-includes surrounding land, which is stated as a
    limitation rather than hidden behind a classifier that would need labels
    we do not have.
    """
    if capacity_mw is None or capacity_mw <= 0 or math.isnan(capacity_mw):
        return C.BUFFER_MIN_M
    area_m2 = capacity_mw * C.LAND_USE_M2_PER_MW
    radius = math.sqrt(area_m2 / math.pi)
    return float(min(max(radius, C.BUFFER_MIN_M), C.BUFFER_MAX_M))


# --- Build progress --------------------------------------------------------


def first_crossing_index(series: Sequence[float], threshold: float) -> int | None:
    """Index of the first value at or above `threshold`, or None."""
    for i, v in enumerate(series):
        if v is not None and not math.isnan(v) and v >= threshold:
            return i
    return None


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def smooth_median(values: Sequence[float | None], window: int = 3) -> list[float | None]:
    """Rolling median, which suppresses single-month label noise without
    shifting a genuine step the way a mean would."""
    out: list[float | None] = []
    for i in range(len(values)):
        lo = max(0, i - window // 2)
        hi = min(len(values), i + window // 2 + 1)
        chunk = [v for v in values[lo:hi] if v is not None and not math.isnan(v)]
        out.append(_median(chunk) if chunk else None)
    return out


def build_status(
    months: Sequence[str], developed_fraction: Sequence[float]
) -> tuple[str, str | None]:
    """Classify the construction signal, rather than always returning a month.

    Returns one of:
      ("ramp", "YYYY-MM")   a genuine rise from a low baseline to a plateau
      ("already_built", first month)  high from the first observation, so the
                          plant predates the satellite record and this check
                          cannot speak to it
      ("no_signal", None)   noisy, flat or declining; no construction visible
      ("no_data", None)     too few usable observations

    The earlier version always returned a month. On a plant built before 2017
    it returned the first month of the record, which looked like a finding and
    was an artefact. Saying "this check cannot speak to it" is the honest
    output, and it is why the status is reported on the card.
    """
    clean = [v for v in developed_fraction if v is not None and not math.isnan(v)]
    if len(clean) < 12:
        return ("no_data", None)

    sm = smooth_median(developed_fraction)
    sm_clean = [v for v in sm if v is not None]
    head = sm_clean[: max(6, len(sm_clean) // 10)]
    tail = sm_clean[-12:]
    head_level, final_level = _median(head), _median(tail)

    if final_level <= 0.05:
        return ("no_signal", None)

    # Already developed when the record opens: no rise left to observe.
    if head_level >= final_level * C.BUILD_COMPLETION_FRACTION:
        first = next((m for m, v in zip(months, sm) if v is not None), None)
        return ("already_built", first)

    # A real ramp needs the plateau to stand clear of the baseline.
    if final_level - head_level < C.BUILD_MIN_RISE:
        return ("no_signal", None)

    threshold = head_level + (final_level - head_level) * C.BUILD_COMPLETION_FRACTION
    idx = first_crossing_index(sm, threshold)
    return ("ramp", months[idx]) if idx is not None else ("no_signal", None)


def observed_build_month(
    months: Sequence[str], developed_fraction: Sequence[float]
) -> str | None:
    """The month construction crossed halfway, or None when no ramp is visible."""
    status, month = build_status(months, developed_fraction)
    return month if status == "ramp" else None


def build_delay_months(
    observed_month: str | None, commissioning_year: float | None
) -> float | None:
    """Months between claimed commissioning and observed substantial build.

    Positive means the satellite record shows the site being built *after* the
    year the operator reports it was commissioned. Claimed commissioning is
    compared against the end of that year, which is the generous reading.
    """
    if observed_month is None or commissioning_year is None:
        return None
    if isinstance(commissioning_year, float) and math.isnan(commissioning_year):
        return None
    year, month = int(observed_month[:4]), int(observed_month[5:7])
    claimed_end = date(int(commissioning_year), 12, 31)
    observed = date(year, month, 15)
    return round((observed - claimed_end).days / 30.44, 1)


# --- Resource --------------------------------------------------------------


def resource_anomaly_pct(annual_ghi: float | None, baseline_ghi: float | None) -> float | None:
    """Percentage difference between a year's GHI and the long-run mean."""
    if not annual_ghi or not baseline_ghi:
        return None
    if baseline_ghi == 0:
        return None
    return round((annual_ghi - baseline_ghi) / baseline_ghi * 100.0, 2)


def mean_or_none(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return round(sum(vals) / len(vals), 3) if vals else None


# --- Thermal derating ------------------------------------------------------


def cell_temperature_c(air_temp_c: float, irradiance_w_m2: float) -> float:
    """NOCT model cell temperature.

    Tcell = Tair + (NOCT - 20) / 800 * G
    """
    return air_temp_c + (C.NOCT_C - 20.0) / C.NOCT_IRRADIANCE_W_M2 * irradiance_w_m2


def thermal_derate_pct(air_temp_c: float, irradiance_w_m2: float = 1000.0) -> float:
    """Indicative output loss from cell temperature above STC, in percent.

    Returns a positive number meaning "percent of output lost". This is an
    order-of-magnitude indicator for screening, not a yield assessment.
    """
    t_cell = cell_temperature_c(air_temp_c, irradiance_w_m2)
    loss = (t_cell - C.STC_CELL_TEMP_C) * C.TEMP_COEFF_PCT_PER_C
    return round(max(0.0, -loss), 2)


# --- Vegetation ------------------------------------------------------------


def linear_trend_per_year(times_years: Sequence[float], values: Sequence[float]) -> float | None:
    """Ordinary least squares slope, in units per year. None if under-determined."""
    pairs = [
        (t, v)
        for t, v in zip(times_years, values)
        if v is not None and not math.isnan(v)
    ]
    if len(pairs) < 4:
        return None
    n = len(pairs)
    mean_t = sum(t for t, _ in pairs) / n
    mean_v = sum(v for _, v in pairs) / n
    num = sum((t - mean_t) * (v - mean_v) for t, v in pairs)
    den = sum((t - mean_t) ** 2 for t, _ in pairs)
    if den == 0:
        return None
    return round(num / den, 5)


# --- Flags and score -------------------------------------------------------


@dataclass
class Flags:
    build_delay: bool = False
    resource_shortfall: bool = False
    thermal_derating: bool = False
    vegetation_encroachment: bool = False
    flood_exposure: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_flags(
    *,
    build_delay_m: float | None,
    mean_resource_anomaly_pct: float | None,
    heat_days_per_year: float | None,
    ndvi_trend_per_year: float | None,
    gsw_occurrence_pct: float | None,
    hand_m: float | None,
) -> Flags:
    """Apply the documented thresholds. Missing evidence never raises a flag."""
    f = Flags()
    if build_delay_m is not None and build_delay_m > C.BUILD_DELAY_FLAG_MONTHS:
        f.build_delay = True
    if (
        mean_resource_anomaly_pct is not None
        and mean_resource_anomaly_pct < C.RESOURCE_ANOMALY_FLAG_PCT
    ):
        f.resource_shortfall = True
    if heat_days_per_year is not None and heat_days_per_year > C.HEAT_DAYS_FLAG:
        f.thermal_derating = True
    if (
        ndvi_trend_per_year is not None
        and ndvi_trend_per_year > C.NDVI_TREND_FLAG_PER_YEAR
    ):
        f.vegetation_encroachment = True
    flood = False
    if gsw_occurrence_pct is not None and gsw_occurrence_pct > C.GSW_OCCURRENCE_FLAG_PCT:
        flood = True
    if hand_m is not None and hand_m < C.HAND_FLAG_M:
        flood = True
    f.flood_exposure = flood
    return f


def flag_score(flags: Flags) -> float:
    """Weighted 0-100 score. Higher means more to investigate."""
    d = flags.as_dict()
    total = sum(C.FLAG_WEIGHTS[k] for k, v in d.items() if v)
    return round(min(total, 100.0), 1)


def traffic_light(score: float) -> str:
    for lo, hi, label in C.TRAFFIC_LIGHT_BANDS:
        if lo <= score < hi:
            return label
    return "red"


def evidence_completeness(values: dict) -> float:
    """Share of the six evidence inputs that were actually resolved, 0-1.

    A high score built on two of six inputs is not the same finding as a high
    score built on six, and the card says so.
    """
    keys = [
        "build_delay_m",
        "mean_resource_anomaly_pct",
        "heat_days_per_year",
        "ndvi_trend_per_year",
        "gsw_occurrence_pct",
        "hand_m",
    ]
    def _resolved(v) -> bool:
        if v is None:
            return False
        try:
            return not math.isnan(float(v))
        except (TypeError, ValueError):
            return True

    present = sum(1 for k in keys if _resolved(values.get(k)))
    return round(present / len(keys), 2)
