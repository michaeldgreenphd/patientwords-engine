"""Task 2: stacked two-panel comparison visualization of tagged graphs.

Tufte-styled rendering (maximize data-ink, minimize chartjunk):

- pure white background; no bounding boxes, grids, or panel fills
- no detached legend: category names are written inline next to each
  category's most prominent node, in that category's color
- structural/embedding/logit nodes and structural-to-structural edges are a
  muted light gray so they recede; saturated blue (clinical) and orange
  (off_target) are reserved for transcoder features
- edges are cubic bezier curves whose stroke width and opacity scale with
  |attribution weight| - near-zero weights are nearly invisible
- the layer axis is dynamic: only layers that contain active nodes get a row,
  and runs of empty layers are compressed to a small elision gap (marked by a
  faint tick), so deep models stay compact

Outputs:
    render_stacked_html - one standalone, responsive index.html for static
        hosting (GitHub Pages): minified inline CSS/JS, interactive hover
        tooltips showing feature id, category, attribution weight, and the
        full autointerp description fetched during tagging
    render_stacked_png  - matplotlib/networkx static figure, same styling
"""

from __future__ import annotations

import html
import json
import logging
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

DEFAULT_MAX_EDGES = 400
PANEL_WIDTH = 1180
ROW_HEIGHT = 34
ELIDED_GAP_ROWS = 1.45  # vertical space for a run of >=1 empty layers
MARGIN = {"left": 66, "right": 34, "top": 40, "bottom": 56}
FEATURE_RADIUS = 5.0
STRUCTURAL_RADIUS = 3.0


def _category(node: dict[str, Any]) -> str:
    return (node.get("medlang") or {}).get("category") or "structural"


def _layer_label(layer: int, top_layer: int) -> str:
    if layer == -1:
        return "emb"
    if layer == top_layer + 1:
        return "logit"
    return f"L{layer}"


def _prepare(graph: dict[str, Any], max_edges: int) -> dict[str, Any]:
    """Layout one panel: positions, pruned edges, dynamic layer rows, node stats."""
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
        dx = ((slot % 3) - 1) * FEATURE_RADIUS * 1.8
        dy = (slot // 3) * FEATURE_RADIUS * 2.0
        positions[node["node_id"]] = (x_of(ctx) + dx, y_of_row(row_of[layer]) - dy)

    # Total |incident weight| per node = the node's attribution mass (shown in tooltips,
    # and used to pick the most prominent node per category for inline labels).
    node_weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        node_weight[link.get("source")] += w
        node_weight[link.get("target")] += w

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


def _bezier_d(src: tuple[float, float], tgt: tuple[float, float]) -> str:
    """Vertical-tangent cubic bezier from source up to target."""
    (x1, y1), (x2, y2) = src, tgt
    mid = (y2 - y1) * 0.55
    return f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + mid:.1f} {x2:.1f},{y2 - mid:.1f} {x2:.1f},{y2:.1f}"


def _node_tooltip_data(node: dict[str, Any], weight: float) -> dict[str, str]:
    """Pre-escaped strings for the JS tooltip (feature id, category, weight, description)."""
    med = node.get("medlang") or {}
    description = med.get("description") or node.get("clerp") or "(no description)"
    return {
        "id": html.escape(f"{node.get('node_id')} · {node.get('feature_type')}"),
        "cat": html.escape(f"{med.get('category', 'structural')} ({med.get('method', '-')})"),
        "w": f"{weight:.3f}",
        "desc": html.escape(str(description)),
    }


