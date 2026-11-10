"""Make the published page's imagery durable.

Earth Engine `getThumbURL` links are signed and temporary. A page that
hotlinks them looks fine the day it is built and shows broken images a week
later. These helpers download the PNGs into docs/assets/img/ so the committed
site stands on its own, and add a second, earlier epoch for the before/after
comparison on the featured asset.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from . import config as C


def _download(url: str, dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = resp.read()
        if len(data) < 1000:  # an error page, not an image
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"    could not fetch {dest.name}: {exc}")
        return False


def localise_thumbnails(records: list[dict], docs_dir: str = "docs") -> int:
    """Download each asset's thumbnail and point the record at the local copy."""
    img_dir = Path(docs_dir) / "assets" / "img"
    saved = 0
    for r in records:
        url = r.get("thumbnail_url")
        if not url:
            continue
        slug = str(r.get("id") or r.get("name")).replace("/", "-")
        dest = img_dir / f"{slug}.png"
        if _download(url, dest):
            # paths are relative to docs/index.html and docs/cards/*.html
            r["thumbnail_local"] = f"assets/img/{dest.name}"
            saved += 1
    return saved


def add_before_after(record: dict, docs_dir: str = "docs", then_year: int | None = None) -> bool:
    """Generate and save an early-epoch thumbnail for the comparison slider.

    Needs Earth Engine initialised. Only worth running on the featured asset.
    """
    from . import gee, metrics as M

    then_year = then_year or int(C.S2_START[:4])
    radius = M.buffer_radius_m(record.get("capacity_mw") or 0.0)
    geom = gee.asset_geometry(record["latitude"], record["longitude"], radius)

    url = gee.rgb_thumbnail_url(geom, then_year)
    if not url:
        print(f"    no cloud-free composite for {then_year}")
        return False

    slug = str(record.get("id") or record.get("name")).replace("/", "-")
    dest = Path(docs_dir) / "assets" / "img" / f"{slug}-{then_year}.png"
    if not _download(url, dest):
        return False
    record["thumbnail_then_url"] = url
    record["thumbnail_then_local"] = f"assets/img/{dest.name}"
    return True


def prepare(records: list[dict], docs_dir: str = "docs") -> dict:
    """Localise every thumbnail, then add a before/after pair for the featured asset."""
    from .site import pick_featured

    saved = localise_thumbnails(records, docs_dir)
    featured = pick_featured(records)
    ba = add_before_after(featured, docs_dir) if featured else False
    return {
        "thumbnails_saved": saved,
        "featured": (featured or {}).get("name"),
        "before_after": ba,
    }
