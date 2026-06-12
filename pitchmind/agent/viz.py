"""Visualization router. Phase 1 ships exactly one template: a shot map with xG.

A shot map is rendered only when the plan asked for one and the result rows carry shot
geometry (x, y, xg). Marker size encodes xG; goals are highlighted.
"""

from __future__ import annotations

import time

import matplotlib

matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt  # noqa: E402
from mplsoccer import VerticalPitch  # noqa: E402

from .. import config
from .executor import ExecResult
from .types import Plan


def _is_truthy(v: object) -> bool:
    return bool(v) and str(v).lower() not in {"false", "0", "none", ""}


def maybe_render(plan: Plan, result: ExecResult, *, title: str = "") -> str | None:
    """Render a shot map if applicable; return the PNG path or None."""
    if plan.viz_type != "shot_map":
        return None
    cols = set(result.columns)
    if not {"x", "y"}.issubset(cols) or not result.rows:
        return None

    pitch = VerticalPitch(
        pitch_type="statsbomb", half=True, pad_bottom=-10,
        pitch_color="#f7f7f4", line_color="#3b3b3b",
    )
    fig, ax = pitch.draw(figsize=(7, 7))

    for row in result.rows:
        x, y = row.get("x"), row.get("y")
        if x is None or y is None:
            continue
        xg = float(row.get("xg") or 0.0)
        is_goal = _is_truthy(row.get("is_goal")) or str(
            row.get("shot_outcome", "")
        ).lower() == "goal"
        size = 120 * xg + 25
        pitch.scatter(
            x, y, s=size, ax=ax,
            color="#d7263d" if is_goal else "#3a86ff",
            edgecolors="black", linewidth=0.5,
            alpha=0.85 if is_goal else 0.55,
            zorder=3 if is_goal else 2,
        )

    if title:
        ax.set_title(title, fontsize=13, pad=8)
    fig.text(
        0.5, 0.03,
        "Marker size ∝ xG · red = goal · Data: StatsBomb",
        ha="center", fontsize=8, color="#555",
    )

    config.ensure_dirs()
    path = config.DATA_DIR / f"shot_map_{int(time.time())}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(path)
