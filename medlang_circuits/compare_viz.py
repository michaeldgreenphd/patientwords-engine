"""Task 2: Tufte-styled comparison visualizations of tagged attribution graphs.

Shared rendering core (every layout inherits these):

- pure white background; no bounding boxes, grids, or panel fills
- no detached legend: category names are written inline next to each
  category's most prominent node, in that category's color
- structural/embedding/logit nodes and structural-to-structural edges are a
  muted light gray; saturated blue (clinical) and orange (off_target) are
  reserved for transcoder features
- node radius is proportional to normalized attribution mass (logits: the
  next-token probability), 3px floor to 14px cap
- edges are cubic bezier curves whose stroke width and opacity scale with
  |attribution weight|, trimmed at both ends to the node rims
- dynamic layer axis: only occupied layers get rows; empty runs compress to a
  small elision gap with a faint tick
- baseline typography: only the single compared content word per panel is
  emphasized in the panel accent color
- clinical-role panels print the normalized attribution mass beside clinical
  nodes at or above NODE_VALUE_THRESHOLD
- optional per-panel headline (e.g. the target-token probability) renders
  prominently at the panel's top right
- delta badges render centered in the gutters between panels

Three isolated layout engines sit on top:

    render_panels_html/png    - vertical stack (2panel mode, and the
                                translation chain, whose gap carries the LLM
                                translation interstitial as a multi-line badge)
    render_quadrant_html/png  - 2x2 syntax-vs-terminology matrix (4quadrant
                                mode) with vocabulary deltas in the column
                                gutters and syntax deltas in the row gutter

Outputs are standalone responsive HTML (minified inline CSS/JS, interactive
hover tooltips with feature id, category, probability/attribution mass, and
the cached autointerp description) plus matplotlib/networkx static PNGs.
"""

from __future__ import annotations

import difflib
import html
import json
import logging
import math
import re
from collections import defaultdict
from typing import Any

from medlang_circuits.schema_utils import max_numeric_layer, node_display_layer
from medlang_circuits.targets import bare_token, parse_logit_clerp

logger = logging.getLogger(__name__)

# Semantic palette: medical/clinical language is green, patient language is black,
# structural context recedes in light gray. Green/black CVD separation validated
# (deltaE 52.5 deutan) with contrast >= 3:1 on white.
CATEGORY_COLORS = {
    "clinical": "#15803d",
    "off_target": "#111827",
    "structural": "#c3c9d2",  # muted light gray - recedes behind feature nodes
}
CATEGORY_LABELS = {"clinical": "Clinical", "off_target": "Off-target", "structural": "Structural"}
POSITIVE_EDGE_COLOR = "#5b6b7f"
NEGATIVE_EDGE_COLOR = "#d1584d"
MUTED_EDGE_COLOR = "#dfe3e8"
INK = "#111827"
FAINT_INK = "#9aa3af"
TOKEN_INK = "#64748b"

DEFAULT_MAX_EDGES = 400
PANEL_WIDTH = 1180
ROW_HEIGHT = 34
ELIDED_GAP_ROWS = 1.45  # vertical space for a run of >=1 empty layers
MARGIN = {"left": 66, "right": 34, "top": 118, "bottom": 66}
PANEL_GAP = 18
BADGE_GAP = 64  # panel gap when a single-line badge renders in it
BADGE_LINE_HEIGHT = 34
DIMMED_NODE_OPACITY = 0.16  # shared-circuit context in pairwise diff views
STRUCTURAL_FILL_OPACITY = 0.55  # scaffolding recedes; clinical/off-target carry the ink

QUAD_GUTTER_X = 64
QUAD_GUTTER_Y = 100  # row gutter hosts syntax deltas and the lower vocabulary delta
QUAD_VOCAB_STRIP = 36  # header strip above the top row for the upper vocabulary delta

# Vertical rim-to-rim spacing between stacked logit nodes (the predictive
# spread). Labels sit beside each node, so the gap only needs to clear the
# 9.5px label line height.
LOGIT_STACK_GAP = 16

MIN_RADIUS = 3.0  # muted structural/embedding floor
MAX_RADIUS = 14.0  # cap (a probability-1.0 logit)
FEATURE_RADIUS_BASE = 4.0
FEATURE_RADIUS_SPAN = 6.0  # feature nodes span 4..10px by sqrt(mass fraction)
STRUCTURAL_RADIUS_SPAN = 2.0  # structural marks span 3..5px
JITTER = 9.0

# Clinical nodes at or above this normalized attribution mass get an on-chart
# value label (clinical-role panels only).
NODE_VALUE_THRESHOLD = 0.5

# Default per-panel roles for 2- and 3-panel stacks (index 1 = patient wording).
DEFAULT_PANEL_ROLES = ("Clinical wording", "Patient wording", "Translated wording")

_LOGIT_PROB_RE = re.compile(r"\(p=([0-9.]+)\)")


def _category(node: dict[str, Any]) -> str:
    return (node.get("medlang") or {}).get("category") or "structural"


def _logit_prob(node: dict[str, Any]) -> float | None:
    match = _LOGIT_PROB_RE.search(node.get("clerp") or "")
    if match:
        try:
            return min(float(match.group(1)), 1.0)
        except ValueError:
            return None
    return None


def _layer_label(layer: int, top_layer: int) -> str:
    if layer == -1:
        return "emb"
    if layer == top_layer + 1:
        return "logit"
    return f"L{layer}"


def _node_radius(node: dict[str, Any], mass_frac: float) -> float:
    """Radius proportional to normalized attribution mass (logits: next-token probability)."""
    if node.get("feature_type") == "logit":
        prob = _logit_prob(node)
        scale = prob if prob is not None else mass_frac
        return min(MAX_RADIUS, MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * scale)
    if _category(node) == "structural":
        return MIN_RADIUS + STRUCTURAL_RADIUS_SPAN * math.sqrt(mass_frac)
    return min(MAX_RADIUS, FEATURE_RADIUS_BASE + FEATURE_RADIUS_SPAN * math.sqrt(mass_frac))


