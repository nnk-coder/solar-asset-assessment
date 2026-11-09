"""Render one assessment record as a self-contained HTML card.

The card is the deliverable. It is written so that a reader who has never
seen the code can tell what was measured, what threshold was applied, and how
much of the rubric was actually resolved.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

from . import config as C

LIGHT = {"green": "#1a7f44", "amber": "#b06b00", "red": "#b3261e"}
TINT = {"green": "#e7f4ec", "amber": "#fdf1de", "red": "#fbeae8"}

FLAG_LABELS = {
    "build_delay": "Build timing vs. reported commissioning",
    "resource_shortfall": "Solar resource vs. 1991-2020 baseline",
    "thermal_derating": "Heat exposure and thermal derating",
    "vegetation_encroachment": "Vegetation trend inside the footprint",
    "flood_exposure": "Surface water and height above drainage",
}

FLAG_RULES = {
    "build_delay": f"flagged when observed build is more than {C.BUILD_DELAY_FLAG_MONTHS} months after the end of the reported commissioning year",
    "resource_shortfall": f"flagged when mean annual GHI anomaly is below {C.RESOURCE_ANOMALY_FLAG_PCT}%",
    "thermal_derating": f"flagged above {C.HEAT_DAYS_FLAG} days per year over {C.HEAT_DAY_THRESHOLD_C}°C",
    "vegetation_encroachment": f"flagged when the NDVI trend exceeds {C.NDVI_TREND_FLAG_PER_YEAR:+.3f} per year",
    "flood_exposure": f"flagged when surface-water occurrence exceeds {C.GSW_OCCURRENCE_FLAG_PCT}% or height above drainage is under {C.HAND_FLAG_M} m",
}


NOT_RESOLVED = "<span class='na'>not resolved</span>"


def _isna(v) -> bool:
    """True for None and for float NaN, which pandas uses for a missing value.

    NaN is truthy, so a bare `if value:` check lets it through. That mistake
    cost a 40-minute Earth Engine run once; hence this helper and its tests.
    """
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _e(v) -> str:
    return html.escape(str(v)) if not _isna(v) else "&mdash;"


def _fmt(v, suffix: str = "", nd: int = 1) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if _isna(v):
        return NOT_RESOLVED
    if isinstance(v, bool):
        return "yes" if v else "no"
    try:
        return f"{float(v):,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _sparkline(values, width=260, height=44, colour="#2b6cb0") -> str:
    """A tiny inline SVG line. No library, no build step."""
    pts = [(i, float(v)) for i, v in enumerate(values or []) if not _isna(v)]
    if len(pts) < 2:
        return "<span class='na'>no series</span>"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    span_x = (x1 - x0) or 1
    span_y = (y1 - y0) or 1
    coords = " ".join(
        f"{(x - x0) / span_x * (width - 4) + 2:.1f},"
        f"{height - 2 - (y - y0) / span_y * (height - 8):.1f}"
        for x, y in pts
    )
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"role='img' aria-label='time series'>"
        f"<polyline fill='none' stroke='{colour}' stroke-width='2' "
        f"stroke-linejoin='round' points='{coords}'/></svg>"
        f"<span class='range'>{y0:,.3g} to {y1:,.3g} over {len(pts)} points</span>"
    )


def _evidence_rows(r: dict) -> str:
    rows = [
        (
            "Reported commissioning year",
            NOT_RESOLVED if _isna(r.get("commissioning_year"))
            else _e(int(float(r["commissioning_year"]))),
            "WRI Global Power Plant Database",
        ),
        (
            "First month substantially built",
            _e(r.get("observed_build_month")),
            "Dynamic World built + bare share of footprint",
        ),
        (
            "Build timing difference",
            _fmt(r.get("build_delay_m"), " months"),
            "positive = built after the reported year",
        ),
        (
            "Mean annual GHI anomaly",
            _fmt(r.get("mean_resource_anomaly_pct"), "%", 2),
            "ERA5-Land vs. 1991-2020 mean",
        ),
        (
            "Baseline annual GHI",
            _fmt(r.get("baseline_ghi_kwh_m2"), " kWh/m²", 0),
            "ERA5-Land 1991-2020",
        ),
        (
            f"Days per year above {C.HEAT_DAY_THRESHOLD_C:.0f}°C",
            _fmt(r.get("heat_days_per_year"), " days", 0),
            "ERA5-Land daily maximum 2 m temperature",
        ),
        (
            "Indicative thermal derating",
            _fmt(r.get("thermal_derate_pct"), "%", 2),
            f"NOCT model, {C.TEMP_COEFF_PCT_PER_C}%/°C, at 1000 W/m²",
        ),
        (
            "NDVI trend inside footprint",
            _fmt(r.get("ndvi_trend_per_year"), " /year", 4),
            "Sentinel-2 annual median, OLS slope",
        ),
        (
            "Surface-water occurrence",
            _fmt(r.get("gsw_occurrence_pct"), "%", 0),
            "JRC Global Surface Water, 1984-2021",
        ),
        (
            "Height above nearest drainage",
            _fmt(r.get("hand_m"), " m"),
            f"Copernicus DEM, {C.HAND_NEIGHBOURHOOD_M:.0f} m neighbourhood",
        ),
    ]
    return "\n".join(
        f"<tr><th scope='row'>{html.escape(k)}</th><td>{v}</td>"
        f"<td class='src'>{html.escape(s)}</td></tr>"
        for k, v, s in rows
    )


def _flag_rows(r: dict) -> str:
    out = []
    for key, fired in (r.get("flags") or {}).items():
        mark = "FLAGGED" if fired else "clear"
        cls = "fired" if fired else "clear"
        out.append(
            f"<li class='{cls}'><span class='mark'>{mark}</span>"
            f"<span class='flabel'>{html.escape(FLAG_LABELS[key])}</span>"
            f"<span class='weight'>weight {C.FLAG_WEIGHTS[key]:.0f}</span>"
            f"<span class='rule'>{html.escape(FLAG_RULES[key])}</span></li>"
        )
    return "\n".join(out)


def render_card(r: dict) -> str:
    light = r.get("traffic_light", "green")
    colour = LIGHT[light]
    tint = TINT[light]
    completeness = r.get("evidence_completeness", 0.0)
    thumb = r.get("thumbnail_url")
    thumb_html = (
        f"<img src='{html.escape(thumb)}' alt='Sentinel-2 true colour composite "
        f"of the site' loading='lazy'>"
        if thumb
        else "<div class='nothumb'>no cloud-free composite available</div>"
    )
    caveat = ""
    if completeness < 1.0:
        caveat = (
            f"<p class='caveat'><b>{completeness:.0%} of the rubric was resolved.</b> "
            f"Unresolved checks are shown as <i>not resolved</i> and were scored as "
            f"clear, so this score is a lower bound on what the evidence might show.</p>"
        )
    errors = ""
    if r.get("errors"):
        items = "".join(f"<li>{html.escape(str(e))}</li>" for e in r["errors"])
        errors = f"<details class='errors'><summary>Query errors ({len(r['errors'])})</summary><ul>{items}</ul></details>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(r.get('name')))} — asset assessment</title>
<link rel="stylesheet" href="../assets/style.css">
</head><body class="card-page">
<article class="card">
  <header style="border-left:10px solid {colour};background:{tint}">
    <p class="eyebrow">Solar asset assessment card</p>
    <h1>{html.escape(str(r.get('name')))}</h1>
    <p class="sub">{_fmt(r.get('capacity_mw'), ' MW', 0)} &middot;
      {_fmt(r.get('latitude'), '', 4)}, {_fmt(r.get('longitude'), '', 4)} &middot;
      operator {_e(r.get('owner'))}</p>
    <div class="scorebox">
      <div class="score" style="color:{colour}">{r.get('score', 0):.0f}<span>/100</span></div>
      <div class="light" style="background:{colour}">{light.upper()}</div>
      <div class="meta">
        <div>Evidence resolved: <b>{completeness:.0%}</b></div>
        <div>Footprint proxy: <b>{_fmt(r.get('footprint_radius_m'), ' m radius', 0)}</b></div>
        <div>Assessed: <b>{_e(r.get('as_of'))}</b></div>
      </div>
    </div>
  </header>

  <section class="imagery">
    <h2>Site</h2>
    <div class="thumb">{thumb_html}</div>
    <div class="series">
      <p class="slabel">Share of footprint built or bare, monthly since {C.S2_START[:4]}</p>
      {_sparkline(r.get('dev_fraction'), colour='#2b6cb0')}
      <p class="slabel">Mean NDVI inside the footprint, annual</p>
      {_sparkline(r.get('ndvi_values'), colour='#1a7f44')}
    </div>
  </section>

  <section>
    <h2>What was measured</h2>
    <table class="evidence">
      <thead><tr><th>Measure</th><th>Value</th><th>Source</th></tr></thead>
      <tbody>{_evidence_rows(r)}</tbody>
    </table>
    {caveat}
  </section>

  <section>
    <h2>Rubric</h2>
    <ul class="flags">{_flag_rows(r)}</ul>
    <p class="note">The score is the sum of the weights of the flags that fired.
      It ranks sites for attention. It is not a valuation, a yield estimate, or a
      statement about the operator.</p>
    {errors}
  </section>

  <footer>
    <p>Reported record: WRI Global Power Plant Database
      {('&middot; <a href="' + html.escape(str(r.get('source_url'))) + '">operator source</a>') if r.get('source_url') else ''}
    </p>
    <p><a href="../index.html">&larr; back to the portfolio</a></p>
  </footer>
</article>
</body></html>
"""


def write_cards(records: list[dict], docs_dir: str = "docs") -> list[str]:
    out = Path(docs_dir) / "cards"
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in records:
        slug = str(r.get("id") or r.get("name")).replace("/", "-")
        p = out / f"{slug}.html"
        p.write_text(render_card(r), encoding="utf-8")
        paths.append(str(p))
    return paths
