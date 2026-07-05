"""Task 2: stacked two-panel comparison visualization of tagged graphs.

Renders two attribution graphs stacked vertically (clinical wording on top,
patient wording below) so each prompt's token string lays out horizontally.

Layout per panel: x = token position (ctx_idx), y = layer (embeddings at the
bottom, logits on top). Node color comes from the Task 1 ``medlang`` metadata:
clinical = blue, off_target = orange, structural = gray. Edge width and opacity
scale with |attribution weight|; negative-weight edges are dashed red.

Outputs:
    render_stacked_html - one self-contained .html (inline SVG, hover tooltips
        via <title>, no external assets)
    render_stacked_png  - matplotlib/networkx static figure for papers/slides
"""

from __future__ import annotations

import html
import logging
from typing import Any

from medlang_circuits.schema_utils import max_numeric_layer, node_display_layer

logger = logging.getLogger(__name__)

CATEGORY_COLORS = {
    "clinical": "#2563eb",  # blue
    "off_target": "#f97316",  # orange
    "structural": "#9ca3af",  # gray
}
POSITIVE_EDGE_COLOR = "#64748b"
NEGATIVE_EDGE_COLOR = "#ef4444"
DEFAULT_MAX_EDGES = 400

PANEL_WIDTH = 1200
PANEL_HEIGHT = 460
MARGIN = {"left": 60, "right": 30, "top": 44, "bottom": 58}
NODE_RADIUS = 5.5


def _prepare(graph: dict[str, Any], max_edges: int) -> dict[str, Any]:
    """Compute node positions and the pruned edge list for one panel."""
    nodes = graph.get("nodes", [])
    top_layer = max_numeric_layer(nodes)
    tokens = graph.get("metadata", {}).get("prompt_tokens", [])
    n_cols = max([len(tokens)] + [n.get("ctx_idx", 0) + 1 for n in nodes])
    layer_span = top_layer + 3  # -1 (embeddings) .. top_layer + 1 (logits)

    inner_w = PANEL_WIDTH - MARGIN["left"] - MARGIN["right"]
    inner_h = PANEL_HEIGHT - MARGIN["top"] - MARGIN["bottom"]

    def x_of(ctx_idx: int) -> float:
        return MARGIN["left"] + (ctx_idx + 0.5) / n_cols * inner_w

    def y_of(layer: int) -> float:
        return MARGIN["top"] + (1 - (layer + 1.5) / layer_span) * inner_h

    positions: dict[str, tuple[float, float]] = {}
    # spread nodes sharing a (ctx, layer) cell slightly so they don't overlap
    cell_counts: dict[tuple[int, int], int] = {}
    for node in nodes:
        layer = node_display_layer(node, top_layer)
        ctx = node.get("ctx_idx", 0)
        offset_slot = cell_counts.get((ctx, layer), 0)
        cell_counts[(ctx, layer)] = offset_slot + 1
        dx = ((offset_slot % 3) - 1) * NODE_RADIUS * 1.6
        dy = (offset_slot // 3) * NODE_RADIUS * 1.8
        positions[node["node_id"]] = (x_of(ctx) + dx, y_of(layer) - dy)

    links = sorted(graph.get("links", []), key=lambda link: -abs(link.get("weight", 0.0)))
    dropped = max(0, len(links) - max_edges)
    links = links[:max_edges]
    max_weight = max((abs(link.get("weight", 0.0)) for link in links), default=1.0) or 1.0

    return {
        "nodes": nodes,
        "links": links,
        "positions": positions,
        "tokens": tokens,
        "x_of": x_of,
        "max_weight": max_weight,
        "dropped_edges": dropped,
        "top_layer": top_layer,
    }


def _node_color(node: dict[str, Any]) -> str:
    category = (node.get("medlang") or {}).get("category")
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["structural"])


