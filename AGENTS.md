# Fork-specific performance enhancements

This fork contains several Python-side performance improvements over the
upstream repo (`bvzrays/forza-painter-fh6`). These are **not** present
upstream and must not be reverted when merging future upstream changes.

## Enhancements by file

### `src/generator_backend.py`
- `"backend"` key in `SETTING_KEYS` — allows configuring Vulkan/OpenCL
  backend for the Go generator binary via `-backend` flag
- `max_resolution` passed to `luma_band()` for pre-downscaling

### `src/preprocess/luma.py`
- **OpenCL GPU path** (`_apply_preprocess_ocl`) — uses `cv2.UMat` to run
  BGR↔LAB color conversions on GPU when OpenCL is available
- **CPU path** (`_apply_preprocess_cpu`) — extracted as separate function
- **Downscale** (`_downscale_if_needed`) — pre-scales to `max_resolution`
  to save CPU time

### `src/utils.py`
- `load_numpy()` — standalone lazy NumPy loader (upstream only has
  `load_cv2` and `load_pillow`)

### `src/app.py`
- **Parallel multi-image generation** — uses `ThreadPoolExecutor` with
  `MAX_CONCURRENT_GENERATORS` (upstream is sequential, one image at a time)
- `active_generator_procs` set for tracking concurrent processes
- Threaded output reader pattern (`_read_gen_output`/`_drain_gen_output`)
- `_log_generation_load_warning()` — warns about VRAM limits when running
  high quality + concurrent generation

### `src/fh6_probe.py`
- **Parallel memory scanning** — uses `ThreadPoolExecutor` with cancel
  events for RTTI and layout-count locator strategies (upstream is
  sequential)
- Per-region worker functions with chunked reading and candidate limits

### `src/geometry_json.py`
- **LRU cache** — `_load_normalized_geometry_cached` with
  `@functools.lru_cache(maxsize=128)` keyed by path+mtime+size
  (upstream has no caching)

### `src/region_painter/preview_renderer.py`
- `on_progress` callback in `render_preview_high_quality()` reports
  rendering progress every 100 shapes

### `src/region_painter/workflow.py`
- `on_progress` passthrough in `finalize_first_pass()` and
  `finalize_region_pass()` for preview rendering progress

## Custom config files
- `config/settings/g. enthusiast - high-end hardware.ini`
- `config/settings/h. enthusiast balance.ini`
- `config/settings/i. 2500-herta-wink-128.ini`
- `config/settings/j. 2500-herta-wink-256.ini`
