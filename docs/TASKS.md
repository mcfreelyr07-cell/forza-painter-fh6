# Region-Focused Iterative Painting — Task List

> Implementation checklist. Check off each item as completed.
> Reference: `docs/region-focused-painting-spec.md` and `docs/ARCHITECT.md`.

---

## Phase 1: Core Package (`src/region_painter/`)

### 1.1 — Package scaffolding
- [x] Create `src/region_painter/__init__.py` (empty or with package docstring)

### 1.2 — `ini_manager.py`
- [x] Implement `modify_ini(original_path, output_path, stop_at, save_at=None)`
- [x] Parse: skip `#`/`;` comments, blank lines; trim `key = value`
- [x] Modify `stopAt` and `saveAt`; filter `saveAt` values > `stopAt`
- [x] Preserve all other fields verbatim
- [x] Write output to temp file path

### 1.3 — `state_manager.py`
- [x] Implement `StateManager` class
- [x] `__init__(work_dir)` — set work directory, create if not exists
- [x] `load()` — load `state.json` or return default empty state
- [x] `save()` — persist to `state.json`
- [x] `add_pass(mask_path, layers, json_path)` — append pass, update `used_layers`
- [x] Properties: `remaining_budget`, `total_budget`, `used_layers`, `is_first_pass_done`
- [x] `reset()` — clear all state for a fresh workflow

### 1.4 — `image_processor.py`
- [x] Implement `create_blank_mask(width, height)` → PIL 'L' mode
- [x] Implement `mask_from_canvas_shapes(shapes, width, height, scale=1.0)` → PIL 'L' mask
  - [x] Rectangle: `ImageDraw.rectangle(coords, fill=255)`
  - [x] Ellipse: `ImageDraw.ellipse(coords, fill=255)`
  - [x] Brush: `ImageDraw.line(points, fill=255, width=brush_size)`
  - [x] Polygon: `ImageDraw.polygon(points, fill=255)`
- [x] Implement `apply_selection_mask(target_path, mask, output_path, feather_radius=0)`
  - [x] Load target RGBA
  - [x] Optional `GaussianBlur(radius)` on mask
  - [x] `new_alpha = original_alpha * (mask / 255)`
  - [x] Save RGBA PNG

### 1.5 — `preview_renderer.py`
- [x] Implement `render_preview(target_path, shapes, output_path, max_preview_size=500)`
- [x] Load target as RGBA canvas
- [x] Skip `shapes[0]` (type 1 background)
- [x] For each type 16 ellipse:
  - [x] Parse `data=[x, y, rx, ry, theta]`, `color=[r, g, b, a]`
  - [x] Compute bounding box: `[x-rx-1, x+rx+1] × [y-ry-1, y+ry+1]`
  - [x] For each pixel in bbox: rotate test `xr²/rx² + yr²/ry² ≤ 1.0`
  - [x] Alpha blend: `dst = dst*(1-α) + color*α`
- [x] Resize to `max_preview_size` maintaining aspect ratio
- [x] Save PNG

### 1.6 — `workflow.py`
- [x] Implement `run_first_pass(image_path, settings_path, first_layers, output_dir, exe_path, on_progress)`
  - [x] Parse original INI → `total_budget`, `maxResolution`
  - [x] Resize input to `maxResolution` if needed → save `target.png`
  - [x] `modify_ini(..., stopAt=first_layers)` → `temp.ini`
  - [x] `subprocess.run([exe, input, -settings, temp.ini, -output, base, -preview, preview])`
  - [x] Parse output JSON → count shapes
  - [x] Write `state.json`
  - [x] Return `{"ok": True, "state": {...}}` or `{"ok": False, "error": str}`
- [x] Implement `run_region_pass(output_dir, region_layers, selection_mask, exe_path, on_progress)`
  - [x] Load state, validate budget
  - [x] `apply_selection_mask(target.png, mask, region_target.png)`
  - [x] `modify_ini(..., stopAt=used+region)` → `temp.ini`
  - [x] `subprocess.run([exe, region_target.png, -resume, base.json, -settings, temp.ini])`
  - [x] `render_preview(target.png, shapes, preview.png)`
  - [x] Update state: `used_layers`, append pass
  - [x] Return `{"ok": True, "new_total": int}` or `{"ok": False, "error": str}`
- [x] Implement `get_status(output_dir)` → dict
- [x] Implement `finalize(output_dir, dest_path)` → copy final JSON, return dict
- [x] Progress callback: call `on_progress(msg)` at each major step

---

## Phase 2: New Tab in `app.py`

### 2.1 — Tab registration
- [x] Add `self.region_paint_tab = Frame(self.tabs)` in `_build()` (alongside other tabs)
- [x] Add tab to notebook: `self.tabs.add(self.region_paint_tab, text=tr(self.lang, "region_paint_tab"))`
- [x] Call `self._build_region_paint_tab()`

### 2.2 — Tab layout: Left panel controls
- [x] Create scrollable left panel (Canvas + Scrollbar pattern, same as Generate tab)
- [x] **Step 1 — Image & Profile** (`ttk.LabelFrame`)
  - [x] Region image listbox (`self.region_image_list`)
  - [x] Add Image / Remove Image buttons
  - [x] Profile dropdown (reuse `self.settings` data, new `self.region_profile_combo`)
