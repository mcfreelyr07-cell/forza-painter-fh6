"""cv2-based preview renderer for geometry JSON.

Renders rotated-ellipse geometry using OpenCV, matching the proven
approach in ``main.py``.  Much faster than Pillow pixel iteration and
produces anti-aliased output that matches the exe's rendering.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils import load_cv2

# Keep the exe-preview helper for fallback scenarios.
_EXE_PREVIEW_GLOB = "_exe_preview.*.png"


def _copy_exe_preview(
    output_dir: str | Path,
    preview_png: str | Path,
    max_preview_size: int = 500,
) -> bool:
    """Copy the exe's last checkpoint preview to *preview_png*.

    Returns ``True`` if a preview was copied, ``False`` otherwise.
    """
    import shutil

    output_dir = Path(output_dir)
    preview_png = Path(preview_png)
    previews = sorted(
        output_dir.glob(_EXE_PREVIEW_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not previews:
        return False
    shutil.copy2(previews[0], preview_png)
    # Optionally resize.
    try:
        from PIL import Image

        img = Image.open(preview_png)
        w, h = img.size
        if max(w, h) > max_preview_size:
            ratio = max_preview_size / max(w, h)
            img = img.resize(
                (max(1, int(w * ratio)), max(1, int(h * ratio))),
                Image.LANCZOS,
            )
            img.save(preview_png, "PNG")
    except Exception:
        pass
    return True


def render_shapes_to_array(shapes: list[dict]) -> "np.ndarray | None":
    """Render *shapes* to a BGR ``numpy`` array (full resolution, no resize).

    Returns ``None`` if cv2/numpy is unavailable or shapes is empty.
    Used by Solution 3: composite the rendered current state with the
    original target so the exe sees error=0 outside the selected region.
    """
    loaded = load_cv2()
    if not loaded:
        return None
    _cv2, np = loaded

    if not shapes:
        return None
    bg_data = shapes[0].get("data", [])
    bg_color = shapes[0].get("color", [0, 0, 0, 255])
    if len(bg_data) < 4:
        return None
    image_w = int(bg_data[2])
    image_h = int(bg_data[3])

    canvas = np.zeros((image_h, image_w, 3), np.uint8)
    bg_r, bg_g, bg_b, bg_a = bg_color[:4] if len(bg_color) >= 4 else (0, 0, 0, 255)
    if bg_a > 0:
        _cv2.rectangle(canvas, (0, 0), (image_w, image_h), (bg_b, bg_g, bg_r), thickness=-1)
    # else: keep black — transparent areas handled by composite alpha logic

    _draw_shapes_on_canvas(np, _cv2, canvas, shapes[1:])
    return canvas


def _draw_shapes_on_canvas(np, cv2_mod, canvas, shapes: list[dict]) -> None:
    """Draw *shapes* onto *canvas* (BGR numpy array, mutated in-place)."""
    temp = np.zeros_like(canvas)
    for shape in shapes:
        shape_type = shape.get("type", 0)
        color = shape.get("color", [0, 0, 0, 255])
        if len(color) < 4:
            continue
        r, g, b, a = color[:4]
        if a <= 0:
            continue

        bgr = (b, g, r)
        alpha_factor = a / 255.0

        if shape_type == 16:
            data = shape.get("data", [])
            if len(data) < 5:
                continue
            x, y, w, h, rot_deg = data[:5]
            if w <= 0 or h <= 0:
                continue
            cx, cy = int(x), int(y)
            axes = (int(h), int(w))
            angle = -90 + rot_deg

            if a >= 255:
                cv2_mod.ellipse(canvas, (cx, cy), axes, angle, 0.0, 360, bgr, thickness=-1)
            else:
                temp.fill(0)
                cv2_mod.ellipse(temp, (cx, cy), axes, angle, 0.0, 360, (255, 255, 255), thickness=-1)
                mask = (temp[:, :, 0] > 0).astype(np.float32) * alpha_factor
                for c in range(3):
                    canvas[:, :, c] = (canvas[:, :, c] * (1.0 - mask) + bgr[c] * mask).astype(np.uint8)

        elif shape_type == 1:
            data = shape.get("data", [])
            if len(data) < 4:
                continue
            x, y, w, h = data[:4]
            x0 = int(round(x - w / 2))
            y0 = int(round(y - h / 2))
            x1 = int(round(x + w / 2))
            y1 = int(round(y + h / 2))

            if a >= 255:
                cv2_mod.rectangle(canvas, (x0, y0), (x1, y1), bgr, thickness=-1)
            else:
                temp.fill(0)
                cv2_mod.rectangle(temp, (x0, y0), (x1, y1), (255, 255, 255), thickness=-1)
                mask = (temp[:, :, 0] > 0).astype(np.float32) * alpha_factor
                for c in range(3):
                    canvas[:, :, c] = (canvas[:, :, c] * (1.0 - mask) + bgr[c] * mask).astype(np.uint8)


def render_preview(
    target_path: str | Path,
    shapes: list[dict],
    output_path: str | Path,
    max_preview_size: int = 500,
) -> None:
    """Render *shapes* and save to *output_path* using OpenCV."""
    target_path = Path(target_path)
    output_path = Path(output_path)

    loaded = load_cv2()
    if not loaded:
        _copy_exe_preview(output_path.parent, output_path, max_preview_size)
        return

    _cv2, np = loaded

    if not shapes:
        return
    bg_data = shapes[0].get("data", [])
    if len(bg_data) >= 4:
        image_w, image_h = int(bg_data[2]), int(bg_data[3])
    else:
        img = _cv2.imread(str(target_path), _cv2.IMREAD_COLOR)
        if img is None:
            return
        image_h, image_w = img.shape[:2]

    canvas = np.zeros((image_h, image_w, 3), np.uint8)
    bg_color = shapes[0].get("color", [0, 0, 0, 255])
    bg_r, bg_g, bg_b, bg_a = bg_color[:4] if len(bg_color) >= 4 else (0, 0, 0, 255)
    if bg_a > 0:
        _cv2.rectangle(canvas, (0, 0), (image_w, image_h), (bg_b, bg_g, bg_r), thickness=-1)
    else:
        canvas[:, :] = (38, 38, 38)

    _draw_shapes_on_canvas(np, _cv2, canvas, shapes[1:])

    if max(image_w, image_h) > max_preview_size:
        ratio = max_preview_size / max(image_w, image_h)
        new_w, new_h = max(1, int(image_w * ratio)), max(1, int(image_h * ratio))
        canvas = _cv2.resize(canvas, (new_w, new_h), interpolation=_cv2.INTER_LANCZOS4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _cv2.imwrite(str(output_path), canvas)


def load_shapes_from_json(json_path: str | Path) -> list[dict]:
    """Load the ``shapes`` list from a geometry JSON file."""
    with open(json_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    return payload.get("shapes", [])
