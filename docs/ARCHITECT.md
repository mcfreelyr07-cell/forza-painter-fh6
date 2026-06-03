# Region-Focused Iterative Painting — Architecture

> Architecture document for the Region Paint feature in Forza Painter FH6.
> Based on `docs/region-focused-painting-spec.md`. Last updated: 2026-06-03.

---

## 1. Overview

Adds a 5th "Region Paint" tab to the tkinter UI that implements staged geometry generation:

```
Total budget 2000 layers
  ├─ First pass: full-image 1000 layers → base.json
  ├─ Region A: resume + 300 layers → merged.json
  ├─ Region B: resume + 400 layers → merged.json
  └─ Region C: resume + 300 layers → final.json
```

Users select regions via Canvas-based tools (rectangle, ellipse, brush, polygon + feather). The exe is called with `-resume` and an alpha-masked target image — masked-out pixels get `opaqueMask=0` in the GPU engine, skipping them from error calculation, so new ellipses naturally concentrate on the selected region.

---

## 2. File Layout

```
src/region_painter/          ← new package
  __init__.py
  ini_manager.py             ← INI read/modify/write for staged generation
  state_manager.py           ← workflow state persistence (state.json)
  image_processor.py         ← apply selection mask to target image
  preview_renderer.py        ← pure Pillow CPU ellipse rendering
  workflow.py                ← orchestration: first-pass + region-pass + status

src/app.py                   ← modified: new tab, worker threads, queue handlers
src/i18n.py                  ← modified: ~30 new translation keys

runtime/region-painter/      ← runtime work directory (created on first use)
  {image_stem}/
    state.json
    target.png
    base.json
    pass_N_mask.png
    preview.png
    temp.ini
```

---

## 3. Core Modules

### 3.1 `ini_manager.py`

```
modify_ini(original_path, output_path, stop_at, save_at=None)
```

- Reads original INI, changes only `stopAt` and `saveAt`
- Filters `saveAt` values > `stopAt`
- All other fields preserved verbatim
- Parser: skip `#`/`;` comments, blank lines; `key = value` trimmed

### 3.2 `state_manager.py`

```python
class StateManager:
    def __init__(self, work_dir: str)
    def load() -> dict           # load state.json or return default
    def save() -> None           # persist to state.json
    def add_pass(mask_path, layers, json_path) -> None
    @property def remaining_budget() -> int
    @property def total_budget() -> int
    @property def used_layers() -> int
    @property def is_first_pass_done() -> bool
```

`state.json` schema:

```json
{
    "original_image": "/path/to/input.png",
    "original_ini": "/path/to/settings.ini",
    "total_budget": 2000,
    "used_layers": 800,
    "working_width": 1200,
    "working_height": 900,
    "max_resolution": 1200,
    "max_preview_size": 500,
    "base_json": "work/base.json",
    "target_path": "work/target.png",
    "preview_path": "work/preview.png",
    "passes": [
        {"mask": null, "layers": 500, "json": "work/base.json"},
        {"mask": "work/pass_2_mask.png", "layers": 300, "json": "work/merged.json"}
    ]
}
```

### 3.3 `image_processor.py`

```python
def apply_selection_mask(target_path, mask: Image.Image, output_path, feather_radius=0)
```

- Loads target RGBA PNG
- If `feather_radius > 0`: applies `GaussianBlur(radius)` to mask
- Multiplies mask into alpha: `new_alpha = original_alpha * (mask_pixel / 255)`
- Saves RGBA PNG

```python
def create_blank_mask(width, height) -> Image.Image
def mask_from_canvas_shapes(shapes, width, height, scale) -> Image.Image
```

`shapes` is `list[dict]` with `{"tool": str, "coords": [...]}`, rendered via `ImageDraw`.

### 3.4 `preview_renderer.py`

```python
def render_preview(target_path, shapes, output_path, max_preview_size=500)
```

Pure Pillow CPU rendering:
1. Load `target_path` as RGBA canvas
2. Skip `shapes[0]` (type 1 background)
3. For each type 16 ellipse, per spec §7 formula:
   - Bounding box clip: `[x-rx-1, x+rx+1] × [y-ry-1, y+ry+1]`
   - Pixel-center rotation test: `xr²/rx² + yr²/ry² ≤ 1.0`
   - Alpha blend: `dst = dst*(1-α) + color*α`
4. Resize to `max_preview_size`, save PNG

### 3.5 `workflow.py`