def _panel_svg(title: str, prep: dict[str, Any], y_offset: float, panel_index: int) -> tuple[list[str], list[dict]]:
    parts = [f'<g transform="translate(0,{y_offset:.0f})">']
    parts.append(f'<text x="{MARGIN["left"]}" y="22" class="t">{html.escape(title)}</text>')

    positions, max_weight, category_of = prep["positions"], prep["max_weight"], prep["category_of"]

    for label, y in prep["layer_ticks"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">{label}</text>')
    for y in prep["elision_ys"]:
        parts.append(f'<text x="{MARGIN["left"] - 12}" y="{y + 3:.1f}" class="lk">&#8942;</text>')

    for link in prep["links"]:
        src, tgt = positions.get(link.get("source")), positions.get(link.get("target"))
        if src is None or tgt is None:
            continue
        weight = link.get("weight", 0.0)
        muted = category_of.get(link.get("source")) == "structural" and category_of.get(link.get("target")) == "structural"
        color, width, opacity = _edge_style(weight, max_weight, muted)
        parts.append(
            f'<path d="{_bezier_d(src, tgt)}" fill="none" stroke="{color}" '
            f'stroke-width="{width:.2f}" stroke-opacity="{opacity:.3f}"/>'
        )

    tooltip_data: list[dict] = []
    for node in prep["nodes"]:
        pos = positions.get(node["node_id"])
        if pos is None:
            continue
        category = _category(node)
        color = CATEGORY_COLORS[category]
        idx = len(tooltip_data)
        tooltip_data.append(_node_tooltip_data(node, prep["node_weight"][node["node_id"]]))
        hook = f'class="n" data-p="{panel_index}" data-i="{idx}"'
        if category == "structural":
            if node.get("feature_type") == "embedding":
                parts.append(
                    f'<rect {hook} x="{pos[0] - 3:.1f}" y="{pos[1] - 3:.1f}" width="6" height="6" fill="{color}"/>'
                )
            else:
                parts.append(f'<circle {hook} cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{STRUCTURAL_RADIUS}" fill="{color}"/>')
            if node.get("feature_type") == "logit" and node.get("clerp"):
                parts.append(
                    f'<text x="{pos[0]:.1f}" y="{pos[1] - 8:.1f}" class="ll">{html.escape(node["clerp"][:24])}</text>'
                )
        else:
            parts.append(f'<circle {hook} cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{FEATURE_RADIUS}" fill="{color}"/>')

    # Inline category labels beside each category's most prominent node (no detached legend).
    for category, node_id in prep["prominent"].items():
        pos = positions.get(node_id)
        if pos is None:
            continue
        parts.append(
            f'<text x="{pos[0] + 10:.1f}" y="{pos[1] + 4:.1f}" class="cl" fill="{CATEGORY_COLORS[category]}">'
            f"{CATEGORY_LABELS[category]}</text>"
        )

    token_y = prep["panel_height"] - MARGIN["bottom"] + 26
    for i, token in enumerate(prep["tokens"]):
        parts.append(f'<text x="{prep["x_of"](i):.1f}" y="{token_y}" class="tk">{html.escape(token)}</text>')

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
    ".tk{font-size:10.5px;text-anchor:middle;fill:#475569;font-family:ui-monospace,'SF Mono',Menlo,monospace}"
    ".ll{font-size:9.5px;text-anchor:middle;fill:#374151;font-family:ui-monospace,Menlo,monospace}"
    ".lk{font-size:9px;text-anchor:end;fill:" + FAINT_INK + "}"
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
    "tt.innerHTML='<div class=h>'+d.id+'</div><div class=c>'+d.cat+' &middot; attribution '+d.w+'</div><div class=d>'+d.desc+'</div>';"
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
) -> str:
    """Write a standalone, responsive comparison page (GitHub Pages ready); returns out_path."""
    svg_parts: list[str] = []
    data: list[list[dict]] = []
    y_offset = 0.0
    for panel_index, (graph, default_label, title) in enumerate(
        ((top_graph, "Clinical wording", top_title), (bottom_graph, "Patient wording", bottom_title))
    ):
        prep = _prepare(graph, max_edges)
        prompt = graph.get("metadata", {}).get("prompt", "")
        label = title or f"{default_label}: “{prompt}”"
        parts, tooltip_data = _panel_svg(label, prep, y_offset, panel_index)
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
        "<p class=\"sub\">Hover a node for its feature id, category, attribution mass, and autointerp "
        "description. Curve width and opacity scale with |attribution weight|; "
        f"<span style=\"color:{NEGATIVE_EDGE_COLOR}\">red</span> curves are negative.</p>"
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
) -> str:
    """Write a static stacked-comparison PNG (networkx + matplotlib), same styling; returns out_path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    preps = [_prepare(g, max_edges) for g in (top_graph, bottom_graph)]
    heights = [p["panel_height"] for p in preps]
    fig_height = sum(heights) / 90.0
    fig, axes = plt.subplots(
        2, 1, figsize=(13, max(fig_height, 6)), height_ratios=heights, facecolor="white"
    )

    for ax, prep, graph, default_label, title in (
        (axes[0], preps[0], top_graph, "Clinical wording", top_title),
        (axes[1], preps[1], bottom_graph, "Patient wording", bottom_title),
    ):
        panel_h = prep["panel_height"]
        positions = {nid: (x, panel_h - y) for nid, (x, y) in prep["positions"].items()}  # flip y
        category_of = prep["category_of"]

        g = nx.DiGraph()
        g.add_nodes_from(positions)
        for link in prep["links"]:
            src, tgt = link.get("source"), link.get("target")
            if src in positions and tgt in positions:
                weight = link.get("weight", 0.0)
                muted = category_of.get(src) == "structural" and category_of.get(tgt) == "structural"
                color, width, opacity = _edge_style(weight, prep["max_weight"], muted)
                (x1, y1), (x2, y2) = positions[src], positions[tgt]
                mid = (y2 - y1) * 0.55
                path = MplPath(
                    [(x1, y1), (x1, y1 + mid), (x2, y2 - mid), (x2, y2)],
                    [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4],
                )
                ax.add_patch(PathPatch(path, fill=False, edgecolor=color, linewidth=width, alpha=opacity))

        for node in prep["nodes"]:
            x, y = positions[node["node_id"]]
            category = _category(node)
            size = FEATURE_RADIUS if category != "structural" else STRUCTURAL_RADIUS
            marker = "s" if node.get("feature_type") == "embedding" else "o"
            ax.scatter([x], [y], s=size**2 * 3.4, c=CATEGORY_COLORS[category], marker=marker, zorder=3)
            if node.get("feature_type") == "logit" and node.get("clerp"):
                ax.text(x, y + 9, node["clerp"][:24], ha="center", fontsize=7, color="#374151", family="monospace")

        for category, node_id in prep["prominent"].items():
            x, y = positions[node_id]
            ax.text(x + 10, y - 3, CATEGORY_LABELS[category], fontsize=9, fontweight="bold",
                    color=CATEGORY_COLORS[category])

        for label, y in prep["layer_ticks"]:
            ax.text(MARGIN["left"] - 12, panel_h - y - 3, label, ha="right", fontsize=7, color=FAINT_INK)
        for i, token in enumerate(prep["tokens"]):
            ax.text(prep["x_of"](i), MARGIN["bottom"] - 30, token, ha="center", fontsize=8,
                    color="#475569", family="monospace")

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
