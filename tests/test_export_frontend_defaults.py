"""Exporter publishing defaults (scripts/export_frontend_simulated.py).

The exporter is script-style (argparse runs at import), so these pins read the
source: 200 most-consequential renders, HTML-only by default (no per-scenario
PNGs; the og:image preview raster survives), with --with-pngs as the opt-back.
Owner decision 2026-07-21.
"""

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1]
        / "scripts" / "export_frontend_simulated.py").read_text(encoding="utf-8")


def _arg_block(flag):
    m = re.search(re.escape(f'"{flag}"') + r"(.*?)parser\.add_argument", _SRC, re.S)
    assert m, f"missing {flag}"
    return m.group(1)


def test_render_cap_defaults_to_200():
    assert re.search(r'"--max-renders",\s*type=int,\s*default=200', _SRC)


def test_pngs_off_by_default_with_optback():
    assert re.search(r'"--no-pngs",\s*action="store_true",\s*default=True', _SRC)
    assert re.search(r'"--with-pngs",\s*action="store_false",\s*dest="no_pngs"', _SRC)


def test_og_preview_raster_still_special_cased():
    # one raster must survive --no-pngs: the link-unfurl og:image
    assert 'modes/simulated/preview.png' in _SRC
