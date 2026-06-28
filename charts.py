"""
Tiny dependency-free SVG chart helpers.

Everything renders server-side as inline SVG so the app needs no charting
library, no CDN, and works fully offline. The functions return HTML strings
that are injected into templates with the |safe filter.
"""

from __future__ import annotations

from typing import Sequence

# Colour palette (kept in sync with static/style.css).
C_PRIMARY = "#2f6f8f"
C_GOOD = "#2e8b57"
C_WARN = "#d98e04"
C_BAD = "#c0392b"
C_GRID = "#e2e8ee"
C_MUTED = "#8a97a6"


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def line_chart(
    series: list[dict],
    *,
    width: int = 460,
    height: int = 260,
    x_label: str = "",
    y_label: str = "",
    x_ticks: Sequence[str] | None = None,
    y_min: float = 0.0,
    y_max: float = 1.0,
    diagonal: bool = False,
) -> str:
    """series: list of {points: [(x,y)...], color, label, dashed?} with x,y in [0,1]-ish.

    Points are expected already normalised to data units; we map y via y_min/y_max
    and x via 0..1 (the caller passes x already in 0..1).
    """
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 38
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b

    def sx(x: float) -> float:
        return pad_l + x * iw

    def sy(y: float) -> float:
        rng = (y_max - y_min) or 1.0
        return pad_t + ih - ((y - y_min) / rng) * ih

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']

    # gridlines + y ticks
    for i in range(5):
        gy = pad_t + ih * i / 4
        val = y_max - (y_max - y_min) * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="{C_GRID}" />'
        )
        parts.append(
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" text-anchor="end" class="tick">{val:.2f}</text>'
        )

    # x ticks
    if x_ticks:
        n = len(x_ticks)
        for i, t in enumerate(x_ticks):
            gx = sx(i / (n - 1)) if n > 1 else sx(0.5)
            parts.append(
                f'<text x="{gx:.1f}" y="{height - pad_b + 16}" text-anchor="middle" class="tick">{_esc(t)}</text>'
            )

    if diagonal:
        parts.append(
            f'<line x1="{sx(0):.1f}" y1="{sy(y_min):.1f}" x2="{sx(1):.1f}" y2="{sy(y_max):.1f}" '
            f'stroke="{C_MUTED}" stroke-dasharray="4 4" />'
        )

    for s in series:
        pts = s["points"]
        color = s.get("color", C_PRIMARY)
        dash = ' stroke-dasharray="5 4"' if s.get("dashed") else ""
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts)
        )
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2"{dash} />')

    if y_label:
        parts.append(
            f'<text x="12" y="{pad_t + ih / 2:.1f}" transform="rotate(-90 12 {pad_t + ih / 2:.1f})" '
            f'text-anchor="middle" class="axis-label">{_esc(y_label)}</text>'
        )
    if x_label:
        parts.append(
            f'<text x="{pad_l + iw / 2:.1f}" y="{height - 4}" text-anchor="middle" class="axis-label">{_esc(x_label)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def bar_chart(
    items: list[dict],
    *,
    width: int = 460,
    height: int = 260,
    max_value: float | None = None,
    threshold: float | None = None,
    threshold_label: str = "",
    value_fmt: str = "{:.2f}",
) -> str:
    """items: list of {label, value, color?}. Horizontal bars."""
    pad_l, pad_r, pad_t, pad_b = 150, 48, 12, 24
    iw = width - pad_l - pad_r
    n = len(items)
    if n == 0:
        return ""
    row_h = (height - pad_t - pad_b) / n
    bar_h = min(22, row_h * 0.6)
    mv = max_value if max_value is not None else max((i["value"] for i in items), default=1.0)
    mv = mv or 1.0

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']

    if threshold is not None:
        tx = pad_l + (threshold / mv) * iw
        parts.append(
            f'<line x1="{tx:.1f}" y1="{pad_t}" x2="{tx:.1f}" y2="{height - pad_b}" '
            f'stroke="{C_BAD}" stroke-dasharray="4 4" />'
        )
        if threshold_label:
            parts.append(
                f'<text x="{tx:.1f}" y="{pad_t - 1}" text-anchor="middle" class="tick" fill="{C_BAD}">{_esc(threshold_label)}</text>'
            )

    for i, it in enumerate(items):
        cy = pad_t + i * row_h + (row_h - bar_h) / 2
        w = max(1.0, (it["value"] / mv) * iw)
        color = it.get("color", C_PRIMARY)
        parts.append(
            f'<text x="{pad_l - 8}" y="{cy + bar_h / 2 + 4:.1f}" text-anchor="end" class="bar-label">{_esc(it["label"])}</text>'
        )
        parts.append(
            f'<rect x="{pad_l}" y="{cy:.1f}" width="{w:.1f}" height="{bar_h:.1f}" rx="3" fill="{color}" />'
        )
        parts.append(
            f'<text x="{pad_l + w + 6:.1f}" y="{cy + bar_h / 2 + 4:.1f}" class="tick">{_esc(value_fmt.format(it["value"]))}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def donut(segments: list[dict], *, size: int = 170, thickness: int = 26) -> str:
    """segments: list of {label, value, color}. Renders a donut with a centre total."""
    total = sum(s["value"] for s in segments) or 1
    r = (size - thickness) / 2
    cx = cy = size / 2
    circ = 2 * 3.141592653589793 * r
    parts = [f'<svg viewBox="0 0 {size} {size}" class="donut" role="img">']
    offset = 0.0
    for s in segments:
        frac = s["value"] / total
        dash = circ * frac
        gap = circ - dash
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{s["color"]}" '
            f'stroke-width="{thickness}" stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})" />'
        )
        offset += dash
    parts.append(
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" class="donut-total">{int(total)}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" class="donut-sub">models</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def confusion_matrix_svg(tn: int, fp: int, fn: int, tp: int) -> str:
    """A simple 2x2 confusion matrix grid."""
    cells = [
        ("True Neg", tn, C_GOOD),
        ("False Pos", fp, C_WARN),
        ("False Neg", fn, C_BAD),
        ("True Pos", tp, C_GOOD),
    ]
    width, height = 300, 200
    cw, ch = 120, 70
    ox, oy = 70, 30
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']
    parts.append(f'<text x="{ox + cw}" y="14" text-anchor="middle" class="tick">Predicted</text>')
    parts.append(f'<text x="{ox + cw / 2}" y="26" text-anchor="middle" class="tick">Negative</text>')
    parts.append(f'<text x="{ox + cw + cw / 2}" y="26" text-anchor="middle" class="tick">Positive</text>')
    parts.append(
        f'<text x="14" y="{oy + ch}" text-anchor="middle" class="tick" transform="rotate(-90 14 {oy + ch})">Actual</text>'
    )
    layout = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for (label, val, color), (col, rowi) in zip(cells, layout):
        x = ox + col * cw
        y = oy + rowi * ch
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{color}" opacity="0.16" stroke="{C_GRID}" />'
        )
        parts.append(f'<text x="{x + cw / 2}" y="{y + ch / 2 - 4}" text-anchor="middle" class="cm-val">{val}</text>')
        parts.append(f'<text x="{x + cw / 2}" y="{y + ch / 2 + 14}" text-anchor="middle" class="tick">{label}</text>')
    parts.append(
        f'<text x="40" y="{oy + ch / 2 + 4}" text-anchor="middle" class="tick">Neg</text>'
    )
    parts.append(
        f'<text x="40" y="{oy + ch + ch / 2 + 4}" text-anchor="middle" class="tick">Pos</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
