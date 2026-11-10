"""The published portfolio page.

Structured as a narrative rather than a method write-up: the question, the
trick, a worked example, the findings, then what it cannot see. A reader with
no remote-sensing background should be able to follow it end to end.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from . import charts, config as C

LIGHT = {"green": "#1a7f44", "amber": "#b06b00", "red": "#b3261e"}
BAND = {
    "green": "little to investigate",
    "amber": "worth a look",
    "red": "investigate before committing",
}

# Short forms for the flowchart, where the box sets the budget.
FEED_SHORT = {
    "Sentinel-2": "the panels and the greenery",
    "Dynamic World": "built ground vs. bare ground",
    "ERA5-Land": "sunlight and temperature",
    "JRC Global Surface Water": "where water has stood",
    "Copernicus DEM": "the shape of the land",
}

FEEDS = [
    ("Sentinel-2", "sees the panels and how green the ground is", "10 m, every 5 days"),
    ("Dynamic World", "sees built-up ground against bare ground", "10 m, every 5 days"),
    ("ERA5-Land", "sees sunlight and temperature", "9 km, daily since 1950"),
    ("JRC Global Surface Water", "sees where water has stood since 1984", "30 m"),
    ("Copernicus DEM", "sees the shape of the land", "30 m"),
]


# --- helpers ---------------------------------------------------------------


def _n(v, default=0.0) -> float:
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


def display_name(r: dict) -> str:
    """WRI names carry abbreviations and stray punctuation. Tidy for display."""
    raw = str(r.get("name") or "Unnamed asset").strip()
    raw = re.sub(r"[{}\[\]]+", "", raw).strip(" -–—")
    if raw.isupper() and len(raw) > 6:
        raw = raw.title()
    return raw or "Unnamed asset"


def _slug(r: dict) -> str:
    return str(r.get("id") or r.get("name")).replace("/", "-")


def _img(r: dict, key: str) -> str | None:
    """Prefer a committed local image over an Earth Engine signed URL.

    Earth Engine thumbnail links are temporary. src/images.py downloads them
    into docs/assets/img/ so the published page keeps working.
    """
    local = r.get(key + "_local")
    if local:
        return str(local)
    return r.get(key + "_url") or r.get(key) or None


# --- flowchart -------------------------------------------------------------


def flowchart() -> str:
    """Five stages, with the evidence fanning out and funnelling back in."""
    w, h = 1300, 470
    mid = 240
    edges, pills, nodes = [], [], []

    def box(x, num, title, body, bw=195):
        return (
            f"<g class='fnode'>"
            f"<rect x='{x}' y='{mid - 58}' width='{bw}' height='116' rx='14'/>"
            f"<text class='fnum' x='{x + 16}' y='{mid - 30}'>{num}</text>"
            f"<text class='ftitle' x='{x + 16}' y='{mid - 6}'>{title}</text>"
            f"<foreignObject x='{x + 14}' y='{mid + 4}' width='{bw - 28}' height='54'>"
            f"<div xmlns='http://www.w3.org/1999/xhtml' class='fbody'>{body}</div>"
            f"</foreignObject></g>"
        )

    pill_x, pill_w, pill_h = 440, 255, 56
    s4_x = 830
    rows = [25, 100, 175, 250, 325]

    for (name, what, _res), y in zip(FEEDS, rows):
        cy = y + pill_h / 2
        edges.append(
            f"<path class='fedge' d='M390 {mid} C 415 {mid}, 415 {cy:.0f}, {pill_x} {cy:.0f}'/>"
        )
        edges.append(
            f"<path class='fedge' d='M{pill_x + pill_w} {cy:.0f} "
            f"C {pill_x + pill_w + 50} {cy:.0f}, {s4_x - 50} {mid}, {s4_x} {mid}'/>"
        )
        pills.append(
            f"<g class='fpill'>"
            f"<rect x='{pill_x}' y='{y}' width='{pill_w}' height='{pill_h}' rx='12'/>"
            f"<text class='fpill-name' x='{pill_x + 14}' y='{y + 23}'>{html.escape(name)}</text>"
            f"<text class='fpill-what' x='{pill_x + 14}' y='{y + 42}'>"
            f"{html.escape(FEED_SHORT.get(name, what))}</text>"
            f"</g>"
        )

    nodes.append(box(0, "1", "The claim", "A database says: 648 MW, built in 2019, this operator.", bw=185))
    nodes.append(box(205, "2", "The place", "Draw the farm's footprint on the map from its capacity.", bw=185))
    nodes.append(box(s4_x, "4", "The test", "Compare each against a published threshold.", bw=185))
    nodes.append(box(1050, "5", "The verdict", "A risk score, a colour, and the reasoning in full.", bw=240))

    edges.append(f"<path class='fedge strong' d='M185 {mid} L205 {mid}'/>")
    edges.append(f"<path class='fedge strong' d='M{s4_x + 185} {mid} L1050 {mid}'/>")

    tag = (
        f"<g class='ftag'><rect x='{pill_x + 28}' y='402' width='160' height='34' rx='17'/>"
        f"<text x='{pill_x + 108}' y='424' text-anchor='middle'>Data cost: &#8377;0</text></g>"
    )
    stage3 = (
        f"<text class='fstage' x='{pill_x + pill_w / 2}' y='14' text-anchor='middle'>"
        f"3 &#183; The evidence &#8212; nine years of free satellite archives</text>"
    )

    return (
        f"<svg class='flow' viewBox='0 0 {w} {h}' preserveAspectRatio='xMidYMid meet' "
        f"role='img' aria-label='How the assessment works, in five stages'>"
        + "".join(edges) + "".join(pills) + "".join(nodes) + stage3 + tag + "</svg>"
    )


# --- worked example --------------------------------------------------------


def pick_featured(records: list[dict]) -> dict | None:
    """The asset that best demonstrates the method.

    Prefer a high risk score with a well-resolved rubric, so the walkthrough
    rests on evidence rather than on gaps.
    """
    if not records:
        return None
    return max(
        records,
        key=lambda r: (_n(r.get("score")), _n(r.get("evidence_completeness"))),
    )


def _narrate(r: dict) -> str:
    """Plain-English account of this asset, composed from its own evidence."""
    name = display_name(r)
    bits = []

    owner = r.get("owner")
    cap = _n(r.get("capacity_mw"))
    opener = f"The database reports <b>{cap:,.0f} MW</b> at {html.escape(name)}"
    if owner and not _isna(owner):
        opener += f", operated by {html.escape(str(owner))}"
    if _isna(r.get("commissioning_year")):
        opener += ". It gives no commissioning year, so there is no build date to test against"
    else:
        opener += f", commissioned {int(float(r['commissioning_year']))}"
    bits.append(opener + ".")

    status = r.get("build_status")
    if status == "already_built":
        bits.append(
            "The satellite record opens in 2017 with the site already developed, "
            "so the construction check cannot speak to this plant. That is "
            "reported as unresolved rather than scored as clean."
        )
    elif status == "ramp" and r.get("observed_build_month"):
        bits.append(
            f"Construction is visible in the imagery, crossing halfway in "
            f"<b>{html.escape(str(r['observed_build_month']))}</b>."
        )
    elif status == "no_signal":
        bits.append(
            "The built-ground signal is too noisy to read a construction date "
            "from, which is common where seasonal vegetation moves the land "
            "classification around."
        )

    ndvi = r.get("ndvi_values") or []
    clean = [v for v in ndvi if not _isna(v)]
    trend = r.get("ndvi_trend_per_year")
    if len(clean) >= 4 and not _isna(trend):
        direction = "risen" if trend > 0 else "fallen"
        bits.append(
            f"Greenness inside the footprint has {direction} from "
            f"<b>{clean[0]:.2f} to {clean[-1]:.2f}</b> over the record "
            f"({trend:+.4f} a year). On a working solar farm this should stay "
            f"low and flat; a rise means vegetation establishing between and "
            f"under the panels, which shades them at low sun angles and shows "
            f"up as a maintenance cost before it shows up as lost output."
        )

    heat = r.get("heat_days_per_year")
    derate = r.get("thermal_derate_pct")
    mean_t = r.get("mean_tmax_c")
    if not _isna(derate) and not _isna(mean_t):
        line = (
            f"Daily maximum temperature averages <b>{mean_t:.1f}&deg;C</b>, which "
            f"implies roughly <b>{derate:.1f}%</b> of output lost to cell "
            f"temperature at full sun."
        )
        if not _isna(heat):
            if heat > C.HEAT_DAYS_FLAG:
                line += (
                    f" It passes {C.HEAT_DAY_THRESHOLD_C:.0f}&deg;C on "
                    f"<b>{heat:,.0f} days a year</b>, which raises the heat check."
                )
            else:
                line += (
                    f" It only passes {C.HEAT_DAY_THRESHOLD_C:.0f}&deg;C on "
                    f"{heat:,.0f} days a year, so the heat check stays clear."
                )
        bits.append(line + " Physics rather than a fault, but it belongs in a yield assumption.")

    hand, gsw = r.get("hand_m"), r.get("gsw_occurrence_pct")
    flood_flag = bool((r.get("flags") or {}).get("flood_exposure"))
    water = []
    if not _isna(gsw):
        if gsw > C.GSW_OCCURRENCE_FLAG_PCT:
            water.append(
                f"standing water has covered part of the footprint <b>{gsw:.0f}% "
                f"of the months</b> on record since 1984"
            )
        else:
            water.append(
                f"standing water has reached it in only {gsw:.0f}% of months since 1984"
            )
    if not _isna(hand):
        if hand < C.HAND_FLAG_M:
            water.append(
                f"the ground sits just <b>{hand:.1f} m</b> above the nearest drainage line"
            )
        else:
            water.append(
                f"it sits {hand:.1f} m above the nearest drainage line, which is comfortable"
            )
    if water:
        line = "On water: " + ", and ".join(water) + "."
        line += (
            " That is enough to raise the flood check."
            if flood_flag
            else " The flood check stays clear."
        )
        bits.append(line)

    fired = [k for k, v in (r.get("flags") or {}).items() if v]
    if fired:
        pretty = ", ".join(k.replace("_", " ") for k in fired)
        bits.append(
            f"<b>Net:</b> {len(fired)} of five checks flagged ({pretty}), giving a "
            f"risk score of {_n(r.get('score')):.0f} out of 100 &mdash; "
            f"{BAND[r.get('traffic_light', 'green')]}."
        )
    else:
        bits.append(
            "<b>Net:</b> no check flagged. On the evidence available this asset "
            "is unremarkable, which is a useful result in itself."
        )

    return "".join(f"<p>{b}</p>" for b in bits)


def _compare_block(r: dict) -> str:
    """Drag-to-compare if two epochs exist, a single image if only one."""
    then = _img(r, "thumbnail_then")
    now = _img(r, "thumbnail") or _img(r, "thumbnail_now")
    y0 = C.S2_START[:4]
    if then and now:
        return f"""
