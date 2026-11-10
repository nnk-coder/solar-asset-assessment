"""One assessment card per asset.

Written so a reader who has never seen the code can tell what was measured,
which threshold was applied, and how much of the rubric was actually resolved.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

from . import charts, config as C
from .site import BAND, LIGHT, display_name

TINT = {"green": "#e7f4ec", "amber": "#fdf1de", "red": "#fbeae8"}
NOT_RESOLVED = "<span class='na'>not resolved</span>"

FLAG_LABELS = {
    "build_delay": "Was it built when the record says?",
    "resource_shortfall": "Is there as much sun as expected?",
    "thermal_derating": "Does it run too hot to perform?",
    "vegetation_encroachment": "Is vegetation taking the site back?",
    "flood_exposure": "Could water reach it?",
}

FLAG_RULES = {
    "build_delay": f"Raised when construction appears more than {C.BUILD_DELAY_FLAG_MONTHS} months after the reported commissioning year ends.",
    "resource_shortfall": f"Raised when average yearly sunlight runs more than {abs(C.RESOURCE_ANOMALY_FLAG_PCT):.0f}% below the 1991–2020 norm for that spot.",
    "thermal_derating": f"Raised above {C.HEAT_DAYS_FLAG} days a year over {C.HEAT_DAY_THRESHOLD_C:.0f}°C. Panels lose roughly {abs(C.TEMP_COEFF_PCT_PER_C)}% of output per °C above 25°C.",
    "vegetation_encroachment": f"Raised when greenness inside the footprint climbs by more than {C.NDVI_TREND_FLAG_PER_YEAR:+.3f} a year.",
    "flood_exposure": f"Raised when standing water has covered part of the site more than {C.GSW_OCCURRENCE_FLAG_PCT:.0f}% of the time since 1984, or the ground sits under {C.HAND_FLAG_M:.0f} m above the nearest drainage line.",
}

BUILD_STATUS_TEXT = {
    "ramp": "Construction visible in the imagery",
    "already_built": "Already built before the satellite record opens",
    "no_signal": "No clear construction signal — too noisy to read",
    "no_data": "Too few usable observations",
}


def _isna(v) -> bool:
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
    try:
        return f"{float(v):,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _img(r: dict, key: str) -> str | None:
    """Cards live in docs/cards/, so a site-relative local path needs ../."""
    local = r.get(key + "_local")
    if local:
        local = str(local)
        return "../" + local if local.startswith("assets/") else local
    return r.get(key + "_url") or r.get(key) or None


def _evidence_rows(r: dict) -> str:
    status = r.get("build_status")
    build_cell = (
        html.escape(BUILD_STATUS_TEXT.get(status, "")) if status else NOT_RESOLVED
    )
    if status == "ramp" and r.get("observed_build_month"):
        build_cell += f" &mdash; {html.escape(str(r['observed_build_month']))}"

    rows = [
        (
            "Build year on record",
            NOT_RESOLVED if _isna(r.get("commissioning_year"))
            else _e(int(float(r["commissioning_year"]))),
            "WRI Global Power Plant Database",
        ),
        ("What the imagery shows", build_cell,
         "Dynamic World, built or bare share of the footprint"),
        ("Difference", _fmt(r.get("build_delay_m"), " months"),
         "positive means built after the reported year"),
        ("Sunlight vs. the local norm", _fmt(r.get("mean_resource_anomaly_pct"), "%", 2),
         "ERA5-Land against its own 1991–2020 average (GHI)"),
        ("Typical yearly sunlight", _fmt(r.get("baseline_ghi_kwh_m2"), " kWh/m²", 0),
         "ERA5-Land 1991–2020 average"),
        (f"Days a year above {C.HEAT_DAY_THRESHOLD_C:.0f}°C",
         _fmt(r.get("heat_days_per_year"), " days", 0),
         "ERA5-Land daily maximum air temperature"),
        ("Output lost to heat", _fmt(r.get("thermal_derate_pct"), "%", 1),
         f"standard cell-temperature model at {C.TEMP_COEFF_PCT_PER_C}%/°C"),
        ("Greenness trend on site", _fmt(r.get("ndvi_trend_per_year"), " a year", 4),
         "Sentinel-2 yearly median, straight-line trend (NDVI)"),
        ("Time this ground has been under water",
         _fmt(r.get("gsw_occurrence_pct"), "%", 0),
         "JRC Global Surface Water, 1984–2021"),
        ("Height above nearest drainage", _fmt(r.get("hand_m"), " m"),
         f"Copernicus DEM, {C.HAND_NEIGHBOURHOOD_M:.0f} m around the site (HAND)"),
    ]
    return "\n".join(
        f"<tr><th scope='row'>{html.escape(k)}</th><td>{v}</td>"
        f"<td class='src'>{html.escape(s) if '<' not in s else s}</td></tr>"
        for k, v, s in rows
    )


def _flag_rows(r: dict) -> str:
    out = []
    for key, fired in (r.get("flags") or {}).items():
        cls = "fired" if fired else "clear"
        mark = "FLAG" if fired else "clear"
        out.append(
            f"<li class='{cls}'><span class='mark'>{mark}</span>"
            f"<span class='flabel'>{html.escape(FLAG_LABELS[key])}</span>"
            f"<span class='weight'>{C.FLAG_WEIGHTS[key]:.0f} pts</span>"
            f"<span class='rule'>{FLAG_RULES[key]}</span></li>"
        )
    return "\n".join(out)


def render_card(r: dict) -> str:
    name = display_name(r)
    light = r.get("traffic_light", "green")
    colour, tint = LIGHT[light], TINT[light]
    completeness = r.get("evidence_completeness") or 0.0
    score = r.get("score") or 0.0

    thumb = _img(r, "thumbnail")
    thumb_html = (
        f"<img src='{html.escape(thumb)}' alt='Satellite view of {html.escape(name)}' loading='lazy'>"
        if thumb
        else "<div class='nothumb'>No cloud-free composite available</div>"
    )

    dev_chart = charts.line_chart(
        r.get("dev_months") or [],
        r.get("dev_fraction") or [],
        width=640, height=230, colour="var(--series-1)",
        y_decimals=2, aria="share of the footprint reading as built or bare",
    )
    ndvi_chart = charts.line_chart(
        [str(int(y)) for y in (r.get("ndvi_years") or [])],
        r.get("ndvi_values") or [],
        width=640, height=230, colour="var(--series-2)",
        y_decimals=2, aria="greenness inside the footprint",
    )

    caveat = ""
    if completeness < 1.0:
        missing = round((1 - completeness) * 6)
        caveat = (
            f"<p class='caveat'><b>{missing} of six checks could not be "
            f"resolved.</b> They are shown as <i>not resolved</i> and counted as "
            f"clear, so this risk score is a <b>lower bound</b> &mdash; the evidence "
            f"that is missing could only push it up.</p>"
        )

    errors = ""
    if r.get("errors"):
        items = "".join(f"<li>{html.escape(str(e))}</li>" for e in r["errors"])
        errors = (
            f"<details class='errors'><summary>Query errors "
            f"({len(r['errors'])})</summary><ul>{items}</ul></details>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} — assessment card</title>
<link rel="stylesheet" href="../assets/style.css">
</head><body class="card-page">
<article class="card">
  <header style="border-left:10px solid {colour};background:{tint}">
    <p class="eyebrow">Solar asset assessment</p>
    <h1>{html.escape(name)}</h1>
    <p class="sub">{_fmt(r.get('capacity_mw'), ' MW', 0)} &middot;
      {_fmt(r.get('latitude'), '', 4)}, {_fmt(r.get('longitude'), '', 4)}
      {('&middot; ' + html.escape(str(r.get('owner')))) if not _isna(r.get('owner')) else ''}</p>
    <div class="scorebox">
      <div>
        <div class="score" style="color:{colour}">{score:.0f}<span>/100</span></div>
        <div class="scorelabel">risk score</div>
      </div>
      <div class="light" style="background:{colour}">{html.escape(BAND[light])}</div>
      <div class="ringbox">
        {charts.completeness_ring(completeness)}
        <span>of checks<br>resolved</span>
      </div>
      <div class="meta">
        <div>Footprint used: <b>{_fmt(r.get('footprint_radius_m'), ' m radius', 0)}</b></div>
        <div>Assessed: <b>{_e(r.get('as_of'))}</b></div>
      </div>
    </div>
  </header>

  <section class="imagery">
    <h2>The site</h2>
    <div class="thumb">{thumb_html}
      <p class="note">True-colour Sentinel-2 composite over the footprint.</p>
    </div>
    <div class="series">
      <p class="slabel">Share of the footprint reading as built or bare ground</p>
      {dev_chart}
      <p class="slabel">How green the ground is inside the footprint</p>
      {ndvi_chart}
      <p class="note">Built-ground share moves with the seasons as well as with
        construction, which is why a construction date is only reported when a
        clear rise is visible.</p>
    </div>
  </section>

  <section>
    <h2>The five checks</h2>
    <ul class="flags">{_flag_rows(r)}</ul>
    {charts.weight_bars(C.FLAG_WEIGHTS, r.get('flags'))}
    <p class="note">Filled bars are the checks that flagged. The risk score is
      their combined weight. It ranks what to examine &mdash; it is not a
      valuation, a yield estimate, or a statement about the operator.</p>
    {caveat}
  </section>

  <section>
    <h2>Every measurement behind it</h2>
    <table class="evidence">
      <thead><tr><th>What was measured</th><th>Value</th><th>Where it comes from</th></tr></thead>
      <tbody>{_evidence_rows(r)}</tbody>
    </table>
    {errors}
  </section>

  <footer>
    <p>Reported record: WRI Global Power Plant Database
      {('&middot; <a href="' + html.escape(str(r.get('source_url'))) + '">operator source</a>') if r.get('source_url') and not _isna(r.get('source_url')) else ''}</p>
    <p><a class="btn" href="../index.html">&larr; Back to the portfolio</a></p>
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
