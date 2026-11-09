# Solar asset assessment

Independent, satellite-based corroboration of reported utility-scale solar
plants in India, built entirely from free and open data in Google Earth Engine.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR-GITHUB-USERNAME/solar-asset-assessment/blob/main/notebooks/solar_asset_assessment.ipynb)

**[→ Published portfolio view](https://YOUR-GITHUB-USERNAME.github.io/solar-asset-assessment/)**

---

## The question

Before anyone does site diligence on an operating solar asset, there is a
reported record: a name, a capacity, a commissioning year, an owner. The
question this answers is narrow and practical:

> How much of that reported record can be independently corroborated from
> free satellite data, fast enough to be worth doing *before* the site visit?

The answer is: partly. This repository is explicit about which part, and the
cards say so on their face rather than in a footnote.

## What it does

For every solar plant in India above 50 MW in the
[WRI Global Power Plant Database](https://datasets.wri.org/dataset/globalpowerplantdatabase),
it runs five checks against a capacity-scaled footprint and produces one
assessment card:

| Check | Evidence | Fires when |
|---|---|---|
| **Build timing** | Dynamic World built + bare share of footprint, monthly since 2017 | observed build more than 12 months after the reported commissioning year ends |
| **Resource shortfall** | ERA5-Land annual GHI vs. the 1991–2020 mean at that pixel | mean annual anomaly below −3% |
| **Thermal derating** | ERA5-Land daily maximum temperature; NOCT cell-temperature model | more than 60 days a year above 40 °C |
| **Vegetation** | Sentinel-2 annual median NDVI inside the footprint, OLS slope | trend above +0.010 per year |
| **Flood exposure** | JRC Global Surface Water occurrence; Copernicus DEM height above nearest drainage | occurrence above 10% or HAND under 5 m |

Flags are weighted (30 / 20 / 15 / 15 / 20) into a 0–100 score and a traffic
light. Higher means *more to investigate*, not *worth less*.

## What makes it arguable rather than opaque

Three deliberate choices, because a screening tool nobody can challenge is a
screening tool nobody should trust.

1. **Every number a reviewer might dispute lives in [`src/config.py`](src/config.py)**
   — land use per MW, every threshold, every weight — with the reasoning
   inline. Disagree with the 40 °C heat-day threshold and you change one line.
2. **The judgement is separated from the data.** [`src/metrics.py`](src/metrics.py)
   has no Earth Engine and no network in it, so the whole rubric is unit
   tested in 0.04 seconds. [`src/gee.py`](src/gee.py) only fetches evidence.
3. **Missing evidence never raises a flag, and never hides either.** If a
   query fails or a site has no cloud-free imagery, the check scores as clear
   and the card reports the resulting *evidence completeness* — so a 45/100
   built on four of six checks is not presented as the same finding as a
   45/100 built on six.

```
src/config.py    every threshold, weight and dataset id
src/metrics.py   pure scoring logic — no EE, no network, fully tested
src/gee.py       Earth Engine queries, one getInfo per asset per metric
src/assess.py    orchestration; per-asset failures are caught, not fatal
src/card.py      one self-contained HTML card per asset
src/site.py      portfolio index with map and sortable table
tests/           36 tests, no credentials required
```

## Running it

**In Colab** (easiest — click the badge above). You need a Google account with
Earth Engine access registered to a Google Cloud project. Set `EE_PROJECT` in
the first cell and run top to bottom. Roughly 20–40 minutes for 25 assets.

**Locally:**

```bash
pip install -r requirements.txt
earthengine authenticate
python -m pytest -q                     # verify the rubric, no credentials needed
python -c "
from src import assess, card, site
import datetime as dt
a = assess.load_assets(limit=25)
r = assess.assess_portfolio(a)
assess.save_results(r); card.write_cards(r)
site.write_site(r, dt.date.today().isoformat())
"
```

Outputs land in `outputs/` (results.json, results.csv) and `docs/`
(index.html, cards/). Commit `docs/` and enable GitHub Pages on the `docs/`
folder of the `main` branch to publish.

## Limitations

Stated plainly, because they bound what the output is worth:

- **The footprint is a circle, not the panel array.** Area is derived from
  capacity at 2.2 ha/MW. It over-includes surrounding land, which dilutes
  every area statistic — most visibly the built-fraction series on small
  plants. Panel segmentation would need labelled training data this does not
  have, and a classifier that silently guesses is worse than a circle that
  admits what it is.
- **HAND is approximated** as mean site elevation minus the minimum elevation
  within 2 km. That is a screening proxy, not a hydraulic flood model.
- **ERA5-Land is ~9 km.** Over that cell the GHI and temperature are a
  regional signal, not a site measurement.
- **Dynamic World mislabels.** Bare ground, quarries and new industrial land
  all read as built or bare. The build-timing check works on the *shape* of
  the time series, which is more robust than any single month, but it is
  still a proxy.
- **WRI is incomplete and partly stale.** Commissioning years in particular
  are known to be uneven. A build-timing flag is at least as likely to mean
  the database is out of date as anything about the asset.
- **A flag is a reason to look.** Nothing here is evidence of misreporting by
  any operator, and nothing here is investment advice.

## Licensing and data

Code is MIT licensed. The data is not mine:

- Sentinel-2 — ESA / Copernicus
- Dynamic World V1 — Google / World Resources Institute
- ERA5-Land — ECMWF / Copernicus Climate Change Service
- JRC Global Surface Water — European Commission Joint Research Centre
- Copernicus DEM GLO-30 — ESA / Airbus
- Global Power Plant Database — World Resources Institute (CC BY 4.0)

Processed in [Google Earth Engine](https://earthengine.google.com/). **Earth
Engine's free tier is for non-commercial use.** This is a personal
methodology prototype, published as independent work; commercial use would
need a commercial Earth Engine licence.
