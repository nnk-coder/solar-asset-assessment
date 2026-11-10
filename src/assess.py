"""Orchestration: turn one power-plant record into one assessment record.

This is the only module that touches both Earth Engine and the metrics layer.
It catches per-asset failures so that one bad geometry does not end the run.
"""

from __future__ import annotations

import datetime as _dt
import math
import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import config as C
from . import gee, metrics as M


# --- asset list ------------------------------------------------------------


def load_assets(
    csv_path: str | None = None,
    country: str = C.COUNTRY,
    fuel: str = C.PRIMARY_FUEL,
    min_mw: float = C.MIN_CAPACITY_MW,
    limit: int | None = None,
) -> pd.DataFrame:
    """Utility-scale solar plants from the WRI Global Power Plant Database.

    WRI is an open, widely cited inventory. It is also incomplete and partly
    stale, which is the point: the exercise is to test reported records
    against observation, so a reported record is what we start from.
    """
    src = csv_path or C.WRI_CSV_URL
    df = pd.read_csv(src, low_memory=False)
    df = df[
        (df["country_long"] == country)
        & (df["primary_fuel"] == fuel)
        & (df["capacity_mw"] >= min_mw)
    ].copy()
    df = df.dropna(subset=["latitude", "longitude"])
    df = df.sort_values("capacity_mw", ascending=False).reset_index(drop=True)
    if limit:
        df = df.head(limit)
    return df[
        [
            "gppd_idnr",
            "name",
            "capacity_mw",
            "latitude",
            "longitude",
            "commissioning_year",
            "owner",
            "url",
        ]
    ]


# --- one asset -------------------------------------------------------------


def assess_asset(row: dict, as_of: str | None = None) -> dict:
    """Run every evidence query for one asset and apply the rubric."""
    as_of = as_of or _dt.date.today().isoformat()
    end = f"{int(as_of[:4])}-01-01"

    capacity = float(row.get("capacity_mw") or 0.0)
    radius = M.buffer_radius_m(capacity)
    geom = gee.asset_geometry(row["latitude"], row["longitude"], radius)

    record: dict[str, Any] = {
        "id": row.get("gppd_idnr"),
        "name": row.get("name"),
        "capacity_mw": capacity,
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "commissioning_year": row.get("commissioning_year"),
        "owner": row.get("owner"),
        "source_url": row.get("url"),
        "footprint_radius_m": round(radius),
        "as_of": as_of,
        "errors": [],
    }

    # Build progress ------------------------------------------------------
    try:
        months, dev = gee.developed_fraction_series(geom, C.S2_START, end)
        record["dev_months"] = months
        record["dev_fraction"] = dev
        status, month = M.build_status(months, dev)
        record["build_status"] = status
        obs = month if status == "ramp" else None
        record["observed_build_month"] = obs
        record["build_delay_m"] = M.build_delay_months(
            obs, row.get("commissioning_year")
        )
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"build: {exc}")
        record["build_delay_m"] = None

    # Resource and heat ---------------------------------------------------
    try:
        y0, y1 = int(C.S2_START[:4]), int(as_of[:4]) - 1
        annual = gee.era5_annual(geom, y0, y1)
        baseline = gee.era5_baseline_ghi(geom)
        record["baseline_ghi_kwh_m2"] = baseline
        for a in annual:
            a["anomaly_pct"] = M.resource_anomaly_pct(a["ghi_kwh_m2"], baseline)
        record["annual_climate"] = annual
        record["mean_resource_anomaly_pct"] = M.mean_or_none(
            [a["anomaly_pct"] for a in annual]
        )
        record["heat_days_per_year"] = M.mean_or_none(
            [a["heat_days"] for a in annual]
        )
        mean_tmax = M.mean_or_none([a["mean_tmax_c"] for a in annual])
        record["mean_tmax_c"] = mean_tmax
        record["thermal_derate_pct"] = (
            M.thermal_derate_pct(mean_tmax) if mean_tmax is not None else None
        )
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"climate: {exc}")
        record["mean_resource_anomaly_pct"] = None
        record["heat_days_per_year"] = None

    # Vegetation ----------------------------------------------------------
    try:
        years, ndvi = gee.ndvi_annual_series(geom, C.S2_START, end)
        record["ndvi_years"] = years
        record["ndvi_values"] = ndvi
        record["ndvi_trend_per_year"] = M.linear_trend_per_year(years, ndvi)
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"ndvi: {exc}")
        record["ndvi_trend_per_year"] = None

    # Water and terrain ---------------------------------------------------
    try:
        wt = gee.water_and_terrain(geom)
        record.update(wt)
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"water: {exc}")
        record["gsw_occurrence_pct"] = None
        record["hand_m"] = None

    # Thumbnail -----------------------------------------------------------
    record["thumbnail_url"] = gee.rgb_thumbnail_url(geom, int(as_of[:4]) - 1)

    # Rubric --------------------------------------------------------------
    inputs = {
        "build_delay_m": record.get("build_delay_m"),
        "mean_resource_anomaly_pct": record.get("mean_resource_anomaly_pct"),
        "heat_days_per_year": record.get("heat_days_per_year"),
        "ndvi_trend_per_year": record.get("ndvi_trend_per_year"),
        "gsw_occurrence_pct": record.get("gsw_occurrence_pct"),
        "hand_m": record.get("hand_m"),
    }
    flags = M.evaluate_flags(**inputs)
    record["flags"] = flags.as_dict()
    record["score"] = M.flag_score(flags)
    record["traffic_light"] = M.traffic_light(record["score"])
    record["evidence_completeness"] = M.evidence_completeness(inputs)
    return record


