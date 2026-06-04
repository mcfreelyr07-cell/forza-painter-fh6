"""Core orchestration for region-focused iterative painting.

Setup-only functions that prepare files and return commands.
The actual subprocess management (Popen, stdout streaming, file polling)
happens in app.py worker threads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from PIL import Image

from generator_backend import GENERATOR_EXE, parse_settings
from region_painter.ini_manager import modify_ini
from region_painter.preview_renderer import (
    load_shapes_from_json,
    render_preview,
    render_shapes_to_array,
)
from region_painter.state_manager import StateManager

# Lazy-loaded via utils.load_cv2 in the composite path.
_np = None
_cv2 = None

ProgressCallback = Callable[[str], None]


def prepare_first_pass(
    image_path, settings_path, first_layers, output_dir,
    exe_path="", on_progress=None,
):
    """Prepare first pass. Returns dict with cmd, paths, state. Does NOT run exe."""
    image_path = Path(image_path).resolve()
    settings_path = Path(settings_path).resolve()
    output_dir = Path(output_dir)
    exe = Path(exe_path) if exe_path else Path(str(GENERATOR_EXE))
    if not exe.exists():
        return {"error": f"Generator exe not found: {exe}"}
    values = parse_settings(settings_path)
    total_budget = int(values.get("stopAt", 3000))
    max_resolution = int(values.get("maxResolution", 1200))
    max_preview_size = int(values.get("maxPreviewSize", 500))
    first_layers = min(first_layers, total_budget)
    _p(on_progress, f"Total budget: {total_budget}, first pass: {first_layers}")
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_ini = output_dir / "temp.ini"
    base_json = output_dir / "base.json"
    preview_png = output_dir / "preview.png"
    target_png = output_dir / "target.png"
    img = Image.open(image_path).convert("RGBA")
    orig_w, orig_h = img.size
    if max(orig_w, orig_h) > max_resolution:
        ratio = max_resolution / max(orig_w, orig_h)
        img = img.resize((max(1, int(orig_w * ratio)), max(1, int(orig_h * ratio))), Image.LANCZOS)
    working_w, working_h = img.size
    img.save(target_png, "PNG")
    modify_ini(settings_path, temp_ini, stop_at=first_layers)
    state = StateManager(output_dir)
    state.init_first_pass(
        original_image=str(image_path), original_ini=str(settings_path),
        total_budget=total_budget, working_width=working_w, working_height=working_h,
        max_resolution=max_resolution, max_preview_size=max_preview_size,
    )
    state.target_path = str(target_png)
    state.base_json = str(base_json)
    state.preview_path = str(preview_png)
    cmd = [str(exe), str(target_png), "-settings", str(temp_ini),
           "-output", str(base_json.with_suffix("")),
           "-preview", str(output_dir / "_exe_preview")]
    _p(on_progress, f"Command: {cmd[0]} ...")
    return {"cmd": cmd, "output_dir": str(output_dir), "target_png": str(target_png),
            "preview_png": str(preview_png), "base_json": str(base_json),
            "total_budget": total_budget, "max_preview_size": max_preview_size, "state": state}


def finalize_first_pass(prep):
    """Post-process after first-pass exe finishes."""
    output_dir = Path(prep["output_dir"])
    base_json = Path(prep["base_json"])
    target_png = Path(prep["target_png"])
    preview_png = Path(prep["preview_png"])
    max_preview_size = prep.get("max_preview_size", 500)
    state = prep["state"]
    json_files = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        return {"ok": False, "error": "No JSON output found after generation."}
    actual_json = json_files[0]
    if actual_json != base_json:
        import shutil
        shutil.copy2(actual_json, base_json)
    shapes = load_shapes_from_json(base_json)
    layers = max(0, len(shapes) - 1)
    # cv2 renderer (built-in exe-preview fallback)
    try:
        render_preview(target_png, shapes, preview_png, max_preview_size)
    except Exception:
        pass
    state.base_json = str(base_json)
    state.add_pass(mask_path=None, layers=layers, json_path=str(base_json))
    return {"ok": True, "layers": layers, "preview_png": str(preview_png)}


def prepare_region_pass(
    output_dir, region_layers, selection_mask,
    exe_path="", on_progress=None,
):
    """Prepare region pass. Returns dict with cmd, paths, state. Does NOT run exe."""
    output_dir = Path(output_dir)
    exe = Path(exe_path) if exe_path else Path(str(GENERATOR_EXE))
    if not exe.exists():
        return {"error": f"Generator exe not found: {exe}"}
    state = StateManager(output_dir)
    if not state.is_first_pass_done:
        return {"error": "First pass has not been completed."}
    if region_layers > state.remaining_budget:
        region_layers = state.remaining_budget
    if region_layers <= 0:
        return {"error": "No remaining budget for region pass."}
    # stopAt must be > len(shapes) for -resume to work (exe validates this).
    new_stop_at = state.used_layers + region_layers
    target_png = Path(state.target_path)
    pass_n = len(state.passes) + 1
    region_target = output_dir / f"region_target_pass{pass_n}.png"
    # --- Solution 3: composite target image ---
    # Render current accumulated shapes; non-selected region shows the
    # rendered state (error=0 for exe), selected region shows original
    # target (error≠0 → exe generates new shapes there).
    # This keeps opaqueMask uniform (all 1s) → occlusion culling works.
    base_json = Path(state.base_json)
    try:
        existing = load_shapes_from_json(base_json) if base_json.exists() else []
        rendered = render_shapes_to_array(existing)
        if rendered is None:
            raise RuntimeError("cv2/numpy unavailable")
        # Load original target as BGRA (preserve alpha for transparent pixels).
        from utils import load_cv2
        loaded = load_cv2()
        if not loaded:
            raise RuntimeError("cv2 unavailable")
        _cv2_mod, np_mod = loaded
        target_bgra = _cv2_mod.imread(str(target_png), _cv2_mod.IMREAD_UNCHANGED)
        if target_bgra is None:
            raise RuntimeError(f"Cannot read target: {target_png}")
        has_alpha = target_bgra.shape[2] == 4
        target_rgb = target_bgra[:, :, :3]
        target_a = target_bgra[:, :, 3] if has_alpha else np_mod.full(
            target_rgb.shape[:2], 255, dtype=np_mod.uint8,
        )
        h, w = target_rgb.shape[:2]
        # Convert PIL 'L' mask to numpy, resize to match target dimensions.
        mask_pil = selection_mask.resize((w, h), Image.NEAREST)
        mask_np = np_mod.array(mask_pil, dtype=np_mod.float32) / 255.0
        mask_np = np_mod.clip(mask_np, 0.0, 1.0)
        mask_3ch = np_mod.stack([mask_np, mask_np, mask_np], axis=-1)
        # Composite RGB: mask → target; 1-mask → rendered current.
        composite_rgb = (target_rgb.astype(np_mod.float32) * mask_3ch +
                         rendered.astype(np_mod.float32) * (1.0 - mask_3ch))
        composite_rgb = composite_rgb.astype(np_mod.uint8)
        # Alpha: use target's original alpha (transparent stays transparent).
        composite = np_mod.dstack([composite_rgb, target_a])
        _cv2_mod.imwrite(str(region_target), composite)
    except Exception as exc:
        return {"error": f"Failed to build composite target: {exc}"}
    mask_png = output_dir / f"pass_{pass_n}_mask.png"
    selection_mask.save(mask_png, "PNG")
    settings_path = Path(state._data.get("original_ini", ""))
    temp_ini = output_dir / "temp.ini"
    if not settings_path.exists():
        return {"error": f"Original settings INI not found: {settings_path}"}
    # Filter saveAt to only include values >= used_layers so the exe
    # does not emit spurious checkpoints during occlusion-culling
    # compaction (where the shape count temporarily drops).
    settings_values = parse_settings(settings_path)
    orig_save_at_str = settings_values.get("saveAt", "")
    orig_save_at = []
    for p in orig_save_at_str.split(","):
        try:
            orig_save_at.append(int(p.strip()))
        except ValueError:
            pass
    used = state.used_layers
    filtered_save_at = [v for v in orig_save_at if v >= used]
    modify_ini(settings_path, temp_ini, stop_at=new_stop_at, save_at=filtered_save_at)
    base_json = Path(state.base_json)
    # Back up the accumulated shapes before the exe runs (exe may overwrite base_json).
    backup_json = output_dir / "_base_backup.json"
    if base_json.exists():
        import shutil
        shutil.copy2(base_json, backup_json)
    else:
        backup_json.write_text('{"shapes":[]}', encoding="utf-8")

    cmd = [str(exe), str(region_target), "-resume", str(base_json),
           "-settings", str(temp_ini),
           "-preview", str(output_dir / "_exe_preview")]
    _p(on_progress, f"Region pass: {region_layers} layers (stopAt={new_stop_at}, remaining={state.remaining_budget})")
    return {"cmd": cmd, "output_dir": str(output_dir), "target_png": str(target_png),
            "preview_png": state.preview_path, "base_json": str(base_json),
            "backup_json": str(backup_json),
            "mask_png": str(mask_png), "new_stop_at": new_stop_at,
            "region_layers": region_layers, "state": state,
            "region_target_stem": region_target.stem,
            "max_preview_size": state.max_preview_size}


def finalize_region_pass(prep):
    """Post-process after region-pass exe finishes.

    Without ``-output`` the exe writes accumulated shapes (old + new)
    to a JSON named after the input image.  We use that output directly
    — no merge with the backup is needed.
    """
    import json

    state = prep["state"]
    output_dir = Path(prep["output_dir"])
    base_json = Path(prep["base_json"])
    backup_json = Path(prep["backup_json"])
    target_png = Path(prep["target_png"])
    preview_png = Path(prep["preview_png"])
    mask_png = prep.get("mask_png", "")
    max_preview_size = prep.get("max_preview_size", 500)
    region_target_stem = prep.get("region_target_stem", "")
    region_layers = prep.get("region_layers", 0)

    # Count old shapes from backup for accurate new_layers calculation.
    old_shapes = load_shapes_from_json(backup_json) if backup_json.exists() else []
    old_type16 = sum(1 for s in old_shapes if s.get("type") == 16)

    # Find the exe's output (accumulated shapes: old + new).
    accumulated: list[dict] = []
    if region_target_stem:
        for c in sorted(
            output_dir.glob(f"{region_target_stem}*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        ):
            if c == backup_json:
                continue
            try:
                accumulated = load_shapes_from_json(c)
                break
            except Exception:
                pass

    if not accumulated:
        accumulated = old_shapes  # fallback

    # Exe output already has all shapes — use it directly.
    new_type16 = sum(1 for s in accumulated if s.get("type") == 16)
    new_layers = max(0, new_type16 - old_type16)
    if new_layers == 0:
        new_layers = region_layers  # safety floor

    # Save accumulated result.
    base_json.write_text(
        json.dumps({"shapes": accumulated}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Render preview — cv2 renderer (built-in exe-preview fallback)
    try:
        render_preview(target_png, accumulated, preview_png, max_preview_size)
    except Exception:
        pass

    state.add_pass(mask_path=str(mask_png), layers=new_layers, json_path=str(base_json))

    # Clean up backup.
    try:
        backup_json.unlink()
    except OSError:
        pass

    return {"ok": True, "new_total": new_type16, "preview_png": str(preview_png)}


def get_status(output_dir):
    """Return a summary of the current workflow state."""
    state = StateManager(output_dir)
    return {
        "total_budget": state.total_budget,
        "used_layers": state.used_layers,
        "remaining": state.remaining_budget,
        "passes": state.passes,
        "is_first_pass_done": state.is_first_pass_done,
    }


def finalize(output_dir, dest_path):
    """Copy the final JSON to dest_path."""
    import shutil
    output_dir = Path(output_dir)
    dest_path = Path(dest_path)
    state = StateManager(output_dir)
    base_json = Path(state.base_json)
    if not base_json.exists():
        return {"ok": False, "error": f"Base JSON not found: {base_json}"}
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_json, dest_path)
    return {"ok": True, "output": str(dest_path)}


def _p(callback, msg):
    if callback:
        callback(msg)
