from __future__ import annotations

import os
import cv2
import numpy as np
from pathlib import Path

from utils import PreprocessError


def _downscale_if_needed(bgra: np.ndarray, max_resolution: int | None) -> np.ndarray:
    if max_resolution is None:
        return bgra
    h, w = bgra.shape[:2]
    longest = max(h, w)
    if longest <= max_resolution:
        return bgra
    scale = max_resolution / longest
    new_size = (int(w * scale), int(h * scale))
    return cv2.resize(bgra, new_size, interpolation=cv2.INTER_AREA)


def luma_band(image_path: str | Path, max_resolution: int | None = None) -> Path:
    """Apply luminance banding preprocessing and write result atomically.

    If *max_resolution* is specified and the input image's longest edge
    exceeds that value, the image is downscaled first so that the
    luminance-banding pass runs at the same resolution the generator will
    ultimately use — saving CPU time and disk I/O with no quality impact.

    Returns the path to the preprocessed output file.
    """
    image_path = Path(image_path)
    bgra = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if bgra is None:
        raise PreprocessError(f"failed to read image: {image_path}")

    bgra = _downscale_if_needed(bgra, max_resolution)
    result = _apply_preprocess(bgra)
    output_path = image_path.with_name(f"{image_path.stem}.luma_band{image_path.suffix}")

    # Atomic write: write to a temp file first, then rename.
    # This avoids leaving a partially-written file if the process crashes mid-write.
    tmp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    ok = cv2.imwrite(str(tmp_path), result)
    if not ok:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise PreprocessError(f"failed to write preprocessed image: {output_path}")

    try:
        os.replace(str(tmp_path), str(output_path))
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise PreprocessError(f"failed to finalize preprocessed image: {output_path}") from exc

    return output_path


def _apply_preprocess(bgra: np.ndarray) -> np.ndarray:
    if bgra.ndim != 3:
        raise PreprocessError(f"expected 3D image array, got shape {bgra.shape}")

    channels = bgra.shape[2]
    if channels not in (3, 4):
        raise PreprocessError(f"expected 3 or 4 channels, got {channels}")

    has_alpha = channels == 4

    # Attempt GPU-accelerated path via OpenCV UMat if OpenCL is available.
    try:
        if cv2.ocl.haveOpenCL():
            return _apply_preprocess_ocl(bgra, has_alpha, channels)
    except Exception:
        pass

    return _apply_preprocess_cpu(bgra, has_alpha)


def _apply_preprocess_ocl(bgra: np.ndarray, has_alpha: bool, channels: int) -> np.ndarray:
    """OpenCL-accelerated path via cv2.UMat — keeps color conversion on GPU."""
    cv2.ocl.setUseOpenCL(True)

    bgr = np.clip(bgra[..., :3], 0, 255).astype(np.uint8)
    alpha = np.clip(bgra[..., 3], 0, 255).astype(np.uint8) if has_alpha else None

    # Upload BGR to GPU
    bgr_u = cv2.UMat(bgr)
    lab_u = cv2.cvtColor(bgr_u, cv2.COLOR_BGR2LAB)

    # Download only L channel for NumPy arithmetic (no OCL equivalent for np.floor)
    lab_cpu = lab_u.get()
    lum = lab_cpu[..., 0].astype(np.float32)

    levels = 24.0
    step = 256.0 / levels
    lq = np.floor(lum / step) * step + step * 0.5
    l_out = lq * 0.82 + lum * 0.18
    l_mid = 128.0
    l_out = (l_out - l_mid) * 1.06 + l_mid

    lab_cpu[..., 0] = np.clip(l_out, 0, 255).astype(np.uint8)

    # Re-upload modified LAB to GPU for the inverse color conversion
    lab_mod = cv2.UMat(lab_cpu)
    bgr_out_u = cv2.cvtColor(lab_mod, cv2.COLOR_LAB2BGR)
    bgr_out = bgr_out_u.get()

    if has_alpha:
        return np.dstack([bgr_out, alpha]).astype(np.uint8)
    return bgr_out.astype(np.uint8)


def _apply_preprocess_cpu(bgra: np.ndarray, has_alpha: bool) -> np.ndarray:
    bgr = np.clip(bgra[..., :3], 0, 255).astype(np.uint8)
    if has_alpha:
        alpha = np.clip(bgra[..., 3], 0, 255).astype(np.uint8)

    # cv2.imread returns BGR, so we convert BGR->LAB, not RGB->LAB.
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lum = lab[..., 0].astype(np.float32)
    levels = 24.0  # TODO make this a setting
    step = 256.0 / levels
    lq = np.floor(lum / step) * step + step * 0.5
    # Keep the band separation, but blend some original luminance back in
    # so the result stays closer to the source and avoids overly harsh steps.
    l_out = lq * 0.82 + lum * 0.18
    # Restore a touch of local contrast so the pass doesn't feel slightly washed.
    l_mid = 128.0
    l_out = (l_out - l_mid) * 1.06 + l_mid
    lab[..., 0] = np.clip(l_out, 0, 255).astype(np.uint8)
    bgr_out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if has_alpha:
        out = np.dstack([bgr_out, alpha]).astype(np.uint8)
    else:
        out = bgr_out.astype(np.uint8)
    return out