def assess_portfolio(df: pd.DataFrame, as_of: str | None = None) -> list[dict]:
    out = []
    for _, row in df.iterrows():
        rec = assess_asset(row.to_dict(), as_of=as_of)
        out.append(rec)
        print(
            f"  {rec['name'][:38]:<38} "
            f"score {rec['score']:>5.1f} "
            f"{rec['traffic_light']:<5} "
            f"evidence {rec['evidence_completeness']:.0%}"
            + (f"  [{len(rec['errors'])} error(s)]" if rec["errors"] else "")
        )
    return out


def save_results(records: list[dict], outputs_dir: str = "outputs") -> dict:
    """Write results.json and results.csv. Returns the paths written."""
    out = Path(outputs_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _clean(o):
        """NaN is not valid JSON. Replace it with null so other tools can read this."""
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        if isinstance(o, float) and math.isnan(o):
            return None
        return o

    json_path = out / "results.json"
    json_path.write_text(
        json.dumps(_clean(records), indent=2, default=str, allow_nan=False)
    )

    flat = []
    for r in records:
        flat.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "capacity_mw": r.get("capacity_mw"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "commissioning_year": r.get("commissioning_year"),
                "observed_build_month": r.get("observed_build_month"),
                "build_delay_m": r.get("build_delay_m"),
                "mean_resource_anomaly_pct": r.get("mean_resource_anomaly_pct"),
                "heat_days_per_year": r.get("heat_days_per_year"),
                "mean_tmax_c": r.get("mean_tmax_c"),
                "thermal_derate_pct": r.get("thermal_derate_pct"),
                "ndvi_trend_per_year": r.get("ndvi_trend_per_year"),
                "gsw_occurrence_pct": r.get("gsw_occurrence_pct"),
                "hand_m": r.get("hand_m"),
                "score": r.get("score"),
                "traffic_light": r.get("traffic_light"),
                "evidence_completeness": r.get("evidence_completeness"),
                **{f"flag_{k}": v for k, v in (r.get("flags") or {}).items()},
            }
        )
    csv_path = out / "results.csv"
    pd.DataFrame(flat).to_csv(csv_path, index=False)
    return {"json": str(json_path), "csv": str(csv_path)}