def _altered_token_indices(tokens_a: list[str], tokens_b: list[str]) -> tuple[set[int], set[int]]:
    """Indices of tokens not shared between the two prompts (the linguistic intervention)."""
    matcher = difflib.SequenceMatcher(a=tokens_a, b=tokens_b, autojunk=False)
    keep_a: set[int] = set()
    keep_b: set[int] = set()
    for block in matcher.get_matching_blocks():
        keep_a.update(range(block.a, block.a + block.size))
        keep_b.update(range(block.b, block.b + block.size))
    return set(range(len(tokens_a))) - keep_a, set(range(len(tokens_b))) - keep_b


def _focus_token_index(tokens: list[str], altered: set[int], focus_token: str | None = None) -> set[int]:
    """Narrow the altered-token set to the single compared content word.

    In "I've got the blues" vs "I have depression" the whole phrase differs, but
    only blues/depression is the lexical substitution worth emphasizing - the
    surrounding function words stay muted. Heuristic: the altered token with the
    longest alphabetic core (ties -> the later token). ``focus_token`` overrides
    the heuristic with an explicit token match (case-insensitive, whitespace-
    insensitive)."""
    if focus_token is not None:
        target = focus_token.strip().lower()
        for i in sorted(altered):
            if tokens[i].strip().lower() == target:
                return {i}
    best: int | None = None
    best_len = 0
    for i in sorted(altered):
        core = re.sub(r"[^A-Za-z]", "", tokens[i])
        if core and len(core) >= best_len:
            best, best_len = i, len(core)
    return {best} if best is not None else set()