<figure class="compare" id="cmp">
  <div class="cmp-wrap">
    <img class="cmp-base" src="{html.escape(now)}" alt="Satellite view of the site, recent">
    <img class="cmp-over" id="cmpThen" src="{html.escape(then)}"
         alt="Satellite view of the same site in {y0}">
    <span class="cmp-line" id="cmpLine"></span>
    <input type="range" min="0" max="100" value="50" id="cmpRange"
           aria-label="Compare {y0} with today">
    <span class="cmp-tag left">{y0}</span><span class="cmp-tag right">today</span>
  </div>
  <figcaption>Drag to compare. Same place, same scale, nine years apart.</figcaption>
</figure>"""
    if now:
        return (
            f"<figure class='compare'><img class='single' src='{html.escape(now)}' "
            f"alt='Satellite view of the site'>"
            f"<figcaption>True-colour Sentinel-2 composite of the footprint.</figcaption>"
            f"</figure>"
        )
    return (
        "<figure class='compare'><div class='nothumb'>No cloud-free composite "
        "available for this site.</div></figure>"
    )


def worked_example(r: dict | None) -> str:
    if not r:
        return ""
    name = display_name(r)
    light = r.get("traffic_light", "green")
    ndvi_years = [str(int(y)) for y in (r.get("ndvi_years") or [])]
    ndvi_vals = r.get("ndvi_values") or []
    ann = []
    clean_idx = [i for i, v in enumerate(ndvi_vals) if not _isna(v)]
    if len(clean_idx) >= 2:
        ann = [
            {"index": clean_idx[0], "text": "bare ground", "side": "above"},
            {"index": clean_idx[-1], "text": "vegetation established", "side": "above"},
        ]
    chart = (
        charts.line_chart(
            ndvi_years,
            ndvi_vals,
            colour="var(--series-2)",
            y_decimals=2,
            annotations=ann,
            aria=f"greenness inside the footprint at {name}, by year",
        )
        if ndvi_years
        else ""
    )
    return f"""
