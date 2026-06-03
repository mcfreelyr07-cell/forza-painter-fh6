"""Pure Pillow CPU preview renderer for geometry JSON.

Renders rotated-ellipse geometry onto a target image using the formula
documented in the region-focused-painting spec (§7).  No GPU or exe
dependency — used after each region pass because the exe's own preview
is based on the masked target and is unsuitable for display.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image


def render_preview(
    target_path: str | Path,
    shapes: list[dict],
    output_path: str | Path,
    max_preview_size: int = 500,
) -> None:
    """Render *shapes* onto *target_path* and save to *output_path*.

    1. Load *target_path* as the RGBA canvas base.
    2. Skip ``shapes[0]`` (the type-1 background rectangle).
    3. For each type-16 rotated ellipse, alpha-blend onto the canvas.
    4. Resize to fit *max_preview_size* (maintaining aspect ratio) and
       save as PNG.
    """
    target_path = Path(target_path)
    output_path = Path(output_path)

    canvas = Image.open(target_path).convert("RGBA")
    w, h = canvas.size
    pixels = canvas.load()

    for shape in shapes[1:]:
        shape_type = shape.get("type", 0)
        if shape_type != 16:
            continue

        data = shape.get("data", [])
        color = shape.get("color", [0, 0, 0, 255])
        if len(data) < 5 or len(color) < 4:
            continue
        if color[3] <= 0:
            continue

        x, y, rx, ry, theta_deg = data[:5]
        r, g, b, a = color[:4]

        if rx <= 0 or ry <= 0:
            continue

        # Pre-compute rotation constants.
        theta = math.radians(theta_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        inv_rx2 = 1.0 / (rx * rx)
        inv_ry2 = 1.0 / (ry * ry)

        # Alpha as float [0, 1].
        alpha = a / 255.0

        # Bounding box in pixel space.
        rx_int = int(math.ceil(rx)) + 1
        ry_int = int(math.ceil(ry)) + 1
        x0 = max(0, int(x) - rx_int)
        y0 = max(0, int(y) - ry_int)
        x1 = min(w, int(x) + rx_int + 1)
        y1 = min(h, int(y) + ry_int + 1)

        for py in range(y0, y1):
            for px in range(x0, x1):
                dx = (px + 0.5) - x
                dy = (py + 0.5) - y
                xr = dx * cos_t + dy * sin_t
                yr = -dx * sin_t + dy * cos_t

                if xr * xr * inv_rx2 + yr * yr * inv_ry2 <= 1.0:
                    pr, pg, pb, pa = pixels[px, py]
                    pa_f = pa / 255.0
                    blend = alpha * (1.0 - pa_f) + pa_f
                    if blend <= 0:
                        continue
                    out_r = int((r * alpha + pr * pa_f * (1.0 - alpha)) / blend)
                    out_g = int((g * alpha + pg * pa_f * (1.0 - alpha)) / blend)
                    out_b = int((b * alpha + pb * pa_f * (1.0 - alpha)) / blend)
                    out_a = int(blend * 255)
                    pixels[px, py] = (min(255, out_r), min(255, out_g), min(255, out_b), min(255, out_a))

    # Resize.
    if max(w, h) > max_preview_size:
        ratio = max_preview_size / max(w, h)
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))
        canvas = canvas.resize((new_w, new_h), Image.LANCZOS)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")


def load_shapes_from_json(json_path: str | Path) -> list[dict]:
    """Load the ``shapes`` list from a geometry JSON file."""
    with open(json_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    return payload.get("shapes", [])