def _prepare(graph: dict[str, Any], max_edges: int) -> dict[str, Any]:
    """Layout one panel: positions, radii, pruned edges, dynamic layer rows, node stats."""
    nodes = graph.get("nodes", [])
    tokens = graph.get("metadata", {}).get("prompt_tokens", [])
    top_layer = max_numeric_layer(nodes)

    layer_of = {n["node_id"]: node_display_layer(n, top_layer) for n in nodes}
    logit_layer = top_layer + 1

    # Total |incident weight| per node = the node's attribution mass. Drives tooltip values,
    # proportional radii, and the pick of each category's most prominent node. Computed
    # before layout because the logit-spread stacking needs the radii.
    node_weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        node_weight[link.get("source")] += w
        node_weight[link.get("target")] += w
    max_mass = max(node_weight.values(), default=1.0) or 1.0
    mass_frac = {n["node_id"]: node_weight[n["node_id"]] / max_mass for n in nodes}
    radius = {n["node_id"]: _node_radius(n, mass_frac[n["node_id"]]) for n in nodes}

    # Predictive spread: logit nodes sharing a token column stack vertically,
    # best probability on top, spaced rim-to-rim so every label stays readable.
    logit_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if layer_of[node["node_id"]] == logit_layer:
            logit_groups[node.get("ctx_idx", 0)].append(node)
    logit_offset: dict[str, float] = {}
    max_stack = 0.0
    for group in logit_groups.values():
        group.sort(key=lambda n: -(_logit_prob(n) or 0.0))
        cursor_px = 0.0
        prev_r: float | None = None
        for node in group:
            r = radius[node["node_id"]]
            if prev_r is not None:
                cursor_px += prev_r + LOGIT_STACK_GAP + r
            logit_offset[node["node_id"]] = cursor_px
            prev_r = r
        max_stack = max(max_stack, cursor_px)

    # Dynamic y-axis: only occupied layers get a row; empty runs compress to a small gap.
    # The step into the logit row grows by the spread's stack height.
    occupied = sorted(set(layer_of.values()))
    row_of: dict[int, float] = {}
    cursor = 0.0
    elisions: list[float] = []  # row positions of compressed gaps (for faint tick marks)
    for i, layer in enumerate(occupied):
        if i > 0:
            step = 1.0 if layer - occupied[i - 1] == 1 else ELIDED_GAP_ROWS
            if step != 1.0:
                elisions.append(cursor + step / 2)
            if layer == logit_layer:
                step += max_stack / ROW_HEIGHT
            cursor += step
        row_of[layer] = cursor
    total_rows = max(cursor, 1.0)

    inner_w = PANEL_WIDTH - MARGIN["left"] - MARGIN["right"]
    panel_height = int(MARGIN["top"] + MARGIN["bottom"] + total_rows * ROW_HEIGHT)
    n_cols = max([len(tokens)] + [n.get("ctx_idx", 0) + 1 for n in nodes])

    def x_of(ctx_idx: float) -> float:
        return MARGIN["left"] + (ctx_idx + 0.5) / n_cols * inner_w

    def y_of_row(row: float) -> float:
        return MARGIN["top"] + (total_rows - row) * ROW_HEIGHT

    positions: dict[str, tuple[float, float]] = {}
    cell_counts: dict[tuple[int, int], int] = defaultdict(int)
    for node in nodes:
        node_id = node["node_id"]
        layer = layer_of[node_id]
        ctx = node.get("ctx_idx", 0)
        if node_id in logit_offset:
            # spread stack: no jitter; offsets grow downward from the logit row
            positions[node_id] = (x_of(ctx), y_of_row(row_of[layer]) + logit_offset[node_id])
            continue
        slot = cell_counts[(ctx, layer)]
        cell_counts[(ctx, layer)] += 1
        dx = ((slot % 3) - 1) * JITTER
        dy = (slot // 3) * JITTER
        positions[node_id] = (x_of(ctx) + dx, y_of_row(row_of[layer]) - dy)

    links = sorted(graph.get("links", []), key=lambda link: -abs(link.get("weight", 0.0)))
    dropped = max(0, len(links) - max_edges)
    links = links[:max_edges]
    max_weight = max((abs(link.get("weight", 0.0)) for link in links), default=1.0) or 1.0

    prominent: dict[str, str] = {}
    for category in CATEGORY_COLORS:
        # exemplar labels sit on feature nodes only: a "Structural" tag on the
        # top logit or an embedding square mislabels the most important marks
        candidates = [n for n in nodes
                      if _category(n) == category
                      and n.get("feature_type") not in ("logit", "embedding")]
        if candidates:
            prominent[category] = max(candidates, key=lambda n: node_weight[n["node_id"]])["node_id"]

    occupied_layers = sorted(row_of)
    # Deep graphs label every 5th layer (plus ends/emb/logit); shallow ones keep all ticks.
    thin_ticks = len(occupied_layers) > 12

    def _keep_tick(layer: int) -> bool:
        if not thin_ticks:
            return True
        if layer in (occupied_layers[0], occupied_layers[-1], -1, top_layer + 1):
            return True
        return layer % 5 == 0

    layer_ticks = [(_layer_label(layer, top_layer), y_of_row(row))
                   for layer, row in row_of.items() if _keep_tick(layer)]
    logit_nodes = [n for n in nodes if n.get("feature_type") == "logit"]
    top_logit_id = (
        max(logit_nodes, key=lambda n: (_logit_prob(n) or 0.0))["node_id"]
        if logit_nodes else None
    )
    return {
        "top_logit_id": top_logit_id,
        "nodes": nodes,
        "links": links,
        "positions": positions,
        "radius": radius,
        "mass_frac": mass_frac,
        "tokens": tokens,
        "x_of": x_of,
        "max_weight": max_weight,
        "dropped_edges": dropped,
        "node_weight": node_weight,
        "prominent": prominent,
        "layer_ticks": layer_ticks,
        "elision_ys": [y_of_row(row) for row in elisions],
        "panel_height": panel_height,
        "category_of": {n["node_id"]: _category(n) for n in nodes},
    }


def _edge_style(weight: float, max_weight: float, muted: bool) -> tuple[str, float, float]:
    """(color, stroke_width, opacity). Low weights fade to near-invisible."""
    frac = abs(weight) / max_weight if max_weight else 0.0
    width = 0.4 + 3.4 * frac**1.1
    opacity = 0.05 + 0.75 * frac**1.3
    if muted:
        return MUTED_EDGE_COLOR, min(width, 1.2), min(opacity, 0.35)
    return (POSITIVE_EDGE_COLOR if weight >= 0 else NEGATIVE_EDGE_COLOR), width, opacity


def _trim_endpoints(
    src: tuple[float, float], tgt: tuple[float, float], r_src: float, r_tgt: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Pull both endpoints back to the node rims so curves don't pierce circle centers.

    Curves have vertical tangents at their endpoints, so the trim is applied along y
    (falling back to x for near-horizontal connections)."""
    (x1, y1), (x2, y2) = src, tgt
    if abs(y2 - y1) > r_src + r_tgt + 2:
        sign = 1.0 if y2 > y1 else -1.0
        return (x1, y1 + sign * r_src), (x2, y2 - sign * r_tgt)
    if abs(x2 - x1) > r_src + r_tgt + 2:
        sign = 1.0 if x2 > x1 else -1.0
        return (x1 + sign * r_src, y1), (x2 - sign * r_tgt, y2)
    return src, tgt


def _bezier_d(src: tuple[float, float], tgt: tuple[float, float], r_src: float, r_tgt: float) -> str:
    """Vertical-tangent cubic bezier between node rims."""
    (x1, y1), (x2, y2) = _trim_endpoints(src, tgt, r_src, r_tgt)
    mid = (y2 - y1) * 0.55
    return f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + mid:.1f} {x2:.1f},{y2 - mid:.1f} {x2:.1f},{y2:.1f}"


def _logit_label(node: dict[str, Any]) -> str:
    """Display label for a logit node: '\u201ctherapist\u201d \u00b7 prob 0.86' (no p= syntax)."""
    token, prob = parse_logit_clerp(node.get("clerp"))
    token = bare_token(token)  # hosted clerps wrap the token as Output "..."
    if prob is None:
        return (node.get("clerp") or "")[:24]
    return f"\u201c{token[:20]}\u201d \u00b7 prob {prob:.2f}"


def _node_tooltip_data(node: dict[str, Any], mass: float, mass_frac: float) -> dict[str, str]:
    """Pre-escaped strings for the JS tooltip.

    ``wl``/``w`` carry the labeled numeric readout: next-token probability for
    logit nodes, attribution mass (absolute + normalized) for everything else.
    The normalized value is the same number printed on high-confidence clinical
    nodes, so on-chart labels and tooltips always agree."""
    med = node.get("medlang") or {}
    description = med.get("description") or node.get("clerp") or "(no description)"
    token, prob = parse_logit_clerp(node.get("clerp")) if node.get("feature_type") == "logit" else ("", None)
    if node.get("feature_type") == "logit" and prob is not None:
        weight_label, weight_value = f"prob({token})", f"{prob:.2f}"
    else:
        weight_label, weight_value = "mass", f"{mass:.3f} (norm {mass_frac:.2f})"
    return {
        "id": html.escape(f"{node.get('node_id')} · {node.get('feature_type')}"),
        "cat": html.escape(f"{med.get('category', 'structural')} ({med.get('method', '-')})"),
        "wl": weight_label,
        "w": weight_value,
        "desc": html.escape(str(description)),
    }


def _panel_svg(
    panel: dict[str, Any],
    prep: dict[str, Any],
    x_offset: float,
    y_offset: float,
    panel_index: int,
) -> tuple[list[str], list[dict]]:
    """SVG parts for one panel spec placed at (x_offset, y_offset) on the canvas."""
    emphasized_tokens: set[int] = panel.get("emphasized") or set()
    emphasis_color: str = panel.get("accent", INK)
    value_labels: bool = panel.get("value_labels", False)
    headline: str | None = panel.get("headline")

    parts = [f'<g transform="translate({x_offset:.0f},{y_offset:.0f})">']
    # Title splits at the first ': ' into a large role line (readable even at
    # gallery-thumbnail scale) and a smaller prompt line underneath.
    role_text, _, prompt_text = (panel["label"] or "").partition(": ")
    parts.append(f'<text x="{MARGIN["left"]}" y="34" class="t">{html.escape(role_text)}</text>')
    if prompt_text:
        parts.append(
            f'<text x="{MARGIN["left"]}" y="60" class="tp">{html.escape(prompt_text)}</text>'
        )
    if headline:
        # Big numeric callout: the one number each panel exists to show. The
        # logit spread owns the right edge; the left column is always free.
        parts.append(
            f'<text x="{MARGIN["left"]}" y="{100 if prompt_text else 74}" class="pp">'
            f"{html.escape(headline)}</text>"
        )

    positions, radius = prep["positions"], prep["radius"]
    max_weight, category_of = prep["max_weight"], prep["category_of"]

    for label, y in prep["layer_ticks"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">{label}</text>')
    for y in prep["elision_ys"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">&#8942;</text>')

    dimmed_nodes: set[str] = panel.get("dimmed") or set()
    for link in prep["links"]:
        src_id, tgt_id = link.get("source"), link.get("target")
        src, tgt = positions.get(src_id), positions.get(tgt_id)
        if src is None or tgt is None:
            continue
        weight = link.get("weight", 0.0)
        muted = (
            (category_of.get(src_id) == "structural" and category_of.get(tgt_id) == "structural")
            or src_id in dimmed_nodes or tgt_id in dimmed_nodes
        )
        color, width, opacity = _edge_style(weight, max_weight, muted)
        d = _bezier_d(src, tgt, radius.get(src_id, 0.0), radius.get(tgt_id, 0.0))
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="{width:.2f}" stroke-opacity="{opacity:.3f}"/>'
        )

    tooltip_data: list[dict] = []
    for node in prep["nodes"]:
        node_id = node["node_id"]
        pos = positions.get(node_id)
        if pos is None:
            continue
        category = _category(node)
        color = CATEGORY_COLORS[category]
        r = radius[node_id]
        frac = prep["mass_frac"][node_id]
        idx = len(tooltip_data)
        tooltip_data.append(_node_tooltip_data(node, prep["node_weight"][node_id], frac))
        hook = f'class="n" data-p="{panel_index}" data-i="{idx}"'
        if node_id in dimmed_nodes:
            dim_attr = f' fill-opacity="{DIMMED_NODE_OPACITY}"'
        elif category == "structural" and node.get("feature_type") != "logit":
            # logits stay full-ink: their size IS the prediction probability
            dim_attr = f' fill-opacity="{STRUCTURAL_FILL_OPACITY}"'
        else:
            dim_attr = ""
        if node.get("feature_type") == "embedding":
            parts.append(
                f'<rect {hook} x="{pos[0] - r:.1f}" y="{pos[1] - r:.1f}" '
                f'width="{2 * r:.1f}" height="{2 * r:.1f}" fill="{color}"{dim_attr}/>'
            )
        else:
            parts.append(
                f'<circle {hook} cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{r:.1f}" '
                f'fill="{color}"{dim_attr}/>'
            )
        if node.get("feature_type") == "logit" and node.get("clerp"):
            is_top = node_id == prep.get("top_logit_id")
            cls = "llt" if is_top else "ll"
            parts.append(
                f'<text x="{pos[0] - r - 7:.1f}" y="{pos[1] + (5 if is_top else 4):.1f}" class="{cls}">'
                f"{html.escape(_logit_label(node))}</text>"
            )
            if is_top:
                parts.append(
                    f'<circle cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{r + 3.5:.1f}" fill="none" '
                    f'stroke="{INK}" stroke-width="1.8"/>'
                )
        # Threshold-based value layer: high-confidence clinical intermediates only.
        if value_labels and category == "clinical" and frac >= NODE_VALUE_THRESHOLD and node_id not in dimmed_nodes:
            parts.append(f'<text x="{pos[0]:.1f}" y="{pos[1] + r + 10:.1f}" class="nv">{frac:.2f}</text>')

    # Inline category labels beside each category's most prominent node (no detached legend).
    for category, node_id in prep["prominent"].items():
        pos = positions.get(node_id)
        if pos is None or node_id in dimmed_nodes:
            continue
        parts.append(
            f'<text x="{pos[0] + radius[node_id] + 5:.1f}" y="{pos[1] + 4:.1f}" class="cl" '
            f'fill="{CATEGORY_COLORS[category]}">{CATEGORY_LABELS[category]}</text>'
        )

    # Token baseline: the compared word is the entire point of the figure, so
    # it gets weight, size, and an accent underline that reads even when the
    # text itself is thumbnail-small.
    token_y = prep["panel_height"] - MARGIN["bottom"] + 30
    for i, token in enumerate(prep["tokens"]):
        x = prep["x_of"](i)
        if i in emphasized_tokens:
            half = max(16.0, len(token) * 4.8)
            parts.append(
                f'<text x="{x:.1f}" y="{token_y}" class="tk tke" '
                f'style="fill:{emphasis_color}">{html.escape(token)}</text>'
            )
            parts.append(
                f'<rect x="{x - half:.1f}" y="{token_y + 6:.1f}" width="{2 * half:.1f}" '
                f'height="3.5" fill="{emphasis_color}"/>'
            )
        else:
            parts.append(f'<text x="{x:.1f}" y="{token_y}" class="tk">{html.escape(token)}</text>')

    if prep["dropped_edges"]:
        parts.append(
            f'<text x="{PANEL_WIDTH - MARGIN["right"]}" y="{prep["panel_height"] - 6:.0f}" '
            f'class="lk" text-anchor="end">{prep["dropped_edges"]} weakest edges omitted</text>'
        )
    parts.append("</g>")
    return parts, tooltip_data


# Minified inline assets for the standalone export.
_CSS = (
    "html,body{background:#fff;margin:0;padding:0}"
    "body{font-family:-apple-system,'Helvetica Neue',Helvetica,Arial,sans-serif;color:" + INK + "}"
    "main{max-width:1240px;margin:0 auto;padding:20px 16px}"
    "main.wide{max-width:2520px}"
    "h1{font-size:24px;font-weight:700;margin:0 0 4px;letter-spacing:-.01em}"
    ".lg{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:13px;color:#4b5563;"
    "margin:2px 0 16px;line-height:2}"
    ".lg .sw{display:inline-block;width:10px;height:10px;margin:0 6px 0 0;vertical-align:-1px}"
    ".lg b{color:" + INK + ";font-weight:600}"
    ".lg .gap{display:inline-block;width:18px}"
    "svg{width:100%;height:auto;display:block}"
    # role line: readable at ~34% gallery-thumbnail scale
    ".t{font-size:30px;font-weight:800;fill:" + INK + ";letter-spacing:-.01em}"
    # prompt sentence: secondary, full-width legible line
    ".tp{font-size:17px;font-weight:400;fill:#374151}"
    # headline number: the panel's one number, unmissable at any scale
    ".pp{font-size:34px;font-weight:800;fill:" + INK + ";font-family:ui-monospace,Menlo,monospace}"
    ".tk{font-size:13px;text-anchor:middle;fill:#475569;font-family:ui-monospace,'SF Mono',Menlo,monospace}"
    ".tke{font-size:16.5px;font-weight:800}"
    ".ll{font-size:12.5px;text-anchor:end;fill:#4b5563;font-family:ui-monospace,Menlo,monospace}"
    ".llt{font-size:20px;font-weight:800;text-anchor:end;fill:" + INK + ";"
    "font-family:ui-monospace,Menlo,monospace}"
    ".lk{font-size:11.5px;text-anchor:end;fill:#6b7280}"
    ".nv{font-size:11px;text-anchor:middle;fill:#4b5563;font-family:ui-monospace,Menlo,monospace}"
    ".bd{font-size:24px;font-weight:800;text-anchor:middle}"
    ".cl{font-size:13px;font-weight:700}"
    ".n{cursor:pointer}.n:hover{stroke:#9aa3af;stroke-width:1.6}"  # visible on green AND black nodes
    "#tt{position:absolute;display:none;max-width:360px;background:#fff;border:1px solid #d1d5db;"
    "border-radius:4px;padding:9px 11px;font-size:13px;line-height:1.5;box-shadow:0 2px 8px rgba(0,0,0,.09);"
    "pointer-events:none;z-index:9}"
    "#tt .h{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#334155}"
    "#tt .c{font-weight:600}#tt .d{color:#374151;margin-top:3px}"
)

_JS = (
    "var tt=document.getElementById('tt'),pinned=false;"
    "function show(e,px,py){"
    "var d=DATA[+e.dataset.p][+e.dataset.i];"
    "tt.innerHTML='<div class=h>'+d.id+'</div>"
    "<div class=c>'+d.cat+' &middot; '+d.wl+': '+d.w+'</div><div class=d>'+d.desc+'</div>';"
    "tt.style.display='block';"
    "var x=px+14,y=py+12,de=document.documentElement;"
    "if(x+tt.offsetWidth+8>de.clientWidth+de.scrollLeft+window.scrollX)x=px-tt.offsetWidth-14;"
    "if(x<2)x=2;"
    "if(y+tt.offsetHeight+8>window.scrollY+window.innerHeight)y=py-tt.offsetHeight-12;"
    "if(y<2)y=2;"
    "tt.style.left=x+'px';tt.style.top=y+'px';}"
    "document.querySelectorAll('.n').forEach(function(e){"
    "e.addEventListener('mousemove',function(ev){if(!pinned)show(e,ev.pageX,ev.pageY);});"
    "e.addEventListener('mouseleave',function(){if(!pinned)tt.style.display='none';});"
    # tap/click fallback: pin the tooltip so hover-only devices are not required
    "e.addEventListener('click',function(ev){"
    "ev.stopPropagation();pinned=true;show(e,ev.pageX,ev.pageY);});});"
    "document.addEventListener('click',function(){pinned=false;tt.style.display='none';});"
)

_LEGEND = (
    f'<span class="sw" style="background:{CATEGORY_COLORS["clinical"]}"></span><b>clinical</b>'
    '<span class="gap"></span>'
    f'<span class="sw" style="background:{CATEGORY_COLORS["off_target"]}"></span><b>off-target</b>'
    '<span class="gap"></span>'
    f'<span class="sw" style="background:{CATEGORY_COLORS["structural"]}"></span><b>structural</b>'
    '<span class="gap"></span>node size = attribution mass'
    '<span class="gap"></span>curve width/opacity = |attribution weight|'
    '<span class="gap"></span>'
    f'<span style="color:{NEGATIVE_EDGE_COLOR};font-weight:600">red curve</span> = negative'
    '<span class="gap"></span>hover or tap any node for details'
)


def _document(svg_parts: list[str], data: list[list[dict]], width: int, height: int, wide: bool = False) -> str:
    """Assemble the standalone HTML page around rendered SVG parts + tooltip payload."""
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    main_class = ' class="wide"' if wide else ""
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Attribution graph comparison</title>"
        f"<style>{_CSS}</style></head><body><main{main_class}>"
        "<h1>Attribution graph comparison</h1>"
        f"<div class=\"lg\">{_LEGEND}</div>"
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f"{''.join(svg_parts)}</svg></main>"
        '<div id="tt"></div>'
        f"<script>var DATA={payload};{_JS}</script></body></html>"
    )


def build_panels(
    graphs: list[dict[str, Any]],
    labels: list[str | None] | None = None,
    focus_tokens: list[str | None] | None = None,
    accents: list[str] | None = None,
    value_label_flags: list[bool] | None = None,
    headlines: list[str | None] | None = None,
    refs: list[int] | None = None,
    dimmed: list[set[str] | None] | None = None,
) -> list[dict[str, Any]]:
    """Build panel specs for the renderers.

    Defaults follow the clinical/patient/translated convention: panel 1 is the
    patient wording (orange accent, no value labels); every other panel is a
    clinical-role panel (blue accent, value labels on). ``refs`` names each
    panel's comparison partner for baseline emphasis (default: panel 0 vs
    panel 1, every later panel vs the panel above it). ``dimmed`` gives each
    panel a set of node_ids to fade into background context (shared-circuit
    de-emphasis in pairwise diff views): faded fill, no value labels, and
    edges touching a dimmed node render muted.
    """
    token_lists = [g.get("metadata", {}).get("prompt_tokens", []) for g in graphs]
    panels: list[dict[str, Any]] = []
    for i, graph in enumerate(graphs):
        role = DEFAULT_PANEL_ROLES[i] if i < len(DEFAULT_PANEL_ROLES) else f"Panel {i + 1}"
        prompt = graph.get("metadata", {}).get("prompt", "")
        label = (labels[i] if labels and labels[i] else None) or f"{role}: “{prompt}”"
        accent = accents[i] if accents else (
            CATEGORY_COLORS["off_target"] if i == 1 else CATEGORY_COLORS["clinical"]
        )
        value_labels = value_label_flags[i] if value_label_flags else (i != 1)
        if len(graphs) > 1:
            ref = refs[i] if refs else (1 if i == 0 else i - 1)
            altered, _ = _altered_token_indices(token_lists[i], token_lists[ref])
            focus = _focus_token_index(
                token_lists[i], altered, focus_tokens[i] if focus_tokens else None
            )
        else:
            focus = set()
        panels.append({
            "graph": graph,
            "label": label,
            "accent": accent,
            "emphasized": focus,
            "value_labels": value_labels,
            "headline": headlines[i] if headlines else None,
            "dimmed": (dimmed[i] if dimmed and i < len(dimmed) else None) or set(),
        })
    return panels


def _badge_lines(badge: Any) -> list[tuple[str, str]]:
    """Normalize a badge spec (str | {'text','color'} | {'lines': [...]}) to [(text, color)]."""
    if isinstance(badge, dict) and "lines" in badge:
        return [line for entry in badge["lines"] for line in _badge_lines(entry)]
    if isinstance(badge, dict):
        return [(str(badge.get("text", "")), str(badge.get("color", INK)))]
    return [(str(badge), INK)]


# ---------------------------------------------------------------------------
# Engine 1: vertical stack (2panel mode + translation chain)
# ---------------------------------------------------------------------------


def render_panels_html(
    panels: list[dict[str, Any]],
    out_path: str,
    badges: list[Any] | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> str:
    """Write a standalone, responsive vertically-stacked comparison page; returns out_path.

    ``badges`` holds one optional entry per gap between panels (len(panels)-1):
    a string, {"text", "color"}, or {"lines": [...]} for multi-line interstitials
    (e.g. the translation-step strip), rendered centered in that gap."""
    badges = badges or []
    svg_parts: list[str] = []
    data: list[list[dict]] = []
    y_offset = 0.0
    for panel_index, panel in enumerate(panels):
        prep = _prepare(panel["graph"], max_edges)
        parts, tooltip_data = _panel_svg(panel, prep, 0.0, y_offset, panel_index)
        svg_parts.extend(parts)
        data.append(tooltip_data)
        y_offset += prep["panel_height"]
        if panel_index < len(panels) - 1:
            badge = badges[panel_index] if panel_index < len(badges) else None
            if badge:
                lines = _badge_lines(badge)
                for line_index, (text, color) in enumerate(lines):
                    svg_parts.append(
                        f'<text x="{PANEL_WIDTH / 2:.0f}" y="{y_offset + 28 + line_index * BADGE_LINE_HEIGHT:.0f}" '
                        f'class="bd" fill="{color}">{html.escape(text)}</text>'
                    )
                y_offset += BADGE_GAP + (len(lines) - 1) * BADGE_LINE_HEIGHT
            else:
                y_offset += PANEL_GAP

    document = _document(svg_parts, data, PANEL_WIDTH, int(y_offset))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(document)
    logger.info("Wrote standalone comparison page to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Engine 2: 2x2 syntax-vs-terminology matrix (4quadrant mode)
# ---------------------------------------------------------------------------


def render_quadrant_html(
    panels: list[dict[str, Any]],
    out_path: str,
    badges: dict[str, Any] | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> str:
    """Write the 2x2 matrix page: panels = [A (top-left), B (top-right), C, D].

    ``badges`` keys: ``vocab_top`` / ``vocab_bottom`` render horizontally,
    centered on the column gutter between the compared boxes of each row (term
    swap within a frame) - vocab_top in a header strip above the top row,
    vocab_bottom in the row gutter; ``syntax_left`` / ``syntax_right`` render
    in the row gutter under each column (frame swap for a fixed term)."""
    if len(panels) != 4:
        raise ValueError(f"4-quadrant layout requires exactly 4 panels, got {len(panels)}")
    badges = badges or {}
    preps = [_prepare(p["graph"], max_edges) for p in panels]
    row_top = max(preps[0]["panel_height"], preps[1]["panel_height"])
    row_bottom = max(preps[2]["panel_height"], preps[3]["panel_height"])
    col_x = (0.0, PANEL_WIDTH + QUAD_GUTTER_X)
    row_y = (float(QUAD_VOCAB_STRIP), QUAD_VOCAB_STRIP + row_top + QUAD_GUTTER_Y)
    width = int(PANEL_WIDTH * 2 + QUAD_GUTTER_X)
    height = int(row_y[1] + row_bottom)

    svg_parts: list[str] = []
    data: list[list[dict]] = []
    placements = [(col_x[0], row_y[0]), (col_x[1], row_y[0]), (col_x[0], row_y[1]), (col_x[1], row_y[1])]
    for panel_index, (panel, prep, (x, y)) in enumerate(zip(panels, preps, placements)):
        parts, tooltip_data = _panel_svg(panel, prep, x, y, panel_index)
        svg_parts.extend(parts)
        data.append(tooltip_data)

    # Horizontal vocabulary deltas, centered on the gutter between the compared boxes:
    # the top one in the header strip, the bottom one in the row gutter above C/D.
    gutter_cx = PANEL_WIDTH + QUAD_GUTTER_X / 2
    for key, cy in (("vocab_top", QUAD_VOCAB_STRIP - 12), ("vocab_bottom", row_y[1] - 16)):
        if badges.get(key):
            text, color = _badge_lines(badges[key])[0]
            svg_parts.append(
                f'<text x="{gutter_cx:.0f}" y="{cy:.0f}" class="bd" fill="{color}">{html.escape(text)}</text>'
            )
    # Syntax deltas in the row gutter, centered under each column.
    gutter_cy = QUAD_VOCAB_STRIP + row_top + 36
    for key, cx in (("syntax_left", PANEL_WIDTH / 2), ("syntax_right", col_x[1] + PANEL_WIDTH / 2)):
        if badges.get(key):
            text, color = _badge_lines(badges[key])[0]
            svg_parts.append(
                f'<text x="{cx:.0f}" y="{gutter_cy:.0f}" class="bd" fill="{color}">{html.escape(text)}</text>'
            )

    document = _document(svg_parts, data, width, height, wide=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(document)
    logger.info("Wrote 4-quadrant comparison page to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# PNG engines (matplotlib/networkx) sharing one panel painter
# ---------------------------------------------------------------------------


def _paint_panel_ax(ax, prep: dict[str, Any], panel: dict[str, Any]) -> None:
    """Paint one panel spec onto a matplotlib axes (mirrors _panel_svg)."""
    import networkx as nx
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    panel_h = prep["panel_height"]
    positions = {nid: (x, panel_h - y) for nid, (x, y) in prep["positions"].items()}  # flip y
    radius, category_of = prep["radius"], prep["category_of"]

    g = nx.DiGraph()
    g.add_nodes_from(positions)
    for link in prep["links"]:
        src, tgt = link.get("source"), link.get("target")
        if src in positions and tgt in positions:
            weight = link.get("weight", 0.0)
            dimmed_nodes = panel.get("dimmed") or set()
            muted = (
                (category_of.get(src) == "structural" and category_of.get(tgt) == "structural")
                or src in dimmed_nodes or tgt in dimmed_nodes
            )
            color, width, opacity = _edge_style(weight, prep["max_weight"], muted)
            p1, p2 = _trim_endpoints(positions[src], positions[tgt], radius[src], radius[tgt])
            (x1, y1), (x2, y2) = p1, p2
            mid = (y2 - y1) * 0.55
            path = MplPath(
                [(x1, y1), (x1, y1 + mid), (x2, y2 - mid), (x2, y2)],
                [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4],
            )
            ax.add_patch(PathPatch(path, fill=False, edgecolor=color, linewidth=width, alpha=opacity))

    dimmed_nodes = panel.get("dimmed") or set()
    for node in prep["nodes"]:
        node_id = node["node_id"]
        x, y = positions[node_id]
        r = radius[node_id]
        marker = "s" if node.get("feature_type") == "embedding" else "o"
        if node_id in dimmed_nodes:
            alpha = DIMMED_NODE_OPACITY
        elif _category(node) == "structural" and node.get("feature_type") != "logit":
            alpha = STRUCTURAL_FILL_OPACITY
        else:
            alpha = 1.0
        ax.scatter([x], [y], s=r**2 * 3.4, c=CATEGORY_COLORS[_category(node)],
                   marker=marker, zorder=3, alpha=alpha)
        if node.get("feature_type") == "logit" and node.get("clerp"):
            is_top = node_id == prep.get("top_logit_id")
            ax.text(x - r - 6, y, _logit_label(node), ha="right", va="center",
                    fontsize=13 if is_top else 8.5,
                    fontweight="bold" if is_top else "normal",
                    color=INK if is_top else "#4b5563", family="monospace")
            if is_top:
                ax.scatter([x], [y], s=(r + 3.5)**2 * 3.4, facecolors="none",
                           edgecolors=INK, linewidths=1.4, zorder=4)
        frac = prep["mass_frac"][node_id]
        if (panel.get("value_labels") and _category(node) == "clinical"
                and frac >= NODE_VALUE_THRESHOLD and node_id not in dimmed_nodes):
            ax.text(x, y - r - 11, f"{frac:.2f}", ha="center", fontsize=8,
                    color="#4b5563", family="monospace")

    for category, node_id in prep["prominent"].items():
        if node_id in dimmed_nodes:
            continue
        x, y = positions[node_id]
        ax.text(x + radius[node_id] + 6, y - 3, CATEGORY_LABELS[category], fontsize=10,
                fontweight="bold", color=CATEGORY_COLORS[category])

    for label, y in prep["layer_ticks"]:
        ax.text(MARGIN["left"] - 12, panel_h - y - 3, label, ha="right", fontsize=8, color="#6b7280")
    emphasized = panel.get("emphasized") or set()
    for token_index, token in enumerate(prep["tokens"]):
        is_emphasized = token_index in emphasized
        tx = prep["x_of"](token_index)
        ax.text(
            tx, MARGIN["bottom"] - 30, token,
            ha="center", fontsize=11 if is_emphasized else 9,
            color=panel.get("accent", TOKEN_INK) if is_emphasized else "#475569",
            fontweight="bold" if is_emphasized else "normal",
            family="monospace",
        )
        if is_emphasized:
            half = max(16.0, len(token) * 4.8)
            ax.plot([tx - half, tx + half],
                    [MARGIN["bottom"] - 40, MARGIN["bottom"] - 40],
                    color=panel.get("accent", TOKEN_INK), linewidth=2.4,
                    solid_capstyle="butt", zorder=4)

    role_text, _, prompt_text = (panel.get("label") or "").partition(": ")
    ax.text(MARGIN["left"], panel_h - 34, role_text, ha="left",
            fontsize=17, fontweight="bold", color=INK)
    if prompt_text:
        ax.text(MARGIN["left"], panel_h - 58, prompt_text, ha="left",
                fontsize=10.5, color="#374151")
    if panel.get("headline"):
        ax.text(MARGIN["left"], panel_h - (96 if prompt_text else 70), panel["headline"],
                ha="left", fontsize=19, fontweight="bold", color=INK, family="monospace")
    ax.set_xlim(0, PANEL_WIDTH)
    ax.set_ylim(0, panel_h)
    ax.set_facecolor("white")
    ax.axis("off")


def _png_legend(fig: Any) -> None:
    """One-line reading key at the top of static exports (mirrors the HTML legend)."""
    entries = [
        ("\u25cf clinical", CATEGORY_COLORS["clinical"], "bold"),
        ("\u25cf off-target", CATEGORY_COLORS["off_target"], "bold"),
        ("\u25cf structural", "#9aa8b8", "bold"),
        ("node size = attribution mass", "#4b5563", "normal"),
        ("curve width/opacity = |weight|", "#4b5563", "normal"),
        ("red curve = negative", NEGATIVE_EDGE_COLOR, "bold"),
    ]
    x = 0.01
    for text, color, weight in entries:
        fig.text(x, 0.995, text, ha="left", va="top", fontsize=9,
                 color=color, family="monospace", fontweight=weight)
        x += 0.017 + len(text) * 0.0062


def render_panels_png(
    panels: list[dict[str, Any]],
    out_path: str,
    badges: list[Any] | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    dpi: int = 160,
) -> str:
    """Write a static vertically-stacked comparison PNG; returns out_path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    badges = badges or []
    preps = [_prepare(p["graph"], max_edges) for p in panels]
    heights = [p["panel_height"] for p in preps]
    fig_height = sum(heights) / 90.0
    fig, axes = plt.subplots(
        len(panels), 1, figsize=(13, max(fig_height, 6)), height_ratios=heights,
        facecolor="white", squeeze=False,
    )
    axes = axes[:, 0]
    _png_legend(fig)

    max_badge_lines = 1
    for panel_index, (ax, prep, panel) in enumerate(zip(axes, preps, panels)):
        _paint_panel_ax(ax, prep, panel)
        # Delta/interstitial badge centered above this panel (the gap below the previous one).
        if panel_index > 0 and panel_index - 1 < len(badges) and badges[panel_index - 1]:
            lines = _badge_lines(badges[panel_index - 1])
            max_badge_lines = max(max_badge_lines, len(lines))
            for line_index, (text, color) in enumerate(reversed(lines)):
                ax.text(0.5, 1.055 + 0.06 * line_index, text, transform=ax.transAxes,
                        ha="center", fontsize=15, fontweight="bold", color=color)

    fig.tight_layout(h_pad=2.0 + 2.0 * max_badge_lines)
    fig.savefig(out_path, dpi=dpi, facecolor="white")
    plt.close(fig)
    logger.info("Wrote stacked PNG to %s", out_path)
    return out_path


def render_quadrant_png(
    panels: list[dict[str, Any]],
    out_path: str,
    badges: dict[str, Any] | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    dpi: int = 160,
) -> str:
    """Write the 2x2 matrix PNG: panels = [A, B, C, D]; badges as in render_quadrant_html."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(panels) != 4:
        raise ValueError(f"4-quadrant layout requires exactly 4 panels, got {len(panels)}")
    badges = badges or {}
    preps = [_prepare(p["graph"], max_edges) for p in panels]
    row_heights = [max(preps[0]["panel_height"], preps[1]["panel_height"]),
                   max(preps[2]["panel_height"], preps[3]["panel_height"])]
    fig_height = sum(row_heights) / 90.0
    fig, axes = plt.subplots(
        2, 2, figsize=(24, max(fig_height, 7)), height_ratios=row_heights,
        facecolor="white", squeeze=False,
    )
    _png_legend(fig)
    order = [axes[0][0], axes[0][1], axes[1][0], axes[1][1]]
    for ax, prep, panel in zip(order, preps, panels):
        _paint_panel_ax(ax, prep, panel)

    def _one(badge: Any) -> tuple[str, str]:
        return _badge_lines(badge)[0]

    # Vocabulary deltas horizontal, centered on the gutter between the compared boxes.
    for key, ax in (("vocab_top", axes[0][0]), ("vocab_bottom", axes[1][0])):
        if badges.get(key):
            text, color = _one(badges[key])
            ax.text(1.03, 1.045, text, transform=ax.transAxes, ha="center",
                    fontsize=15, fontweight="bold", color=color)
    # Syntax deltas horizontal in the row gutter, centered under each column.
    for key, ax in (("syntax_left", axes[1][0]), ("syntax_right", axes[1][1])):
        if badges.get(key):
            text, color = _one(badges[key])
            ax.text(0.5, 1.11, text, transform=ax.transAxes, ha="center",
                    fontsize=15, fontweight="bold", color=color)

    fig.tight_layout(h_pad=4.0, w_pad=4.0)
    fig.savefig(out_path, dpi=dpi, facecolor="white")
    plt.close(fig)
    logger.info("Wrote 4-quadrant PNG to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Two-panel wrappers (the classic clinical/patient stack)
# ---------------------------------------------------------------------------


def render_stacked_html(
    top_graph: dict[str, Any],
    bottom_graph: dict[str, Any],
    out_path: str,
    top_title: str | None = None,
    bottom_title: str | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    top_focus_token: str | None = None,
    bottom_focus_token: str | None = None,
    badges: list[Any] | None = None,
) -> str:
    """Two-panel wrapper around render_panels_html (clinical top, patient bottom)."""
    panels = build_panels(
        [top_graph, bottom_graph],
        labels=[top_title, bottom_title],
        focus_tokens=[top_focus_token, bottom_focus_token],
    )
    return render_panels_html(panels, out_path, badges=badges, max_edges=max_edges)


def render_stacked_png(
    top_graph: dict[str, Any],
    bottom_graph: dict[str, Any],
    out_path: str,
    top_title: str | None = None,
    bottom_title: str | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    dpi: int = 160,
    top_focus_token: str | None = None,
    bottom_focus_token: str | None = None,
    badges: list[Any] | None = None,
) -> str:
    """Two-panel wrapper around render_panels_png (clinical top, patient bottom)."""
    panels = build_panels(
        [top_graph, bottom_graph],
        labels=[top_title, bottom_title],
        focus_tokens=[top_focus_token, bottom_focus_token],
    )
    return render_panels_png(panels, out_path, badges=badges, max_edges=max_edges, dpi=dpi)