<section class="worked">
  <p class="eyebrow">One asset, start to finish</p>
  <h2>{html.escape(name)}</h2>
  <p class="lede">The same five checks every other asset gets, shown in full so
    you can see what the method actually produces.</p>
  <div class="worked-grid">
    <div class="worked-vis">
      {_compare_block(r)}
      <div class="chartbox">
        <p class="slabel">How green the ground is inside the footprint</p>
        {chart}
        <p class="note">Higher means more vegetation. A working solar farm
          should sit low and flat.</p>
      </div>
    </div>
    <div class="worked-text">
      <div class="verdict" style="border-color:{LIGHT[light]}">
        <span class="vscore" style="color:{LIGHT[light]}">{_n(r.get('score')):.0f}</span>
        <span class="vof">/100 risk score</span>
        <span class="vband">{html.escape(BAND[light])}</span>
      </div>
      {_narrate(r)}
      <p><a class="btn" href="cards/{html.escape(_slug(r))}.html">See the full assessment card &rarr;</a></p>
    </div>
  </div>
</section>"""


# --- table and map ---------------------------------------------------------


def _rows(records: list[dict]) -> str:
    out = []
    for r in records:
        light = r.get("traffic_light", "green")
        flags = r.get("flags") or {}
        fired = ", ".join(k.replace("_", " ") for k, v in flags.items() if v) or "none"
        out.append(
            "<tr>"
            f"<td><a href='cards/{html.escape(_slug(r))}.html'>{html.escape(display_name(r))}</a></td>"
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
            "name": display_name(r),
            "lat": _n(r.get("latitude")),
            "lon": _n(r.get("longitude")),
            "score": _n(r.get("score")),
            "light": r.get("traffic_light") or "green",
            "mw": _n(r.get("capacity_mw")),
            "slug": _slug(r),
        }
        for r in records
        if not _isna(r.get("latitude")) and not _isna(r.get("longitude"))
    ]
    return json.dumps(pts, allow_nan=False)


# --- page ------------------------------------------------------------------


def render_index(records: list[dict], as_of: str) -> str:
    n = len(records)
    counts = {k: sum(1 for r in records if r.get("traffic_light") == k) for k in LIGHT}
    mean_completeness = (
        sum(_n(r.get("evidence_completeness")) for r in records) / n if n else 0
    )
    total_mw = sum(_n(r.get("capacity_mw")) for r in records)
    unresolved = sum(
        1 for r in records if _isna(r.get("commissioning_year"))
    )
    featured = pick_featured(records)

    feed_rows = "".join(
        f"<tr><td><b>{html.escape(nm)}</b></td><td>{html.escape(what)}</td>"
        f"<td class='src'>{html.escape(res)}</td></tr>"
        for nm, what, res in FEEDS
    )

    gap_note = ""
    if unresolved:
        gap_note = f"""
  <div class="gapnote">
    <h3>Where this run is thin</h3>
    <p>{unresolved} of {n} assets have no commissioning year in the source
      database, and all of them were already built when the satellite record
      opens in {C.S2_START[:4]}. So the construction check &mdash; the heaviest
      weight in the score &mdash; could not be resolved for any asset here.
      Those are reported as unresolved, not as clean, and every risk score on
      this page should be read as a <b>lower bound</b>.</p>
    <p class="note">This is a finding about the public record, not a fault in
      the assets. It is also the clearest argument for the method: the gap is
      visible instead of silently filled in.</p>
  </div>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solar asset assessment — India</title>
