"""Build the GitHub Pages view: a portfolio index with a map and a sortable table."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

from . import config as C

LIGHT = {"green": "#1a7f44", "amber": "#b06b00", "red": "#b3261e"}


def _n(v, default=0.0) -> float:
    """Coerce to float, mapping None and NaN to a default.

    pandas hands back NaN for missing values and NaN is truthy, so `v or 0`
    is not enough.
    """
    if v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) else f


def _isna(v) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _rows(records: list[dict]) -> str:
    out = []
    for r in records:
        slug = str(r.get("id") or r.get("name")).replace("/", "-")
        light = r.get("traffic_light", "green")
        flags = r.get("flags") or {}
        fired = ", ".join(k.replace("_", " ") for k, v in flags.items() if v) or "none"
        out.append(
            "<tr>"
            f"<td><a href='cards/{html.escape(slug)}.html'>{html.escape(str(r.get('name')))}</a></td>"
            f"<td data-v='{_n(r.get('capacity_mw'))}'>{_n(r.get('capacity_mw')):,.0f}</td>"
            f"<td data-v='{_n(r.get('score'))}'>"
            f"<span class='pill' style='background:{LIGHT[light]}'>{_n(r.get('score')):.0f}</span></td>"
            f"<td data-v='{_n(r.get('evidence_completeness'))}'>{_n(r.get('evidence_completeness')):.0%}</td>"
            f"<td>{html.escape(fired)}</td>"
            "</tr>"
        )
    return "\n".join(out)


def _markers(records: list[dict]) -> str:
    pts = [
        {
            "name": str(r.get("name")),
            "lat": _n(r.get("latitude")),
            "lon": _n(r.get("longitude")),
            "score": _n(r.get("score")),
            "light": r.get("traffic_light") or "green",
            "mw": _n(r.get("capacity_mw")),
            "slug": str(r.get("id") or r.get("name")).replace("/", "-"),
        }
        for r in records
        if not _isna(r.get("latitude")) and not _isna(r.get("longitude"))
    ]
    return json.dumps(pts, allow_nan=False)


def render_index(records: list[dict], as_of: str) -> str:
    n = len(records)
    counts = {k: sum(1 for r in records if r.get("traffic_light") == k) for k in LIGHT}
    mean_completeness = (
        sum(_n(r.get("evidence_completeness")) for r in records) / n if n else 0
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solar asset assessment — India</title>
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
</head><body>
<main class="site">
<header class="hero">
  <p class="eyebrow">Open-data prototype</p>
  <h1>Solar asset assessment</h1>
  <p class="lede">Every utility-scale solar plant in India above {C.MIN_CAPACITY_MW:.0f} MW in the
    WRI Global Power Plant Database, tested against what satellites actually
    observed at the site. Five checks, published thresholds, one card per asset.</p>
  <p class="lede small">This exists to answer a narrow question: can a reported
    asset record be independently corroborated from free data, quickly enough
    to be worth doing before a diligence site visit? The answer is partly, and
    the cards are explicit about which part.</p>
</header>

<section class="stats">
  <div class="stat"><b>{n}</b><span>assets assessed</span></div>
  <div class="stat"><b style="color:{LIGHT['red']}">{counts['red']}</b><span>red</span></div>
  <div class="stat"><b style="color:{LIGHT['amber']}">{counts['amber']}</b><span>amber</span></div>
  <div class="stat"><b style="color:{LIGHT['green']}">{counts['green']}</b><span>green</span></div>
  <div class="stat"><b>{mean_completeness:.0%}</b><span>mean evidence resolved</span></div>
  <div class="stat"><b class="date">{html.escape(as_of)}</b><span>run date</span></div>
</section>

<section>
  <h2>Where they are</h2>
  <div id="map" style="height:460px;border-radius:10px;overflow:hidden"></div>
  <p class="note">Marker size reflects capacity; colour is the traffic light.</p>
</section>

<section>
  <h2>Portfolio</h2>
  <p class="note">Click a column heading to sort. Score is the weighted sum of
    flags that fired, not a valuation.</p>
  <table class="portfolio" id="pf">
    <thead><tr>
      <th>Asset</th><th>MW</th><th>Score</th><th>Evidence</th><th>Flags fired</th>
    </tr></thead>
    <tbody>{_rows(records)}</tbody>
  </table>
</section>

<section>
  <h2>How the score is built</h2>
  <table class="weights">
    <thead><tr><th>Check</th><th>Weight</th><th>Fires when</th></tr></thead>
    <tbody>
      <tr><td>Build timing</td><td>{C.FLAG_WEIGHTS['build_delay']:.0f}</td>
        <td>observed build more than {C.BUILD_DELAY_FLAG_MONTHS} months after the reported commissioning year ends</td></tr>
      <tr><td>Resource shortfall</td><td>{C.FLAG_WEIGHTS['resource_shortfall']:.0f}</td>
        <td>mean annual GHI anomaly below {C.RESOURCE_ANOMALY_FLAG_PCT}% against 1991-2020</td></tr>
      <tr><td>Thermal derating</td><td>{C.FLAG_WEIGHTS['thermal_derating']:.0f}</td>
        <td>more than {C.HEAT_DAYS_FLAG} days a year above {C.HEAT_DAY_THRESHOLD_C:.0f}°C</td></tr>
      <tr><td>Vegetation</td><td>{C.FLAG_WEIGHTS['vegetation_encroachment']:.0f}</td>
        <td>NDVI trend inside the footprint above {C.NDVI_TREND_FLAG_PER_YEAR:+.3f} per year</td></tr>
      <tr><td>Flood exposure</td><td>{C.FLAG_WEIGHTS['flood_exposure']:.0f}</td>
        <td>surface-water occurrence above {C.GSW_OCCURRENCE_FLAG_PCT:.0f}% or height above drainage under {C.HAND_FLAG_M:.0f} m</td></tr>
    </tbody>
  </table>
</section>

<section class="limits">
  <h2>What this does not do</h2>
  <ul>
    <li>The footprint is a capacity-scaled circle, not a segmented panel array.
      It over-includes surrounding land, which dilutes every area statistic.</li>
    <li>Height above nearest drainage is approximated from a DEM neighbourhood
      minimum. It is a screening proxy, not a hydraulic flood model.</li>
    <li>A flag is a reason to look, never a finding. Nothing here is evidence
      of misreporting by any operator.</li>
    <li>Unresolved checks score as clear, so a score is a lower bound. Each card
      states how much of the rubric was resolved.</li>
    <li>Earth Engine's free tier is for non-commercial use. This is a personal
      methodology prototype.</li>
  </ul>
</section>

<footer class="sitefoot">
  <p>Data: Sentinel-2 (ESA/Copernicus), Dynamic World (Google/WRI),
     ERA5-Land (ECMWF/Copernicus), JRC Global Surface Water,
     Copernicus DEM GLO-30, WRI Global Power Plant Database.
     Processed in Google Earth Engine. Code MIT licensed.</p>
</footer>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const PTS = {_markers(records)};
const COL = {json.dumps(LIGHT)};
const map = L.map('map').setView([22.5, 79.0], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);
PTS.forEach(p => {{
  L.circleMarker([p.lat, p.lon], {{
    radius: Math.max(5, Math.min(18, Math.sqrt(p.mw || 1) / 3)),
    color: COL[p.light] || '#666', fillColor: COL[p.light] || '#666',
    fillOpacity: 0.65, weight: 1.5
  }}).addTo(map).bindPopup(
    `<b>${{p.name}}</b><br>${{(p.mw||0).toLocaleString()}} MW &middot; score ${{p.score}}` +
    `<br><a href="cards/${{p.slug}}.html">assessment card</a>`
  );
}});
if (PTS.length) {{
  map.fitBounds(PTS.map(p => [p.lat, p.lon]), {{padding: [40, 40]}});
}}

// sortable table, no dependency
document.querySelectorAll('#pf thead th').forEach((th, i) => {{
  th.style.cursor = 'pointer';
  let asc = false;
  th.addEventListener('click', () => {{
    asc = !asc;
    const tb = document.querySelector('#pf tbody');
    const rows = Array.from(tb.rows);
    rows.sort((a, b) => {{
      const av = a.cells[i].dataset.v, bv = b.cells[i].dataset.v;
      if (av !== undefined && bv !== undefined) return (asc ? 1 : -1) * (parseFloat(av) - parseFloat(bv));
      return (asc ? 1 : -1) * a.cells[i].innerText.localeCompare(b.cells[i].innerText);
    }});
    rows.forEach(r => tb.appendChild(r));
  }});
}});
</script>
</body></html>
"""


def write_site(records: list[dict], as_of: str, docs_dir: str = "docs") -> str:
    out = Path(docs_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "index.html"
    p.write_text(render_index(records, as_of), encoding="utf-8")
    return str(p)
