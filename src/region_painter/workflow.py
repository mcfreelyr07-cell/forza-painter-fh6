"""Core orchestration for region-focused iterative painting.

Provides the high-level functions that the UI calls:
- ``run_first_pass`` — initial full-image generation.
- ``run_region_pass`` — resume + masked region generation.
- ``get_status`` / ``finalize`` — state queries and export.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image

from generator_backend import (
    GENERATOR_EXE,
    build_generator_env,
    parse_settings,
)
from region_painter.ini_manager import modify_ini
from region_painter.image_processor import apply_selection_mask
from region_painter.preview_renderer import load_shapes_from_json, render_preview
from region_painter.state_manager import StateManager

ProgressCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_first_pass(
    image_path: str | Path,
    settings_path: str | Path,
    first_layers: int,
    output_dir: str | Path,
    exe_path: str | Path = "",
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Execute the initial full-image generation pass.

    Returns ``{"ok": True, "state": {...}}`` on success, or
    ``{"ok": False, "error": str}`` on failure.
    """
    image_path = Path(image_path).resolve()
    settings_path = Path(settings_path).resolve()
    output_dir = Path(output_dir)
    exe = Path(exe_path) if exe_path else Path(str(GENERATOR_EXE))

    if not exe.exists():
        return {"ok": False, "error": f"Generator exe not found: {exe}"}

    # --- Parse settings ---
    values = parse_settings(settings_path)
    total_budget = int(values.get("stopAt", 3000))
    max_resolution = int(values.get("maxResolution", 1200))
    max_preview_size = int(values.get("maxPreviewSize", 500))
    first_layers = min(first_layers, total_budget)

    _progress(on_progress, f"Total budget: {total_budget}, first pass: {first_layers}")
    _progress(on_progress, f"Max resolution: {max_resolution}")

    # --- Prepare output directory ---
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_ini = output_dir / "temp.ini"
    base_json = output_dir / "base.json"
    preview_png = output_dir / "preview.png"
    target_png = output_dir / "target.png"

    # --- Resize input image to working resolution ---
    img = Image.open(image_path).convert("RGBA")
    orig_w, orig_h = img.size
    if max(orig_w, orig_h) > max_resolution:
        ratio = max_resolution / max(orig_w, orig_h)
        new_w = max(1, int(orig_w * ratio))
        new_h = max(1, int(orig_h * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        _progress(on_progress, f"Resized image: {orig_w}x{orig_h} → {new_w}x{new_h}")
    working_w, working_h = img.size
    img.save(target_png, "PNG")

    # --- Modify INI ---
    modify_ini(settings_path, temp_ini, stop_at=first_layers)
    _progress(on_progress, f"Temporary INI written to {temp_ini}")

    # --- Initialize state ---
    state = StateManager(output_dir)
    state.init_first_pass(
        original_image=str(image_path),
        original_ini=str(settings_path),
        total_budget=total_budget,
        working_width=working_w,
        working_height=working_h,
        max_resolution=max_resolution,
        max_preview_size=max_preview_size,
    )
    state.target_path = str(target_png)
    state.base_json = str(base_json)
    state.preview_path = str(preview_png)

    # --- Run exe ---
    cmd = [
        str(exe),
        str(target_png),
        "-settings", str(temp_ini),
        "-output", str(base_json.with_suffix("")),
        "-preview", str(preview_png.with_suffix("")),
    ]
    _progress(on_progress, f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=output_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=build_generator_env(),
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"Generator exe not found: {exe}"}
    except OSError as exc:
        return {"ok": False, "error": f"Failed to launch generator: {exc}"}

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        return {"ok": False, "error": f"Generator exited with code {result.returncode}: {stderr[:500]}"}

    _progress(on_progress, "Generator finished successfully.")

    # --- Parse results ---
    json_files = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        return {"ok": False, "error": "No JSON output found after generation."}

    actual_json = json_files[0]
    if actual_json != base_json:
        # The exe may append a number to the filename; rename to base.json.
        import shutil
        shutil.copy2(actual_json, base_json)

    shapes = load_shapes_from_json(base_json)
    layers = max(0, len(shapes) - 1)  # exclude background

    _progress(on_progress, f"Generated {layers} drawable layers.")

    # --- Render preview ---
    try:
        render_preview(target_png, shapes, preview_png, max_preview_size)
        _progress(on_progress, f"Preview saved to {preview_png}")
    except Exception as exc:
        _progress(on_progress, f"Preview render failed (non-fatal): {exc}")

    # --- Finalize state ---
    state.base_json = str(base_json)
    state.add_pass(mask_path=None, layers=layers, json_path=str(base_json))

    return {"ok": True, "state": state._data}


def run_region_pass(
    output_dir: str | Path,
    region_layers: int,
    selection_mask: Image.Image,
    exe_path: str | Path = "",
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Execute a region-focused generation pass.

    *selection_mask* must be a PIL ``'L'`` mode image at the same
    resolution as the working target.

    Returns ``{"ok": True, "new_total": int}`` on success, or
    ``{"ok": False, "error": str}`` on failure.
    """
    output_dir = Path(output_dir)
    exe = Path(exe_path) if exe_path else Path(str(GENERATOR_EXE))

    if not exe.exists():
        return {"ok": False, "error": f"Generator exe not found: {exe}"}

    # --- Load state ---
    state = StateManager(output_dir)
    if not state.is_first_pass_done:
        return {"ok": False, "error": "First pass has not been completed."}

    if region_layers > state.remaining_budget:
        region_layers = state.remaining_budget
        _progress(on_progress, f"Truncated region layers to remaining budget: {region_layers}")
    if region_layers <= 0:
        return {"ok": False, "error": "No remaining budget for region pass."}

    new_stop_at = state.used_layers + region_layers
    _progress(on_progress, f"Region pass: {region_layers} layers (stopAt={new_stop_at})")

    # --- Apply mask ---
    target_png = Path(state.target_path)
    region_target = output_dir / f"region_target_pass{len(state.passes) + 1}.png"
    try:
        apply_selection_mask(target_png, selection_mask, region_target, feather_radius=0)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to apply selection mask: {exc}"}
    _progress(on_progress, f"Masked target saved to {region_target}")

    # --- Save mask for record ---
    mask_png = output_dir / f"pass_{len(state.passes) + 1}_mask.png"
    selection_mask.save(mask_png, "PNG")

    # --- Modify INI ---
    settings_path = Path(state._data.get("original_ini", ""))
    temp_ini = output_dir / "temp.ini"
    if not settings_path.exists():
        return {"ok": False, "error": f"Original settings INI not found: {settings_path}"}
    modify_ini(settings_path, temp_ini, stop_at=new_stop_at)
    _progress(on_progress, f"Temporary INI written to {temp_ini}")

    # --- Run exe with -resume ---
    base_json = Path(state.base_json)
    cmd = [
        str(exe),
        str(region_target),
        "-resume", str(base_json),
        "-settings", str(temp_ini),
    ]
    _progress(on_progress, f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=output_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=build_generator_env(),
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"Generator exe not found: {exe}"}
    except OSError as exc:
        return {"ok": False, "error": f"Failed to launch generator: {exc}"}

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        return {"ok": False, "error": f"Generator exited with code {result.returncode}: {stderr[:500]}"}

    _progress(on_progress, "Region pass finished successfully.")

    # --- Parse results ---
    shapes = load_shapes_from_json(base_json)
    total_layers = max(0, len(shapes) - 1)
    new_layers = total_layers - state.used_layers
    _progress(on_progress, f"Total layers now: {total_layers} (+{new_layers} this pass)")

    # --- Render preview ---
    preview_png = Path(state.preview_path)
    try:
        render_preview(target_png, shapes, preview_png, state.max_preview_size)
        _progress(on_progress, f"Preview saved to {preview_png}")
    except Exception as exc:
        _progress(on_progress, f"Preview render failed (non-fatal): {exc}")

    # --- Update state ---
    state.add_pass(mask_path=str(mask_png), layers=new_layers, json_path=str(base_json))

    return {"ok": True, "new_total": total_layers}


def get_status(output_dir: str | Path) -> dict:
    """Return a summary of the current workflow state."""
    state = StateManager(output_dir)
    return {
        "total_budget": state.total_budget,
        "used_layers": state.used_layers,
        "remaining": state.remaining_budget,
        "passes": state.passes,
        "is_first_pass_done": state.is_first_pass_done,
    }


def finalize(output_dir: str | Path, dest_path: str | Path) -> dict:
    """Copy the final JSON to *dest_path* and return result."""
    output_dir = Path(output_dir)
    dest_path = Path(dest_path)

    state = StateManager(output_dir)
    base_json = Path(state.base_json)
    if not base_json.exists():
        return {"ok": False, "error": f"Base JSON not found: {base_json}"}

    import shutil

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_json, dest_path)

    return {"ok": True, "output": str(dest_path)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _progress(callback: ProgressCallback | None, message: str) -> None:
    if callback:
        callback(message)
