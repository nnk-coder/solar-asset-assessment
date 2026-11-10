"""Rendering smoke tests. No network, no Earth Engine.

These build the card and the index from synthetic records so the HTML layer
can be verified without a Colab run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import card as CARD  # noqa: E402
from src import site as SITE  # noqa: E402


def _record(**over):
    r = {
        "id": "IND0000001",
        "name": "Example Solar Park",
        "capacity_mw": 250.0,
        "latitude": 23.1,
        "longitude": 74.2,
        "commissioning_year": 2019,
        "owner": "Example Energy Ltd",
        "source_url": "https://example.org/plant",
        "footprint_radius_m": 1323,
        "as_of": "2026-11-09",
        "build_status": "ramp",
        "observed_build_month": "2021-04",
        "build_delay_m": 15.5,
        "mean_resource_anomaly_pct": -1.2,
        "baseline_ghi_kwh_m2": 1980.0,
        "heat_days_per_year": 72.0,
        "mean_tmax_c": 34.5,
        "thermal_derate_pct": 9.1,
        "ndvi_trend_per_year": 0.004,
        "gsw_occurrence_pct": 2.0,
        "hand_m": 18.0,
        "elevation_m": 410.0,
        "dev_fraction": [0.02, 0.05, 0.3, 0.6, 0.78, 0.8, 0.81, 0.8],
        "dev_months": ["2019-01", "2019-06", "2020-01", "2021-01",
                       "2021-06", "2022-01", "2023-01", "2024-01"],
        "ndvi_values": [0.21, 0.22, 0.23, 0.24, 0.25],
        "ndvi_years": [2019.0, 2020.0, 2021.0, 2022.0, 2023.0],
        "thumbnail_url": None,
        "flags": {
            "build_delay": True,
            "resource_shortfall": False,
            "thermal_derating": True,
            "vegetation_encroachment": False,
            "flood_exposure": False,
        },
        "score": 45.0,
        "traffic_light": "amber",
        "evidence_completeness": 1.0,
        "errors": [],
    }
    r.update(over)
    return r


def test_card_renders_and_names_the_asset():
    out = CARD.render_card(_record())
    assert out.startswith("<!doctype html>")
    assert "Example Solar Park" in out
    assert "45" in out
    assert "worth a look" in out
    assert "risk score" in out


def test_card_marks_unresolved_evidence_rather_than_zero():
    out = CARD.render_card(
        _record(hand_m=None, gsw_occurrence_pct=None, evidence_completeness=0.67)
    )
    assert "not resolved" in out
    assert "2 of six checks could not be resolved" in out
    assert "lower bound" in out


def test_card_escapes_hostile_names():
    out = CARD.render_card(_record(name="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_card_handles_missing_series():
    out = CARD.render_card(_record(dev_fraction=[], ndvi_values=None))
    assert "Not enough observations to plot" in out


def test_card_surfaces_query_errors():
    out = CARD.render_card(_record(errors=["climate: timeout"]))
    assert "Query errors (1)" in out
    assert "climate: timeout" in out


def test_index_renders_every_asset():
    recs = [
        _record(),
        _record(id="IND0000002", name="Second Park", traffic_light="red", score=70.0),
        _record(id="IND0000003", name="Third Park", traffic_light="green", score=0.0),
    ]
    out = SITE.render_index(recs, "2026-11-09")
    assert "Second Park" in out and "Third Park" in out
    assert "cards/IND0000002.html" in out
    assert "<b>3</b><span>assets tested</span>" in out


def test_index_counts_traffic_lights():
    recs = [
        _record(traffic_light="red"),
        _record(id="b", traffic_light="red"),
        _record(id="c", traffic_light="green"),
    ]
    out = SITE.render_index(recs, "2026-11-09")
    assert ">2</b><span>investigate</span>" in out
    assert ">1</b><span>little to investigate</span>" in out


def test_index_embeds_valid_marker_json():
    import json
    import re

    recs = [_record()]
    out = SITE.render_index(recs, "2026-11-09")
    m = re.search(r"const PTS = (\[.*?\]);", out, re.S)
    assert m
    pts = json.loads(m.group(1))
    assert pts[0]["name"] == "Example Solar Park"
    assert pts[0]["lat"] == 23.1


def test_index_survives_empty_portfolio():
    out = SITE.render_index([], "2026-11-09")
    assert "<b>0</b><span>assets tested</span>" in out


def test_card_survives_nan_commissioning_year():
    """pandas hands back NaN, and NaN is truthy. Regression: int(nan) raised."""
    out = CARD.render_card(_record(commissioning_year=float("nan")))
    assert "not resolved" in out
    assert re.search(r"\bnan\b", out, re.I) is None


def test_card_survives_nan_everywhere():  # noqa: D103
    nan = float("nan")
    out = CARD.render_card(
        _record(
            commissioning_year=nan,
            capacity_mw=nan,
            build_delay_m=nan,
            mean_resource_anomaly_pct=nan,
            baseline_ghi_kwh_m2=nan,
            heat_days_per_year=nan,
            thermal_derate_pct=nan,
            ndvi_trend_per_year=nan,
            gsw_occurrence_pct=nan,
            hand_m=nan,
            dev_fraction=[0.1, nan, 0.4],
            ndvi_values=[nan, nan],
        )
    )
    assert re.search(r"\bnan\b", out, re.I) is None


def test_index_survives_nan_values():
    import json
    import re

    nan = float("nan")
    recs = [_record(capacity_mw=nan, score=nan, evidence_completeness=nan)]
    out = SITE.render_index(recs, "2026-11-09")
    # "nan" as a standalone token, not the "nan" inside "maintenance"
    assert re.search(r"\bnan\b", out, re.I) is None
    pts = json.loads(re.search(r"const PTS = (\[.*?\]);", out, re.S).group(1))
    assert pts[0]["mw"] == 0.0


def test_index_drops_assets_without_coordinates():
    recs = [_record(), _record(id="b", name="No Coords", latitude=float("nan"))]
    out = SITE.render_index(recs, "2026-11-09")
    import json
    import re

    pts = json.loads(re.search(r"const PTS = (\[.*?\]);", out, re.S).group(1))
    assert len(pts) == 1
    assert "No Coords" in out  # still listed in the table


def test_evidence_completeness_treats_nan_as_unresolved():
    from src import metrics as M

    assert M.evidence_completeness({"hand_m": float("nan")}) == 0.0


def test_write_cards_and_site(tmp_path):
    recs = [_record(), _record(id="IND0000002", name="Second Park")]
    paths = CARD.write_cards(recs, docs_dir=str(tmp_path))
    assert len(paths) == 2
    assert (tmp_path / "cards" / "IND0000001.html").exists()
    index = SITE.write_site(recs, "2026-11-09", docs_dir=str(tmp_path))
    assert Path(index).exists()