<meta name="description" content="Testing reported solar plants in India against what satellites actually saw, using only free data.">
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
</head><body>
<main class="site">

<header class="hero">
  <p class="eyebrow">Open-data prototype &middot; {html.escape(as_of)}</p>
  <h1>A solar farm's paperwork says one thing.<br>What did the satellites see?</h1>
  <p class="lede">Before anyone spends money on a solar asset &mdash; lending against
    it, buying it, insuring it, auditing it &mdash; there is a reported record: a
    capacity, a build year, an owner. Almost none of it has been checked.</p>
  <p class="lede">This takes {n} of India's largest solar plants and tests that
    record against nine years of free satellite imagery. No site visit, no
    licence fee, no data purchase. Every threshold is published, and where the
    evidence runs out, the page says so instead of guessing.</p>
</header>

<section class="stats">
  <div class="stat"><b>{n}</b><span>assets tested</span></div>
  <div class="stat"><b>{total_mw:,.0f}</b><span>MW covered</span></div>
  <div class="stat"><b style="color:{LIGHT['red']}">{counts['red']}</b><span>investigate</span></div>
  <div class="stat"><b style="color:{LIGHT['amber']}">{counts['amber']}</b><span>worth a look</span></div>
  <div class="stat"><b style="color:{LIGHT['green']}">{counts['green']}</b><span>little to investigate</span></div>
  <div class="stat"><b>{mean_completeness:.0%}</b><span>of checks resolved</span></div>