```python
ProgressCallback = Callable[[str], None]

def run_first_pass(image_path, settings_path, first_layers, output_dir,
                   exe_path=GENERATOR_EXE, on_progress=None) -> dict

def run_region_pass(output_dir, region_layers, selection_mask,
                    exe_path=GENERATOR_EXE, on_progress=None) -> dict

def get_status(output_dir) -> dict
def finalize(output_dir, dest_path) -> dict
```

**First pass**:
1. Parse original INI → `total_budget = stopAt`, `maxResolution`
2. Resize input to `maxResolution` if needed → save as `target.png`
3. `modify_ini(..., stopAt=first_layers)` → `temp.ini`
4. `subprocess.run([exe, input.png, -settings, temp.ini, -output, base, -preview, preview])`
5. Parse output JSON → `used_layers = len(shapes) - 1`
6. Write `state.json`

**Region pass**:
1. Load `state.json`, validate `remaining >= region_layers` (truncate if not)
2. `apply_selection_mask(target.png, mask, region_target.png)`
3. `modify_ini(..., stopAt=used+region)` → `temp.ini`
4. `subprocess.run([exe, region_target.png, -resume, base.json, -settings, temp.ini])`
5. `render_preview(target.png, shapes, preview.png)`
6. Update state: `used_layers = len(shapes) - 1`, append pass

Return format: `{"ok": bool, "state"/"new_total": int, "error": str}`.

---

## 4. Tab Layout (app.py)

```
┌──────────────────────────────────────────────────────────┐
│ [Generate JSON] [Import] [Export] [Tutorial] [Region Paint] │
├────────────────────────────┬─────────────────────────────┤
│ Left (scrollable, ~40%)    │ Right (Canvas, ~60%)         │
│                            │                              │
│ Step 1 — Image & Profile   │  ┌──────────────────────┐   │
│  [Image list] [Add] [Del]  │  │                      │   │
│  [Profile dropdown ▼]      │  │   Working image       │   │
│                            │  │   + red mask overlay  │   │
│ Step 2 — Budget            │  │                      │   │
│  Total: [____]             │  │   Mouse interactions: │   │
│  First pass: [____]        │  │   - Drag = rect/ell  │   │
│  Remaining: 500            │  │   - Motion = brush   │   │
│                            │  │   - Click = polygon  │   │
│ Step 3 — Selection         │  │                      │   │
│  [Rect][Ellipse][Brush]    │  └──────────────────────┘   │
│  [Polygon][Clear]          │                              │
│  Feather: [===o====] 5px   │  Preview after each pass:    │
│                            │  ┌──────────────────────┐   │
│ Step 4 — Actions           │  │  Rendered preview    │   │
│  [Start First Pass]        │  │  (Pillow CPU)        │   │
│  [Paint Region] [Stop]     │  └──────────────────────┘   │
│  Status: Running...        │                              │
│                            │                              │
│ Pass History               │                              │
│  #1 First pass — 500 layers│                              │
│  #2 Region — 300 layers    │                              │
└────────────────────────────┴─────────────────────────────┘
```

### Tab Construction

```python
self.region_paint_tab = Frame(self.tabs)
self.tabs.add(self.region_paint_tab, text=tr(self.lang, "region_paint_tab"))
self._build_region_paint_tab()
```

Follows the same pattern as `_build_generate_tab()`:
- Left panel: scrollable Canvas → Frame with `ttk.LabelFrame` sections
- Right panel: Canvas for image display + selection overlay + preview
- Uses `self._label()`, `self._button()`, `self.translated` helpers

---

## 5. Selection Tools (Canvas)

### Tool State

```python
self.region_tool = StringVar(value="rect")
self.region_shapes: list[dict] = []    # {"tool": "rect", "coords": [x1,y1,x2,y2]}
self.region_brush_size = IntVar(value=15)
self.region_feather = IntVar(value=0)
self.region_mask: Image.Image | None = None  # PIL 'L' at working resolution
```

### Canvas Bindings

| Tool | Button-1 | B1-Motion | ButtonRelease-1 | Motion |
|------|----------|-----------|-----------------|--------|
| Rectangle | Start drag (x1,y1) | Update rubber-band rect | Finalize, append shape | — |
| Ellipse | Start drag (x1,y1) | Update rubber-band oval | Finalize, append shape | — |
| Brush | Start stroke | Append line segment | Finalize, append shape | Show cursor |
| Polygon | Add vertex | — | — (double-click closes) | Show cursor |