- [x] **Step 2 — Budget** (`ttk.LabelFrame`)
  - [x] Total budget Entry (`self.region_total_var`)
  - [x] First-pass layers Entry (`self.region_first_var`)
  - [x] Region layers Entry (`self.region_layers_var`)
  - [x] Remaining layers Label (read-only, updates dynamically)
- [x] **Step 3 — Selection Tools** (`ttk.LabelFrame`)
  - [x] Tool buttons: Rectangle, Ellipse, Brush, Polygon (radio-style via StringVar)
  - [x] Clear mask button
  - [x] Brush size slider (5-50px, shown when brush selected)
  - [x] Feather slider (0-20px)
- [x] **Step 4 — Actions** (`ttk.LabelFrame`)
  - [x] Start First Pass button
  - [x] Paint Region button (disabled until first pass done)
  - [x] Stop button
  - [x] Status label
  - [x] Progress label
- [x] **Pass History** (`ttk.LabelFrame`)
  - [x] Listbox showing passes: `#1 First pass — 500 layers`, `#2 Region — 300 layers`
  - [x] Clear history / reset button

### 2.3 — Tab layout: Right panel (Canvas)
- [x] Create right-side Frame with Canvas widget
- [x] Canvas displays:
  - [x] Working image (scaled to fit)
  - [x] Red semi-transparent mask overlay (updated on each shape change)
  - [x] Rubber-band preview during drag operations
- [x] After each pass: show rendered preview image (from `preview_renderer`)
- [x] Image display: load with Pillow → `ImageTk.PhotoImage` → Canvas `create_image`

### 2.4 — Canvas mouse handlers
- [x] Implement `_region_canvas_press(event)` — start drag / add vertex / start brush
- [x] Implement `_region_canvas_drag(event)` — update rubber-band / append brush segment
- [x] Implement `_region_canvas_release(event)` — finalize shape, update shapes list, redraw overlay
- [x] Implement `_region_canvas_motion(event)` — cursor preview for brush/polygon
- [x] Implement `_region_canvas_double_click(event)` — close polygon
- [x] Implement `_region_redraw_overlay()` — composite all shapes as red overlay
- [x] Implement `_region_get_canvas_scale()` — compute display-to-working ratio
- [x] Implement `_region_generate_mask()` — convert `self.region_shapes` → PIL 'L' mask at working resolution

### 2.5 — Worker threads
- [x] Implement `_region_first_pass_start()` — validate inputs, disable UI, spawn thread
- [x] Implement `_region_first_pass_worker(setting)` — calls `workflow.run_first_pass()`
  - [x] Subprocess management via `_popen_registered`
  - [x] stdout reader thread for log output
  - [x] File polling for preview updates
  - [x] Queue messages: `region_log`, `region_status`, `region_progress`, `region_preview`, `region_done`
  - [x] Graceful stop via `shutdown_event`
- [x] Implement `_region_pass_start()` — generate mask, validate, spawn thread
- [x] Implement `_region_pass_worker(region_layers, mask)` — calls `workflow.run_region_pass()`
  - [x] Same subprocess/reader/polling pattern
  - [x] Post-completion: render preview, update pass history
- [x] Implement `_region_stop()` — set `shutdown_event`, terminate process

### 2.6 — Queue handler extensions
- [x] Add `"region_status"` → update region status label
- [x] Add `"region_log"` → append to existing log widget
- [x] Add `"region_progress"` → update region progress label
- [x] Add `"region_preview"` → load and display preview image on canvas
- [x] Add `"region_done"` → re-enable buttons, update pass history, refresh canvas
- [x] Add `"region_canvas_update"` → update canvas image display

### 2.7 — UI state management
- [x] `_region_update_button_states()` — enable/disable based on current state
  - [x] No image → all generate buttons disabled
  - [x] First pass not done → Paint Region disabled
  - [x] No mask → Paint Region disabled
  - [x] Budget exhausted → Paint Region disabled with message
  - [x] Running → Start/Paint disabled, Stop enabled
- [x] `_region_update_remaining_label()` — update remaining budget display
- [x] `_region_refresh_pass_history()` — rebuild pass history listbox

---

## Phase 3: i18n (`src/i18n.py`)

- [x] Add all new keys to `TEXT["en"]` dictionary (see ARCHITECT.md §7 for full list)
- [x] Add placeholder entries (English values) in `TEXT["pt-br"]`
- [x] Add placeholder entries in `TEXT["zh"]`
- [x] Add placeholder entries in `TEXT["zh-tw"]`
- [x] Add placeholder entries in `TEXT["ko"]`
- [x] Add placeholder entries in `TEXT["es"]`

---

## Phase 4: Integration & Polish

- [ ] Verify generated JSON from region workflow is importable via existing Import tab
- [ ] Test: first pass → generate preview → region pass → generate preview → compare
- [ ] Test: stop during first pass → state preserved → can restart
- [ ] Test: stop during region pass → state preserved → base JSON intact
- [ ] Test: budget exhausted → region pass blocked with clear message
- [ ] Test: no image selected → buttons disabled gracefully
- [ ] Test: feather = 0 (hard edge) vs feather = 20 (soft transition)
- [ ] Test: all 4 selection tools produce correct masks
- [ ] Test: pass history correctly reflects all passes
- [ ] Test: language switching updates all new tab labels
- [ ] Test: window resize → canvas scales correctly
- [ ] Test: dark theme consistency with existing tabs

---

## Phase 5: Documentation

- [ ] Update `CHANGELOG.md` with new feature entry
- [ ] Update `README.md` if needed (mention Region Paint tab)
