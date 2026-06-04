"""Preview renderer — same approach as scripts/heatmap.py render_preview.

Uses cv2 ellipse/rectangle draw calls with numpy boolean-mask alpha blending.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils import load_cv2

_EXE_PREVIEW_GLOB = "_exe_preview.*.png"


def _copy_exe_preview(
    output_dir: str | Path,
    preview_png: str | Path,
    max_preview_size: int = 500,
) -> bool:
    import shutil
    from PIL import Image as PILImage

    output_dir = Path(output_dir)
    preview_png = Path(preview_png)
    previews = sorted(
        output_dir.glob(_EXE_PREVIEW_GLOB),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not previews:
        return False
    shutil.copy2(previews[0], preview_png)
    try:
        img = PILImage.open(preview_png)
        w, h = img.size
        if max(w, h) > max_preview_size:
            ratio = max_preview_size / max(w, h)
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), PILImage.LANCZOS)
            img.save(preview_png, "PNG")
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# Canvas rendering — identical to scripts/heatmap.py render_preview
# ---------------------------------------------------------------------------

def _draw_shapes_to_canvas(cv2, np, shapes, image_w, image_h):
    """Draw shapes onto a BGR canvas, matching heatmap.py."""
    canvas = np.zeros((image_h, image_w, 3), dtype=np.uint8)

    bg = shapes[0]
    bg_color = bg.get("color", [0, 0, 0, 0])
    if len(bg_color) == 4 and int(bg_color[3]) > 0:
        bg_r, bg_g, bg_b, _bg_a = [int(c) for c in bg_color]
        cv2.rectangle(canvas, (0, 0), (image_w, image_h), (bg_b, bg_g, bg_r), thickness=-1)
    # else: keep black (transparent)

    for shape in shapes[1:]:
        color = shape.get("color", [])
        if len(color) == 4 and int(color[3]) <= 0:
            continue
        r, g, b, a = [int(c) for c in color]
        shape_type = int(shape["type"])
        data = shape["data"]

        mask = np.zeros((image_h, image_w), dtype=np.uint8)
        if shape_type == 1:
            x, y, w, h = data
            x0 = int(round(x - w / 2))
            y0 = int(round(y - h / 2))
            x1 = int(round(x + w / 2))
            y1 = int(round(y + h / 2))
            cv2.rectangle(mask, (x0, y0), (x1, y1), 1, thickness=-1)
        elif shape_type == 16:
            x, y, w, h, rot_deg = data
            cv2.ellipse(mask, (int(x), int(y)), (int(h), int(w)), -90 + rot_deg, 0.0, 360.0, 1, thickness=-1)
        else:
            continue

        where = mask > 0
        if a >= 255:
            canvas[where] = (b, g, r)
        else:
            alpha_norm = a / 255.0
            canvas[where] = (
                (1 - alpha_norm) * canvas[where].astype(np.float32)
                + alpha_norm * np.array([b, g, r], dtype=np.float32)
            ).astype(np.uint8)

    return canvas


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_shapes_to_array(shapes: list[dict], target_path: str | Path) -> "np.ndarray | None":
    """Render *shapes* on top of the target image (for composite)."""
    target_path = Path(target_path)
    if not shapes:
        return None
    bg_data = shapes[0].get("data", [])
    if len(bg_data) < 4:
        return None
    image_w = int(bg_data[2])
    image_h = int(bg_data[3])

    loaded = load_cv2()
    if not loaded:
        return None
    cv2, np = loaded
    # Load target as base canvas.
    canvas = cv2.imread(str(target_path), cv2.IMREAD_COLOR)
    if canvas is None:
        return None
    # Draw shapes on top (skip shapes[0] — target is the background).
    for shape in shapes[1:]:
        color = shape.get("color", [])
        if len(color) == 4 and int(color[3]) <= 0:
            continue
        r, g, b, a = [int(c) for c in color]
        shape_type = int(shape["type"])
        data = shape["data"]

        mask = np.zeros((image_h, image_w), dtype=np.uint8)
        if shape_type == 1:
            x, y, w, h = data
            x0 = int(round(x - w / 2)); y0 = int(round(y - h / 2))
            x1 = int(round(x + w / 2)); y1 = int(round(y + h / 2))
            cv2.rectangle(mask, (x0, y0), (x1, y1), 1, thickness=-1)
        elif shape_type == 16:
            x, y, w, h, rot_deg = data
            cv2.ellipse(mask, (int(x), int(y)), (int(h), int(w)), -90 + rot_deg, 0.0, 360.0, 1, thickness=-1)
        else:
            continue

        where = mask > 0
        if a >= 255:
            canvas[where] = (b, g, r)
        else:
            alpha_norm = a / 255.0
            canvas[where] = (
                (1 - alpha_norm) * canvas[where].astype(np.float32)
                + alpha_norm * np.array([b, g, r], dtype=np.float32)
            ).astype(np.uint8)
    return canvas


def render_preview(
    target_path: str | Path,
    shapes: list[dict],
    output_path: str | Path,
    max_preview_size: int = 500,
) -> None:
    """Render *shapes* exactly like heatmap.py and save as BGR PNG."""
    target_path = Path(target_path)
    output_path = Path(output_path)

    loaded = load_cv2()
    if not loaded:
        _copy_exe_preview(output_path.parent, output_path, max_preview_size)
        return

    cv2, np = loaded
    if not shapes:
        return
    bg_data = shapes[0].get("data", [])
    if len(bg_data) < 4:
        return
    image_w = int(bg_data[2])
    image_h = int(bg_data[3])

    canvas = _draw_shapes_to_canvas(cv2, np, shapes, image_w, image_h)

    if max(image_w, image_h) > max_preview_size:
        ratio = max_preview_size / max(image_w, image_h)
        new_w = max(1, int(image_w * ratio))
        new_h = max(1, int(image_h * ratio))
        canvas = cv2.resize(canvas, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Build RGBA: R,G,B from canvas (BGR→RGB), alpha=255 where non-black.
    alpha = np.where(canvas.max(axis=2) > 0, 255, 0).astype(np.uint8)
    rgba = np.dstack([canvas[:, :, 2], canvas[:, :, 1], canvas[:, :, 0], alpha])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image as PILImage
    PILImage.fromarray(rgba, "RGBA").save(str(output_path), "PNG")


def load_shapes_from_json(json_path: str | Path) -> list[dict]:
    """Load the ``shapes`` list from a geometry JSON file."""
    with open(json_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    return payload.get("shapes", [])