### Coordinates

- Canvas displays image scaled to fit `max_canvas_size` (e.g., 500px)
- Scale factor: `scale = display_size / working_size`
- On mask generation: scale shape coords back to working resolution: `working_coord = canvas_coord / scale`
- Mask rendered at full working resolution via PIL `ImageDraw`

### Overlay Rendering

After each shape is finalized, redraw the red semi-transparent overlay:
1. Create a blank RGBA image at working resolution
2. For each shape in `self.region_shapes`, draw filled red (255,0,0,80) on the overlay
3. Scale overlay to display size
4. Composite onto the canvas image using `Image.alpha_composite()`
5. Update canvas with `PhotoImage`

---

## 6. Worker Threads & Queue

### Thread Pattern (follows existing `_generate_worker`)

```python
def _region_first_pass_worker(self, setting):
    # 1. Signal UI: buttons disabled, status "Running"
    # 2. Call workflow.run_first_pass(...) in subprocess
    # 3. Monitor subprocess stdout via reader thread
    # 4. Poll for preview files every 0.5s, JSON every 2s
    # 5. On completion: queue.put(("region_done", result))
    # 6. On error: queue.put(("region_status", "Failed"))
```

### New Queue Message Types

| Type | Payload | Handler |
|------|---------|---------|
| `"region_status"` | str | Update status label |
| `"region_log"` | str | Append to log widget |
| `"region_progress"` | str | Update progress label |
| `"region_preview"` | Path | Render preview image |
| `"region_done"` | dict | Re-enable buttons, update pass history, refresh preview |
| `"region_canvas_update"` | PIL Image | Update canvas display |

### Process Management

Reuses existing:
- `self.shutdown_event` — signal to stop
- `self._popen_registered()` — track process for cleanup
- `self._terminate_process()` — kill on stop
- `self.generation_lock` — prevent concurrent runs

---

## 7. i18n Keys

All keys added to `i18n.py` `TEXT["en"]` dict, with placeholder entries in other languages:

```
region_paint_tab           = "Region Paint"
region_step_image          = "Step 1 — Choose image & profile"
region_step_budget         = "Step 2 — Set layer budget"
region_step_selection      = "Step 3 — Select region to refine"
region_step_actions        = "Step 4 — Generate"
region_total_layers        = "Total budget"
region_first_pass_layers   = "First-pass layers"
region_region_layers       = "Region layers"
region_remaining           = "Remaining"
region_tool_rect           = "Rectangle"
region_tool_ellipse        = "Ellipse"
region_tool_brush          = "Brush"
region_tool_polygon        = "Polygon"
region_tool_clear          = "Clear mask"
region_brush_size          = "Brush size"
region_feather             = "Feather"
region_start_first_pass    = "Start First Pass"
region_paint_region        = "Paint Selected Region"
region_stop                = "Stop"
region_pass_history        = "Pass History"
region_no_image            = "Please add an image first."
region_no_mask             = "Please select a region first."
region_budget_exceeded     = "Not enough remaining layers ({remaining} left, need {needed})."
region_first_pass_done     = "First pass complete. {layers} layers used. Select a region to refine."
region_pass_done           = "Region pass complete. {layers} layers added, {remaining} remaining."
region_no_first_pass       = "Run the first pass before painting regions."
```

---

## 8. Dependencies

- **Pillow >= 10.0** — already in project (`requirements.txt`), used for image I/O + mask + preview rendering
- **No new dependencies** — all existing dependencies suffice

---

## 9. Exclusions

- No modification to Go exe (per spec §9)
- No JSON merger — exe resume outputs merged JSON directly
- No coordinate translation — mask approach preserves dimensions
- No modification to existing Generate/Import/Export/Tutorial tabs
- No undo/redo for selection tools (v1)
- No lasso, magic wand, or advanced selection tools (v1)
- No batch region processing (v1)

---

## 10. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `src/region_painter/` not project root | Consistent with existing `src/` layout |
| `runtime/region-painter/{stem}/` | Alongside existing `runtime/` folders |
| Own image list per tab | Region workflow is a different paradigm than batch generate |
| Pillow-only preview | Follows spec; avoids OpenCV optional dependency complexity |
| Canvas coords → scale → PIL mask | Natural for tkinter; single source of truth for selection state |
| Reuse existing `_popen_registered` | Proven process lifecycle management |
| Separate queue message types | Clean separation from generate/import/export messages |