def _node_tooltip(node: dict[str, Any]) -> str:
    med = node.get("medlang") or {}
    parts = [
        f"{node.get('node_id')} [{node.get('feature_type')}]",
        f"category: {med.get('category', '?')} ({med.get('method', '?')})",
    ]
    if node.get("clerp"):
        parts.append(node["clerp"])
    if med.get("matched_terms"):
        parts.append("matched: " + ", ".join(med["matched_terms"]))
    return "\n".join(parts)


def _panel_svg(title: str, prep: dict[str, Any], y_offset: int) -> list[str]:
    parts = [f'<g transform="translate(0,{y_offset})">']
    parts.append(
        f'<text x="{MARGIN["left"]}" y="24" class="panel-title">{html.escape(title)}</text>'
    )

    positions, max_weight = prep["positions"], prep["max_weight"]
    for link in prep["links"]:
        src, tgt = positions.get(link.get("source")), positions.get(link.get("target"))
        if src is None or tgt is None:
            continue
        weight = link.get("weight", 0.0)
        frac = abs(weight) / max_weight
        width = 0.4 + 2.6 * frac
        opacity = 0.12 + 0.55 * frac
        color = POSITIVE_EDGE_COLOR if weight >= 0 else NEGATIVE_EDGE_COLOR
        dash = "" if weight >= 0 else ' stroke-dasharray="4 3"'
        parts.append(
            f'<line x1="{src[0]:.1f}" y1="{src[1]:.1f}" x2="{tgt[0]:.1f}" y2="{tgt[1]:.1f}" '
            f'stroke="{color}" stroke-width="{width:.2f}" stroke-opacity="{opacity:.2f}"{dash}>'
            f"<title>{html.escape(link.get('source', ''))} -&gt; {html.escape(link.get('target', ''))} "
            f"(w={weight:.3f})</title></line>"
        )

    for node in prep["nodes"]:
        pos = positions.get(node["node_id"])
        if pos is None:
            continue
        feature_type = node.get("feature_type")
        color = _node_color(node)
        tooltip = f"<title>{html.escape(_node_tooltip(node))}</title>"
        if feature_type == "embedding":
            parts.append(
                f'<rect x="{pos[0] - 5:.1f}" y="{pos[1] - 5:.1f}" width="10" height="10" '
                f'fill="{color}" class="node">{tooltip}</rect>'
            )
        elif feature_type == "logit":
            label = html.escape((node.get("clerp") or "")[:24])
            parts.append(
                f'<g class="node"><circle cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{NODE_RADIUS}" '
                f'fill="{color}" stroke="#334155" stroke-width="1.2">{tooltip}</circle>'
                f'<text x="{pos[0]:.1f}" y="{pos[1] - 9:.1f}" class="logit-label">{label}</text></g>'
            )
        else:
            parts.append(
                f'<circle cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{NODE_RADIUS}" fill="{color}" '
                f'class="node">{tooltip}</circle>'
            )

    token_y = PANEL_HEIGHT - MARGIN["bottom"] + 24
    for i, token in enumerate(prep["tokens"]):
        parts.append(
            f'<text x="{prep["x_of"](i):.1f}" y="{token_y}" class="token">{html.escape(token)}</text>'
        )

    if prep["dropped_edges"]:
        parts.append(
            f'<text x="{PANEL_WIDTH - MARGIN["right"]}" y="24" class="note" text-anchor="end">'
            f"{prep['dropped_edges']} weakest edges hidden</text>"
        )
    parts.append(f'<text x="14" y="{MARGIN["top"] + 8}" class="axis">layer &#8593;</text>')
    parts.append("</g>")
    return parts