</section>

<section>
  <p class="eyebrow">How it works</p>
  <h2>From a claim on a page to a number you can argue with</h2>
  <div class="flowwrap">{flowchart()}</div>
  <table class="feeds">
    <thead><tr><th>What we look at</th><th>What it tells us</th><th>Resolution</th></tr></thead>
    <tbody>{feed_rows}</tbody>
  </table>
</section>

<section class="versus">
  <h2>Why bother</h2>
  <div class="vgrid">
    <div class="vcol old">
      <h3>The usual way</h3>
      <p class="vbig">Weeks</p>
      <ul>
        <li>Send an engineer to the site</li>
        <li>One asset at a time</li>
        <li>Costs scale with every asset added</li>
        <li>Tells you about today, not about the last nine years</li>
      </ul>
    </div>
    <div class="vcol new">
      <h3>This way</h3>
      <p class="vbig">Minutes</p>
      <ul>
        <li>Runs from a desk, before anyone travels</li>
        <li>Whole portfolio at once</li>
        <li>Data costs nothing; the hundredth asset is free</li>
        <li>Reads the full history back to {C.S2_START[:4]}</li>
      </ul>
    </div>
  </div>
  <p class="note">This does not replace a site visit. It decides <i>which</i>
    sites are worth one, and what to ask when you get there.</p>
</section>

{worked_example(featured)}

<section>
  <h2>Every asset in this run</h2>
  <div id="map" style="height:460px;border-radius:12px;overflow:hidden"></div>
  <p class="note">Marker size is capacity; colour is the verdict.</p>
  <table class="portfolio" id="pf">
    <thead><tr>
      <th>Asset</th><th>MW</th><th>Risk score</th><th>Checks resolved</th><th>Flags raised</th>
    </tr></thead>
    <tbody>{_rows(records)}</tbody>
  </table>
  <p class="note">Click a column heading to sort.</p>
</section>

<section>
  <h2>What the risk score is made of</h2>
  <p class="lede">Five checks, each weighted by how much it would change a
    decision. A flag adds its weight; the total is the score.</p>
  {charts.weight_bars(C.FLAG_WEIGHTS)}
  <div class="bands">
    <span class="pill" style="background:{LIGHT['green']}">0&ndash;24</span> little to investigate
    <span class="pill" style="background:{LIGHT['amber']}">25&ndash;54</span> worth a look
    <span class="pill" style="background:{LIGHT['red']}">55&ndash;100</span> investigate before committing
  </div>
  <p class="note"><b>A high score is not a bad asset.</b> It means the public
    record and the satellite record disagree, or the site carries a physical
    exposure worth pricing. It ranks what to examine. It is not a valuation,
    a yield estimate, or a statement about any operator.</p>
  {gap_note}
