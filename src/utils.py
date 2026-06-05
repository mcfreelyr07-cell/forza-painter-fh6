from __future__ import annotations

import importlib
from typing import Any, Tuple


class PreprocessError(Exception):
    """Raised when image preprocessing fails."""


class MemoryWriteError(Exception):
    """Raised when writing game process memory fails."""


class ProcessNotFoundError(Exception):
    """Raised when the target game process cannot be found."""


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def parse_int(value: Any) -> int | None:
    """Parse a string/int/float into an int, supporting 0x/0b/0o prefixes.

    Returns None for None or empty string.
    """
    if value is None or value == "":
        return None
    return int(str(value), 0)


def clamp_byte(value: float) -> int:
    """Clamp a float to the range [0, 255] and round to nearest int."""
    return max(0, min(255, int(round(value))))


# ---------------------------------------------------------------------------
# Lazy optional dependency loaders (moved here from app.py / main.py)
# ---------------------------------------------------------------------------

def load_cv2() -> Tuple[Any, Any] | None:
    """Lazy-load OpenCV and NumPy, caching the result.

    Returns a tuple (cv2_module, numpy_module) or None on failure.
    """
    if not hasattr(load_cv2, "_cache"):
        load_cv2._cache = None  # type: ignore[attr-defined]
        load_cv2._error = None  # type: ignore[attr-defined]
    if load_cv2._cache is not None:  # type: ignore[attr-defined]
        return load_cv2._cache  # type: ignore[attr-defined]
    if load_cv2._error is not None:  # type: ignore[attr-defined]
        return None
    try:
        cv2 = importlib.import_module("cv2")
        np = importlib.import_module("numpy")
        load_cv2._cache = (cv2, np)  # type: ignore[attr-defined]
        return load_cv2._cache  # type: ignore[attr-defined]
    except Exception as exc:
        load_cv2._error = exc  # type: ignore[attr-defined]
        return None


def load_pillow() -> Tuple[Any, Any] | None:
    """Lazy-load Pillow Image and ImageDraw, caching the result.

    Returns a tuple (Image, ImageDraw) or None on failure.
    """
    if not hasattr(load_pillow, "_cache"):
        load_pillow._cache = None  # type: ignore[attr-defined]
        load_pillow._error = None  # type: ignore[attr-defined]
    if load_pillow._cache is not None:  # type: ignore[attr-defined]
        return load_pillow._cache  # type: ignore[attr-defined]
    if load_pillow._error is not None:  # type: ignore[attr-defined]
        return None
    try:
        Image = importlib.import_module("PIL.Image")
        ImageDraw = importlib.import_module("PIL.ImageDraw")
        load_pillow._cache = (Image, ImageDraw)  # type: ignore[attr-defined]
        return load_pillow._cache  # type: ignore[attr-defined]
    except Exception as exc:
        load_pillow._error = exc  # type: ignore[attr-defined]
        return None


def load_numpy():
    """Lazy-load NumPy, caching the result.

    Returns the numpy module or None on failure.
    """
    if not hasattr(load_numpy, "_cache"):
        load_numpy._cache = None  # type: ignore[attr-defined]
        load_numpy._error = None  # type: ignore[attr-defined]
    if load_numpy._cache is not None:  # type: ignore[attr-defined]
        return load_numpy._cache  # type: ignore[attr-defined]
    if load_numpy._error is not None:  # type: ignore[attr-defined]
        return None
    try:
        np_mod = importlib.import_module("numpy")
        load_numpy._cache = np_mod  # type: ignore[attr-defined]
        return load_numpy._cache  # type: ignore[attr-defined]
    except Exception as exc:
        load_numpy._error = exc  # type: ignore[attr-defined]
        return None