def render_stacked_html(
    top_graph: dict[str, Any],
    bottom_graph: dict[str, Any],
    out_path: str,
    top_title: str | None = None,
    bottom_title: str | None = None,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> str:
    """Write a self-contained stacked-comparison HTML file; returns out_path."""
    panels = []
    for graph, default_label, offset, title in (
        (top_graph, "Clinical wording", 0, top_title),
        (bottom_graph, "Patient wording", PANEL_HEIGHT + 16, bottom_title),
    ):
        prompt = graph.get("metadata", {}).get("prompt", "")
        label = title or f"{default_label}: “{prompt}”"
        panels.extend(_panel_svg(label, _prepare(graph, max_edges), offset))

    total_height = PANEL_HEIGHT * 2 + 16
    legend = "".join(
        f'<span class="key"><span class="swatch" style="background:{color}"></span>{name}</span>'
        for name, color in CATEGORY_COLORS.items()
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Attribution graph comparison</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 16px; color: #1e293b; }}
  .panel-title {{ font-size: 14px; font-weight: 600; fill: #0f172a; }}
  .token {{ font-size: 11px; text-anchor: middle; fill: #334155; font-family: ui-monospace, monospace; }}
  .logit-label {{ font-size: 10px; text-anchor: middle; fill: #0f172a; font-family: ui-monospace, monospace; }}
  .note, .axis {{ font-size: 10px; fill: #64748b; }}
  .node:hover {{ stroke: #0f172a; stroke-width: 2px; cursor: default; }}
  .legend {{ margin: 8px 0 12px; font-size: 12px; }}
  .key {{ margin-right: 16px; }}
  .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 5px; margin-right: 4px; }}
</style></head><body>
<h2 style="font-size:16px">Attribution graph comparison</h2>
<div class="legend">{legend}
  <span class="key" style="color:{POSITIVE_EDGE_COLOR}">&#9472; positive edge</span>
  <span class="key" style="color:{NEGATIVE_EDGE_COLOR}">&#9476; negative edge</span>
  <span class="key">edge width &#8733; |attribution weight|</span>
</div>
<svg width="{PANEL_WIDTH}" height="{total_height}" viewBox="0 0 {PANEL_WIDTH} {total_height}">
{chr(10).join(panels)}
</svg>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(document)
    logger.info("Wrote stacked HTML to %s", out_path)
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
    """Write a static stacked-comparison PNG via networkx + matplotlib; returns out_path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    fig, axes = plt.subplots(2, 1, figsize=(14, 11))
    for ax, graph, default_label, title in (
        (axes[0], top_graph, "Clinical wording", top_title),
        (axes[1], bottom_graph, "Patient wording", bottom_title),
    ):
        prep = _prepare(graph, max_edges)
        g = nx.DiGraph()
        # flip y for matplotlib (SVG y grows downward)
        pos = {nid: (x, PANEL_HEIGHT - y) for nid, (x, y) in prep["positions"].items()}
        for node in prep["nodes"]:
            g.add_node(node["node_id"])
        for link in prep["links"]:
            if link.get("source") in pos and link.get("target") in pos:
                g.add_edge(link["source"], link["target"], weight=link.get("weight", 0.0))

        edge_weights = [g.edges[e]["weight"] for e in g.edges]
        max_weight = prep["max_weight"]
        nx.draw_networkx_edges(
            g,
            pos,
            ax=ax,
            width=[0.4 + 2.6 * abs(w) / max_weight for w in edge_weights],
            edge_color=[POSITIVE_EDGE_COLOR if w >= 0 else NEGATIVE_EDGE_COLOR for w in edge_weights],
            alpha=0.45,
            arrows=False,
        )
        nx.draw_networkx_nodes(
            g,
            pos,
            ax=ax,
            node_size=55,
            node_color=[_node_color(n) for n in prep["nodes"]],
            edgecolors="#334155",
            linewidths=0.4,
        )
        for i, token in enumerate(prep["tokens"]):
            ax.text(prep["x_of"](i), 8, token, ha="center", fontsize=8, family="monospace")
        prompt = graph.get("metadata", {}).get("prompt", "")
        ax.set_title(title or f"{default_label}: “{prompt}”", fontsize=11, loc="left")
        ax.set_xlim(0, PANEL_WIDTH)
        ax.set_ylim(0, PANEL_HEIGHT)
        ax.axis("off")

    handles = [
        plt.Line2D([], [], marker="o", linestyle="", color=color, label=name)
        for name, color in CATEGORY_COLORS.items()
    ]
    axes[0].legend(handles=handles, loc="upper right", fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    logger.info("Wrote stacked PNG to %s", out_path)
    return out_path