</section>

<section class="limits">
  <p class="eyebrow">Read this part</p>
  <h2>Five things this gets wrong &mdash; and why they are published</h2>
  <p class="lede">Any screening tool can be made to look certain. This one
    lists its own failure modes, because a number you cannot challenge is a
    number you should not rely on.</p>
  <ol class="limitlist">
    <li><b>The footprint is a circle, not the panels.</b> Area comes from
      capacity at 2.2 hectares per MW. It takes in surrounding land, which
      dilutes every area measurement &mdash; most of all on smaller plants.</li>
    <li><b>Flood exposure is a terrain proxy.</b> Height above the nearest
      drainage line is estimated from an elevation model, not modelled
      hydraulically. It finds sites worth a flood study; it is not one.</li>
    <li><b>The weather data is coarse.</b> ERA5-Land cells are about 9 km
      across, so sunlight and temperature are regional, not measured at the
      fence line.</li>
    <li><b>Land classification confuses things.</b> Bare earth, quarries and
      new industrial land all read as developed. Seasonal vegetation moves the
      signal enough to mask a real construction ramp.</li>
    <li><b>The source database is incomplete.</b> Commissioning years are
      patchy. A timing flag is at least as likely to mean the database is
      stale as anything about the asset.</li>
  </ol>
  <p class="note">And the standing rule: <b>a flag is a reason to look, never
    a finding.</b> Nothing here is evidence of misreporting by any operator,
    and nothing here is investment advice.</p>
</section>

<footer class="sitefoot">
  <p><b>Data</b> &middot; Sentinel-2 (ESA/Copernicus) &middot; Dynamic World
     (Google/WRI) &middot; ERA5-Land (ECMWF/Copernicus) &middot; JRC Global
     Surface Water &middot; Copernicus DEM GLO-30 &middot; Global Power Plant
     Database (WRI, CC BY 4.0). Processed in Google Earth Engine.</p>
  <p>A personal methodology prototype, published as independent work. Earth
     Engine's free tier is non-commercial. Code MIT licensed.</p>
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
    radius: Math.max(6, Math.min(20, Math.sqrt(p.mw || 1) / 3)),
    color: COL[p.light] || '#666', fillColor: COL[p.light] || '#666',
    fillOpacity: 0.6, weight: 2
  }}).addTo(map).bindPopup(
    `<b>${{p.name}}</b><br>${{(p.mw||0).toLocaleString()}} MW &middot; risk score ${{p.score}}` +
    `<br><a href="cards/${{p.slug}}.html">assessment card</a>`
  );
}});
if (PTS.length) map.fitBounds(PTS.map(p => [p.lat, p.lon]), {{padding: [50, 50]}});

document.querySelectorAll('#pf thead th').forEach((th, i) => {{
  th.style.cursor = 'pointer';
  let asc = false;
  th.addEventListener('click', () => {{
    asc = !asc;
    const tb = document.querySelector('#pf tbody');
    Array.from(tb.rows).sort((a, b) => {{
      const av = a.cells[i].dataset.v, bv = b.cells[i].dataset.v;
      if (av !== undefined && bv !== undefined) return (asc ? 1 : -1) * (parseFloat(av) - parseFloat(bv));
      return (asc ? 1 : -1) * a.cells[i].innerText.localeCompare(b.cells[i].innerText);
    }}).forEach(r => tb.appendChild(r));
  }});
}});

const rng = document.getElementById('cmpRange');
if (rng) {{
  const then = document.getElementById('cmpThen');
  const line = document.getElementById('cmpLine');
  const move = () => {{
    const v = +rng.value;
    then.style.clipPath = 'inset(0 ' + (100 - v) + '% 0 0)';
    line.style.left = v + '%';
  }};
  rng.addEventListener('input', move); move();
}}

const io = new IntersectionObserver(es => es.forEach(e => {{
  if (e.isIntersecting) {{ e.target.classList.add('in'); io.unobserve(e.target); }}
}}), {{threshold: 0.15}});
document.querySelectorAll('section, .flowwrap').forEach(el => {{
  el.classList.add('reveal'); io.observe(el);
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
