"""Earth Engine data extraction.

Each function returns plain Python values so that src/metrics.py can stay
free of Earth Engine. One `getInfo()` per asset per metric, built by mapping
server-side over a date sequence, rather than a call per month.
"""

from __future__ import annotations

import math
from typing import Any

import ee

from . import config as C


# --- session ---------------------------------------------------------------


def init(project: str) -> None:
    """Authenticate and initialise. `project` is your Cloud project id."""
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def asset_geometry(lat: float, lon: float, radius_m: float) -> ee.Geometry:
    return ee.Geometry.Point([float(lon), float(lat)]).buffer(float(radius_m))


def _num(v: Any) -> float | None:
    """Coerce an Earth Engine result to a float, mapping nulls to None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


# --- development fraction (build progress) --------------------------------


def developed_fraction_series(
    geom: ee.Geometry, start: str, end: str
) -> tuple[list[str], list[float | None]]:
    """Monthly share of the footprint classified built or bare by Dynamic World.

    A PV plant reads as 'built' or 'bare' once panels and access roads are in.
    The ramp from near-zero to a plateau is the construction signal.
    """
    col = ee.ImageCollection(C.EE_DW).filterBounds(geom).filterDate(start, end)
    n_months = (
        ee.Date(end).difference(ee.Date(start), "month").floor().subtract(1)
    )
    months = ee.List.sequence(0, n_months)

    def month_feat(i):
        s = ee.Date(start).advance(ee.Number(i), "month")
        e = s.advance(1, "month")
        sub = col.filterDate(s, e)
        val = ee.Algorithms.If(
            sub.size().gt(0),
            sub.select("label")
            .mode()
            .remap([C.DW_BUILT, C.DW_BARE], [1, 1], 0)
            .rename("dev")
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=C.REDUCE_SCALE_M,
                maxPixels=1e9,
                bestEffort=True,
            )
            .get("dev"),
            None,
        )
        return ee.Feature(None, {"month": s.format("YYYY-MM"), "dev": val})

    fc = ee.FeatureCollection(months.map(month_feat))
    rows = fc.getInfo()["features"]
    out_m, out_v = [], []
    for r in rows:
        p = r["properties"]
        out_m.append(p.get("month"))
        out_v.append(_num(p.get("dev")))
    return out_m, out_v


# --- vegetation ------------------------------------------------------------


def _mask_s2(img: ee.Image) -> ee.Image:
    scl = img.select("SCL")
    mask = ee.Image.constant(1)
    for cls in C.S2_SCL_MASK_CLASSES:
        mask = mask.And(scl.neq(cls))
    return img.updateMask(mask)


def ndvi_annual_series(
    geom: ee.Geometry, start: str, end: str
) -> tuple[list[float], list[float | None]]:
    """Mean NDVI inside the footprint, one value per calendar year.

    Inside a working solar farm NDVI should be low and flat. A rising trend is
    vegetation growth: low-angle shading, and an O&M signal.
    """
    col = (
        ee.ImageCollection(C.EE_S2)
        .filterBounds(geom)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", C.S2_MAX_CLOUD_PCT))
        .map(_mask_s2)
    )
    y0 = int(start[:4])
    y1 = int(end[:4]) - 1
    years = ee.List.sequence(y0, y1)

    def year_feat(y):
        s = ee.Date.fromYMD(ee.Number(y), 1, 1)
        e = s.advance(1, "year")
        sub = col.filterDate(s, e)
        val = ee.Algorithms.If(
            sub.size().gt(0),
            sub.median()
            .normalizedDifference(["B8", "B4"])
            .rename("ndvi")
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=C.REDUCE_SCALE_M,
                maxPixels=1e9,
                bestEffort=True,
            )
            .get("ndvi"),
            None,
        )
        return ee.Feature(None, {"year": y, "ndvi": val})

    rows = ee.FeatureCollection(years.map(year_feat)).getInfo()["features"]
    out_y, out_v = [], []
    for r in rows:
        p = r["properties"]
        out_y.append(float(p.get("year")))
        out_v.append(_num(p.get("ndvi")))
    return out_y, out_v


# --- climate ---------------------------------------------------------------


def era5_annual(
    geom: ee.Geometry, start_year: int, end_year: int
) -> list[dict]:
    """Annual GHI (kWh/m2), heat-day count and mean daily max temperature."""
    col = ee.ImageCollection(C.EE_ERA5_DAILY).filterBounds(geom)
    years = ee.List.sequence(start_year, end_year)

    def year_feat(y):
        s = ee.Date.fromYMD(ee.Number(y), 1, 1)
        e = s.advance(1, "year")
        sub = col.filterDate(s, e)

        ghi = (
            sub.select("surface_solar_radiation_downwards_sum")
            .sum()
            .divide(3.6e6)
            .rename("ghi")
        )
        tmax_c = sub.map(
            lambda im: im.select("temperature_2m_max").subtract(273.15).rename("tmax")
        )
        heat_days = tmax_c.map(
            lambda im: im.gt(C.HEAT_DAY_THRESHOLD_C)
        ).sum().rename("heat_days")
        mean_tmax = tmax_c.mean().rename("mean_tmax")

        stats = (
            ghi.addBands(heat_days)
            .addBands(mean_tmax)
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=C.ERA5_SCALE_M,
                maxPixels=1e9,
                bestEffort=True,
            )
        )
        return ee.Feature(
            None,
            {
                "year": y,
                "ghi": stats.get("ghi"),
                "heat_days": stats.get("heat_days"),
                "mean_tmax": stats.get("mean_tmax"),
            },
        )

    rows = ee.FeatureCollection(years.map(year_feat)).getInfo()["features"]
    return [
        {
            "year": int(r["properties"]["year"]),
            "ghi_kwh_m2": _num(r["properties"].get("ghi")),
            "heat_days": _num(r["properties"].get("heat_days")),
            "mean_tmax_c": _num(r["properties"].get("mean_tmax")),
        }
        for r in rows
    ]


def era5_baseline_ghi(geom: ee.Geometry) -> float | None:
    """Mean annual GHI over the climatological baseline, kWh/m2."""
    col = (
        ee.ImageCollection(C.EE_ERA5_DAILY)
        .filterBounds(geom)
        .filterDate(C.ERA5_BASELINE_START, C.ERA5_BASELINE_END)
        .select("surface_solar_radiation_downwards_sum")
    )
    n_years = (
        int(C.ERA5_BASELINE_END[:4]) - int(C.ERA5_BASELINE_START[:4]) + 1
    )
    total = col.sum().divide(3.6e6).divide(n_years).rename("ghi")
    v = total.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=C.ERA5_SCALE_M,
        maxPixels=1e9,
        bestEffort=True,
    ).get("ghi")
    return _num(v.getInfo())


# --- water and terrain -----------------------------------------------------


def water_and_terrain(geom: ee.Geometry) -> dict:
    """Surface-water occurrence inside the footprint and height above drainage.

    HAND is approximated as mean site elevation minus the minimum elevation
    within a surrounding neighbourhood. It is a screening proxy, not a
    hydraulic model, and the README says so.
    """
    gsw = ee.Image(C.EE_GSW).select("occurrence").unmask(0)
    occ = gsw.reduceRegion(
        reducer=ee.Reducer.max(),
        geometry=geom,
        scale=30,
        maxPixels=1e9,
        bestEffort=True,
    ).get("occurrence")

    dem = ee.ImageCollection(C.EE_DEM).select("DEM").mosaic()
    site_elev = dem.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=90,
        maxPixels=1e9,
        bestEffort=True,
    ).get("DEM")
    nbr_min = dem.reduceRegion(
        reducer=ee.Reducer.min(),
        geometry=geom.buffer(C.HAND_NEIGHBOURHOOD_M),
        scale=90,
        maxPixels=1e9,
        bestEffort=True,
    ).get("DEM")

    res = ee.Dictionary(
        {"occ": occ, "site": site_elev, "nbr": nbr_min}
    ).getInfo()

    site = _num(res.get("site"))
    nbr = _num(res.get("nbr"))
    hand = round(site - nbr, 1) if (site is not None and nbr is not None) else None
    return {
        "gsw_occurrence_pct": _num(res.get("occ")),
        "elevation_m": site,
        "hand_m": hand,
    }


# --- thumbnail -------------------------------------------------------------


def rgb_thumbnail_url(geom: ee.Geometry, year: int, dim: int = 600) -> str | None:
    """A true-colour Sentinel-2 median for one year, as a static PNG url.

    Used on the assessment card so a reader can see the site rather than only
    read numbers about it.
    """
    try:
        col = (
            ee.ImageCollection(C.EE_S2)
            .filterBounds(geom)
            .filterDate(f"{year}-01-01", f"{year}-12-31")
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", C.S2_MAX_CLOUD_PCT))
            .map(_mask_s2)
        )
        if col.size().getInfo() == 0:
            return None
        img = col.median().select(["B4", "B3", "B2"])
        return img.getThumbURL(
            {
                "region": geom.bounds(),
                "dimensions": dim,
                "min": 0,
                "max": 3000,
                "format": "png",
            }
        )
    except Exception:
        return None
