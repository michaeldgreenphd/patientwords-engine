"""Task 2: stacked two-panel comparison visualization of tagged graphs.

Tufte-styled rendering (maximize data-ink, minimize chartjunk):

- pure white background; no bounding boxes, grids, or panel fills
- no detached legend: category names are written inline next to each
  category's most prominent node, in that category's color
- structural/embedding/logit nodes and structural-to-structural edges are a
  muted light gray so they recede; saturated blue (clinical) and orange
  (off_target) are reserved for transcoder features
- node radius is proportional to normalized attribution mass (logits: the
  next-token probability), from a 3px floor for muted structural marks to a
  14px cap for a high-probability logit
- edges are cubic bezier curves whose stroke width and opacity scale with
  |attribution weight|, trimmed at both ends to the node rims so curves snap
  to circle edges instead of piercing the centers
- the layer axis is dynamic: only layers that contain active nodes get a row,
  and runs of empty layers are compressed to a small elision gap (marked by a
  faint tick), so deep models stay compact
- the token baseline is a micro/macro read: of the tokens that differ between
  the two phrasings, only the single compared content word is emphasized
  (bold, panel accent color: "depression" in blue vs "blues" in orange);
  surrounding differenced function words stay muted like static tokens
- top (clinical) panel only: clinical nodes whose normalized attribution mass
  meets NODE_VALUE_THRESHOLD get their value printed beside the node, showing
  at a glance which intermediate concepts drive the high-confidence prediction

Outputs:
    render_stacked_html - one standalone, responsive index.html for static
        hosting (GitHub Pages): minified inline CSS/JS, interactive hover
        tooltips showing feature id, category, probability/attribution mass,
        and the full autointerp description fetched during tagging
    render_stacked_png  - matplotlib/networkx static figure, same styling
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

logger = logging.getLogger(__name__)

CATEGORY_COLORS = {
    "clinical": "#2563eb",
    "off_target": "#f97316",
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
MARGIN = {"left": 66, "right": 34, "top": 40, "bottom": 56}

MIN_RADIUS = 3.0  # muted structural/embedding floor
MAX_RADIUS = 14.0  # cap (a probability-1.0 logit)
FEATURE_RADIUS_BASE = 4.0
FEATURE_RADIUS_SPAN = 6.0  # feature nodes span 4..10px by sqrt(mass fraction)
STRUCTURAL_RADIUS_SPAN = 2.0  # structural marks span 3..5px
JITTER = 9.0

# Clinical nodes at or above this normalized attribution mass get an on-chart
# value label (top/clinical panel only).
NODE_VALUE_THRESHOLD = 0.5

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

    # Dynamic y-axis: only occupied layers get a row; empty runs compress to a small gap.
    occupied = sorted(set(layer_of.values()))
    row_of: dict[int, float] = {}
    cursor = 0.0
    elisions: list[float] = []  # row positions of compressed gaps (for faint tick marks)
    for i, layer in enumerate(occupied):
        if i > 0:
            step = 1.0 if layer - occupied[i - 1] == 1 else ELIDED_GAP_ROWS
            if step != 1.0:
                elisions.append(cursor + step / 2)
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
        layer = layer_of[node["node_id"]]
        ctx = node.get("ctx_idx", 0)
        slot = cell_counts[(ctx, layer)]
        cell_counts[(ctx, layer)] += 1
        dx = ((slot % 3) - 1) * JITTER
        dy = (slot // 3) * JITTER
        positions[node["node_id"]] = (x_of(ctx) + dx, y_of_row(row_of[layer]) - dy)

    # Total |incident weight| per node = the node's attribution mass. Drives tooltip values,
    # proportional radii, and the pick of each category's most prominent node.
    node_weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        node_weight[link.get("source")] += w
        node_weight[link.get("target")] += w
    max_mass = max(node_weight.values(), default=1.0) or 1.0
    mass_frac = {n["node_id"]: node_weight[n["node_id"]] / max_mass for n in nodes}
    radius = {n["node_id"]: _node_radius(n, mass_frac[n["node_id"]]) for n in nodes}

    links = sorted(graph.get("links", []), key=lambda link: -abs(link.get("weight", 0.0)))
    dropped = max(0, len(links) - max_edges)
    links = links[:max_edges]
    max_weight = max((abs(link.get("weight", 0.0)) for link in links), default=1.0) or 1.0

    prominent: dict[str, str] = {}
    for category in CATEGORY_COLORS:
        candidates = [n for n in nodes if _category(n) == category]
        if candidates:
            prominent[category] = max(candidates, key=lambda n: node_weight[n["node_id"]])["node_id"]

    layer_ticks = [(_layer_label(layer, top_layer), y_of_row(row)) for layer, row in row_of.items()]
    return {
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
    width = 0.3 + 2.3 * frac**1.2
    opacity = 0.03 + 0.55 * frac**1.6
    if muted:
        return MUTED_EDGE_COLOR, min(width, 1.0), min(opacity, 0.35)
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


def _node_tooltip_data(node: dict[str, Any], mass: float, mass_frac: float) -> dict[str, str]:
    """Pre-escaped strings for the JS tooltip.

    ``wl``/``w`` carry the labeled numeric readout: next-token probability for
    logit nodes, attribution mass (absolute + normalized) for everything else.
    The normalized value is the same number printed on high-confidence clinical
    nodes, so on-chart labels and tooltips always agree."""
    med = node.get("medlang") or {}
    description = med.get("description") or node.get("clerp") or "(no description)"
    prob = _logit_prob(node)
    if node.get("feature_type") == "logit" and prob is not None:
        weight_label, weight_value = "Probability", f"{prob:.2f}"
    else:
        weight_label, weight_value = "Mass", f"{mass:.3f} (norm {mass_frac:.2f})"
    return {
        "id": html.escape(f"{node.get('node_id')} · {node.get('feature_type')}"),
        "cat": html.escape(f"{med.get('category', 'structural')} ({med.get('method', '-')})"),
        "wl": weight_label,
        "w": weight_value,
        "desc": html.escape(str(description)),
    }


def _panel_svg(
    title: str,
    prep: dict[str, Any],
    y_offset: float,
    panel_index: int,
    emphasized_tokens: set[int],
    emphasis_color: str,
    value_labels: bool,
) -> tuple[list[str], list[dict]]:
    parts = [f'<g transform="translate(0,{y_offset:.0f})">']
    parts.append(f'<text x="{MARGIN["left"]}" y="22" class="t">{html.escape(title)}</text>')

    positions, radius = prep["positions"], prep["radius"]
    max_weight, category_of = prep["max_weight"], prep["category_of"]

    for label, y in prep["layer_ticks"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">{label}</text>')
    for y in prep["elision_ys"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">&#8942;</text>')

    for link in prep["links"]:
        src_id, tgt_id = link.get("source"), link.get("target")
        src, tgt = positions.get(src_id), positions.get(tgt_id)
        if src is None or tgt is None:
            continue
        weight = link.get("weight", 0.0)
        muted = category_of.get(src_id) == "structural" and category_of.get(tgt_id) == "structural"
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
        if node.get("feature_type") == "embedding":
            parts.append(
                f'<rect {hook} x="{pos[0] - r:.1f}" y="{pos[1] - r:.1f}" '
                f'width="{2 * r:.1f}" height="{2 * r:.1f}" fill="{color}"/>'
            )
        else:
            parts.append(f'<circle {hook} cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{r:.1f}" fill="{color}"/>')
        if node.get("feature_type") == "logit" and node.get("clerp"):
            parts.append(
                f'<text x="{pos[0]:.1f}" y="{pos[1] - r - 5:.1f}" class="ll">{html.escape(node["clerp"][:24])}</text>'
            )
        # Threshold-based value layer: high-confidence clinical intermediates only.
        if value_labels and category == "clinical" and frac >= NODE_VALUE_THRESHOLD:
            parts.append(f'<text x="{pos[0]:.1f}" y="{pos[1] + r + 10:.1f}" class="nv">{frac:.2f}</text>')

    # Inline category labels beside each category's most prominent node (no detached legend).
    for category, node_id in prep["prominent"].items():
        pos = positions.get(node_id)
        if pos is None:
            continue
        parts.append(
            f'<text x="{pos[0] + radius[node_id] + 5:.1f}" y="{pos[1] + 4:.1f}" class="cl" '
            f'fill="{CATEGORY_COLORS[category]}">{CATEGORY_LABELS[category]}</text>'
        )

    # Token baseline: emphasize the altered words so the intervention reads at a glance.
    token_y = prep["panel_height"] - MARGIN["bottom"] + 26
    for i, token in enumerate(prep["tokens"]):
        style = f' style="fill:{emphasis_color};font-weight:600"' if i in emphasized_tokens else ""
        parts.append(f'<text x="{prep["x_of"](i):.1f}" y="{token_y}" class="tk"{style}>{html.escape(token)}</text>')

    if prep["dropped_edges"]:
        parts.append(
            f'<text x="{PANEL_WIDTH - MARGIN["right"]}" y="22" class="lk" text-anchor="end">'
            f"{prep['dropped_edges']} weakest edges omitted</text>"
        )
    parts.append("</g>")
    return parts, tooltip_data


# Minified inline assets for the standalone export.
_CSS = (
    "html,body{background:#fff;margin:0;padding:0}"
    "body{font-family:-apple-system,'Helvetica Neue',Helvetica,Arial,sans-serif;color:" + INK + "}"
    "main{max-width:1240px;margin:0 auto;padding:20px 16px}"
    "h1{font-size:17px;font-weight:600;margin:0 0 2px}"
    "p.sub{font-size:12px;color:" + FAINT_INK + ";margin:0 0 14px}"
    "svg{width:100%;height:auto;display:block}"
    ".t{font-size:13px;font-weight:600;fill:" + INK + "}"
    ".tk{font-size:10.5px;text-anchor:middle;fill:" + TOKEN_INK + ";font-family:ui-monospace,'SF Mono',Menlo,monospace}"
    ".ll{font-size:9.5px;text-anchor:middle;fill:#374151;font-family:ui-monospace,Menlo,monospace}"
    ".lk{font-size:9px;text-anchor:end;fill:" + FAINT_INK + "}"
    ".nv{font-size:9px;text-anchor:middle;fill:#6b7280;font-family:ui-monospace,Menlo,monospace}"
    ".cl{font-size:11px;font-weight:600}"
    ".n{cursor:pointer}.n:hover{stroke:" + INK + ";stroke-width:1.6}"
    "#tt{position:absolute;display:none;max-width:340px;background:#fff;border:1px solid #d1d5db;"
    "border-radius:4px;padding:8px 10px;font-size:12px;line-height:1.45;box-shadow:0 2px 8px rgba(0,0,0,.09);"
    "pointer-events:none;z-index:9}"
    "#tt .h{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#334155}"
    "#tt .c{font-weight:600}#tt .d{color:#374151;margin-top:3px}"
)

_JS = (
    "var tt=document.getElementById('tt');"
    "document.querySelectorAll('.n').forEach(function(e){"
    "e.addEventListener('mousemove',function(ev){"
    "var d=DATA[+e.dataset.p][+e.dataset.i];"
    "tt.innerHTML='<div class=h>'+d.id+'</div>"
    "<div class=c>'+d.cat+' &middot; '+d.wl+': '+d.w+'</div><div class=d>'+d.desc+'</div>';"
    "tt.style.display='block';"
    "var x=ev.pageX+14,y=ev.pageY+12;"
    "if(x+360>document.documentElement.clientWidth)x=ev.pageX-354;"
    "tt.style.left=x+'px';tt.style.top=y+'px';});"
    "e.addEventListener('mouseleave',function(){tt.style.display='none';});});"
)


def render_stacked_html(
    top_graph: dict[str, Any],
    bottom_graph: dict[str, Any],
    out_path: str,
    top_title: str | None = None,
    bottom_title: str | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    top_focus_token: str | None = None,
    bottom_focus_token: str | None = None,
) -> str:
    """Write a standalone, responsive comparison page (GitHub Pages ready); returns out_path.

    ``top_focus_token``/``bottom_focus_token`` override the heuristic pick of the
    single emphasized baseline word per panel."""
    top_tokens = top_graph.get("metadata", {}).get("prompt_tokens", [])
    bottom_tokens = bottom_graph.get("metadata", {}).get("prompt_tokens", [])
    altered_top, altered_bottom = _altered_token_indices(top_tokens, bottom_tokens)
    focus_top = _focus_token_index(top_tokens, altered_top, top_focus_token)
    focus_bottom = _focus_token_index(bottom_tokens, altered_bottom, bottom_focus_token)
    panels = (
        (top_graph, "Clinical wording", top_title, focus_top, CATEGORY_COLORS["clinical"], True),
        (bottom_graph, "Patient wording", bottom_title, focus_bottom, CATEGORY_COLORS["off_target"], False),
    )

    svg_parts: list[str] = []
    data: list[list[dict]] = []
    y_offset = 0.0
    for panel_index, (graph, default_label, title, emphasized, accent, value_labels) in enumerate(panels):
        prep = _prepare(graph, max_edges)
        prompt = graph.get("metadata", {}).get("prompt", "")
        label = title or f"{default_label}: “{prompt}”"
        parts, tooltip_data = _panel_svg(label, prep, y_offset, panel_index, emphasized, accent, value_labels)
        svg_parts.extend(parts)
        data.append(tooltip_data)
        y_offset += prep["panel_height"] + 14

    total_height = int(y_offset)
    # JSON payload is embedded in a script tag: escape "</" so descriptions can't close it.
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Attribution graph comparison</title>"
        f"<style>{_CSS}</style></head><body><main>"
        "<h1>Attribution graph comparison</h1>"
        "<p class=\"sub\">Hover a node for its feature id, category, probability/attribution mass, and "
        "autointerp description. Node size scales with attribution mass (logits: next-token "
        "probability); curve width and opacity scale with |attribution weight|; "
        f"<span style=\"color:{NEGATIVE_EDGE_COLOR}\">red</span> curves are negative. The emphasized "
        "baseline token in each panel marks the compared word; numbers beside clinical nodes (top "
        f"panel) show normalized attribution mass &#8805; {NODE_VALUE_THRESHOLD:.2f}.</p>"
        f'<svg viewBox="0 0 {PANEL_WIDTH} {total_height}" xmlns="http://www.w3.org/2000/svg">'
        f"{''.join(svg_parts)}</svg></main>"
        '<div id="tt"></div>'
        f"<script>var DATA={payload};{_JS}</script></body></html>"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(document)
    logger.info("Wrote standalone comparison page to %s", out_path)
    return out_path


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
) -> str:
    """Write a static stacked-comparison PNG (networkx + matplotlib), same styling; returns out_path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    top_tokens = top_graph.get("metadata", {}).get("prompt_tokens", [])
    bottom_tokens = bottom_graph.get("metadata", {}).get("prompt_tokens", [])
    altered_top, altered_bottom = _altered_token_indices(top_tokens, bottom_tokens)
    focus_top = _focus_token_index(top_tokens, altered_top, top_focus_token)
    focus_bottom = _focus_token_index(bottom_tokens, altered_bottom, bottom_focus_token)
    preps = [_prepare(g, max_edges) for g in (top_graph, bottom_graph)]
    heights = [p["panel_height"] for p in preps]
    fig_height = sum(heights) / 90.0
    fig, axes = plt.subplots(
        2, 1, figsize=(13, max(fig_height, 6)), height_ratios=heights, facecolor="white"
    )

    for ax, prep, graph, default_label, title, emphasized, accent, value_labels in (
        (axes[0], preps[0], top_graph, "Clinical wording", top_title, focus_top,
         CATEGORY_COLORS["clinical"], True),
        (axes[1], preps[1], bottom_graph, "Patient wording", bottom_title, focus_bottom,
         CATEGORY_COLORS["off_target"], False),
    ):
        panel_h = prep["panel_height"]
        positions = {nid: (x, panel_h - y) for nid, (x, y) in prep["positions"].items()}  # flip y
        radius, category_of = prep["radius"], prep["category_of"]

        g = nx.DiGraph()
        g.add_nodes_from(positions)
        for link in prep["links"]:
            src, tgt = link.get("source"), link.get("target")
            if src in positions and tgt in positions:
                weight = link.get("weight", 0.0)
                muted = category_of.get(src) == "structural" and category_of.get(tgt) == "structural"
                color, width, opacity = _edge_style(weight, prep["max_weight"], muted)
                p1, p2 = _trim_endpoints(positions[src], positions[tgt], radius[src], radius[tgt])
                (x1, y1), (x2, y2) = p1, p2
                mid = (y2 - y1) * 0.55
                path = MplPath(
                    [(x1, y1), (x1, y1 + mid), (x2, y2 - mid), (x2, y2)],
                    [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4],
                )
                ax.add_patch(PathPatch(path, fill=False, edgecolor=color, linewidth=width, alpha=opacity))

        for node in prep["nodes"]:
            node_id = node["node_id"]
            x, y = positions[node_id]
            r = radius[node_id]
            marker = "s" if node.get("feature_type") == "embedding" else "o"
            ax.scatter([x], [y], s=r**2 * 3.4, c=CATEGORY_COLORS[_category(node)], marker=marker, zorder=3)
            if node.get("feature_type") == "logit" and node.get("clerp"):
                ax.text(x, y + r + 5, node["clerp"][:24], ha="center", fontsize=7,
                        color="#374151", family="monospace")
            frac = prep["mass_frac"][node_id]
            if value_labels and _category(node) == "clinical" and frac >= NODE_VALUE_THRESHOLD:
                ax.text(x, y - r - 11, f"{frac:.2f}", ha="center", fontsize=7,
                        color="#6b7280", family="monospace")

        for category, node_id in prep["prominent"].items():
            x, y = positions[node_id]
            ax.text(x + radius[node_id] + 6, y - 3, CATEGORY_LABELS[category], fontsize=9,
                    fontweight="bold", color=CATEGORY_COLORS[category])

        for label, y in prep["layer_ticks"]:
            ax.text(MARGIN["left"] - 12, panel_h - y - 3, label, ha="right", fontsize=7, color=FAINT_INK)
        for i, token in enumerate(prep["tokens"]):
            emphasized_token = i in emphasized
            ax.text(
                prep["x_of"](i),
                MARGIN["bottom"] - 30,
                token,
                ha="center",
                fontsize=8,
                color=accent if emphasized_token else TOKEN_INK,
                fontweight="bold" if emphasized_token else "normal",
                family="monospace",
            )

        prompt = graph.get("metadata", {}).get("prompt", "")
        ax.set_title(title or f"{default_label}: “{prompt}”", fontsize=11, loc="left", color=INK)
        ax.set_xlim(0, PANEL_WIDTH)
        ax.set_ylim(0, panel_h)
        ax.set_facecolor("white")
        ax.axis("off")

    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, facecolor="white")
    plt.close(fig)
    logger.info("Wrote stacked PNG to %s", out_path)
    return out_path
