"""Thresholds and constants for the solar asset assessment.

Every number a reviewer might argue with lives here, not buried in the analysis.
Sources and reasoning are given inline so the rubric can be challenged.
"""

from __future__ import annotations

# --- Asset selection -------------------------------------------------------

WRI_CSV_URL = (
    "https://raw.githubusercontent.com/wri/global-power-plant-database/"
    "master/output_database/global_power_plant_database.csv"
)

COUNTRY = "India"
PRIMARY_FUEL = "Solar"
MIN_CAPACITY_MW = 50.0  # utility scale only; below this the buffer method is noise

# --- Footprint -------------------------------------------------------------

# Indian utility-scale PV land use, including inter-row spacing, access roads
# and setbacks. Published Indian parks run roughly 2.0-2.5 ha per MW (DC).
# 2.2 ha/MW = 22,000 m^2/MW is a defensible mid-point.
LAND_USE_M2_PER_MW = 22_000.0

BUFFER_MIN_M = 400.0
BUFFER_MAX_M = 6_000.0

# --- Temporal windows ------------------------------------------------------

S2_START = "2017-01-01"  # Sentinel-2 SR has reliable global coverage from here
ERA5_BASELINE_START = "1991-01-01"
ERA5_BASELINE_END = "2020-12-31"

# --- Build detection -------------------------------------------------------

# Fraction of the final developed area that counts as "substantially built".
BUILD_COMPLETION_FRACTION = 0.50

# Months after the claimed commissioning year end before we flag a delay.
BUILD_DELAY_FLAG_MONTHS = 12

# Sentinel-2 SCL classes to mask: 3 cloud shadow, 8 cloud medium probability,
# 9 cloud high probability, 10 thin cirrus.
S2_SCL_MASK_CLASSES = (3, 8, 9, 10)
S2_MAX_CLOUD_PCT = 40

# Dynamic World class indices (GOOGLE/DYNAMICWORLD/V1 'label' band).
DW_BUILT = 6
DW_BARE = 7

# --- Resource --------------------------------------------------------------

# Annual GHI anomaly below this is flagged as a resource shortfall.
RESOURCE_ANOMALY_FLAG_PCT = -3.0

# --- Thermal derating ------------------------------------------------------

# Standard crystalline-silicon power temperature coefficient.
TEMP_COEFF_PCT_PER_C = -0.35
STC_CELL_TEMP_C = 25.0
NOCT_C = 45.0  # nominal operating cell temperature, typical module datasheet
NOCT_IRRADIANCE_W_M2 = 800.0

HEAT_DAY_THRESHOLD_C = 40.0
HEAT_DAYS_FLAG = 60  # days per year above threshold before we flag it

# --- Vegetation encroachment ----------------------------------------------

# NDVI inside a working solar farm should be low and flat. A rising trend is
# vegetation growth: shading at low sun angles, and a soiling / O&M signal.
NDVI_TREND_FLAG_PER_YEAR = 0.010

# --- Water and flood -------------------------------------------------------

# JRC Global Surface Water occurrence (% of months 1984-2021 with water).
GSW_OCCURRENCE_FLAG_PCT = 10.0

# Height above nearest drainage, approximated as elevation minus the minimum
# elevation within a neighbourhood of this radius.
HAND_NEIGHBOURHOOD_M = 2_000.0
HAND_FLAG_M = 5.0

# --- Scoring ---------------------------------------------------------------

# Weights sum to 100. A higher score means more to investigate, not a valuation.
FLAG_WEIGHTS = {
    "build_delay": 30.0,
    "resource_shortfall": 20.0,
    "thermal_derating": 15.0,
    "vegetation_encroachment": 15.0,
    "flood_exposure": 20.0,
}

TRAFFIC_LIGHT_BANDS = (
    (0.0, 25.0, "green"),
    (25.0, 55.0, "amber"),
    (55.0, 100.1, "red"),
)

# --- Earth Engine asset ids -----------------------------------------------

EE_S2 = "COPERNICUS/S2_SR_HARMONIZED"
EE_DW = "GOOGLE/DYNAMICWORLD/V1"
EE_ERA5_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"
EE_GSW = "JRC/GSW1_4/GlobalSurfaceWater"
EE_DEM = "COPERNICUS/DEM/GLO30"

# Reduction scale in metres. 20 m keeps Sentinel-2 detail while staying inside
# Earth Engine's interactive compute limits for a few dozen assets.
REDUCE_SCALE_M = 20
ERA5_SCALE_M = 11_132  # native ERA5-Land grid
