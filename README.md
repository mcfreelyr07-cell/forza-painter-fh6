<p align="center">
  <img src="https://github.com/user-attachments/assets/d4f48f71-d76e-4ffe-9fb1-0b075d79bf05" alt="forza-painter FH6 logo" width="720">
</p>

<h1 align="center">forza-painter FH6</h1>

<p align="center">
  <strong>Image to Forza Horizon 6 Vinyl Group generator and importer.</strong>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">中文</a>
</p>

<p align="center">
  <code>v1.4.0</code> · <code>Windows</code> · <code>Forza Horizon 6</code> · <code>GPU/OpenCL</code>
</p>

Generate Forza Horizon 6 Vinyl Group layers from PNG/JPG/BMP images. The desktop app handles generation, preview, and import in one place; normal users do not need to type memory addresses.

> **If the result looks blurry:** raise `Random samples` first. Values above **200000** usually make a major quality difference; higher values are clearer but take much longer to generate.

| What it does | Details |
| --- | --- |
| Generate JSON | Convert images into geometry JSON with the bundled GPU/OpenCL generator. |
| Preview output | Show source and generated geometry previews inside the app. |
| Import to FH6 | Import JSON into the currently open FH6 Vinyl Group Editor. |
| Safe FH6 workflow | Auto-locate and verify the current editable layer table before writing. |

## Resources

- Import walkthrough video: https://www.bilibili.com/video/BV1hG5Z6nENZ
- Bundled GPU generator source/reference: https://github.com/zjl88858/forza-painter-geometrize-gpu

## Preview

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/app-import-preview.png" alt="App import page"><br>
      <strong>App import page</strong>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/fh6-template-ready.png" alt="FH6 template ready"><br>
      <strong>Template ready in FH6</strong>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/fh6-import-result.png" alt="FH6 import result"><br>
      <strong>Imported result</strong>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/fh6-car-applied.png" alt="FH6 car applied result"><br>
      <strong>Applied to car</strong>
    </td>
  </tr>
</table>

## Quick Start

1. Download this repository as a ZIP and extract it.
2. Install 64-bit Python. Python 3.12 is recommended.
3. Double-click `install_dependencies.bat`.
4. Double-click `start_app.bat`.
5. In FH6, open Vinyl Group Editor, load a sphere template, then Ungroup it.
6. Generate JSON in the app, open the Import page, enter the template layer count, then import.

## Setup

Most users only need to run:

```text
install_dependencies.bat
start_app.bat
```

If the app does not start, run:

```text
check_environment.bat
```

The core Python app only needs `psutil` and `pywin32`. Image/JSON preview uses optional NumPy/OpenCV dependencies; the installer may skip them on Python versions where preview packages are likely to conflict.

## Generate JSON

1. Open the `Generate JSON` page.
2. Click `Add images` and choose PNG/JPG/BMP images.
3. Select a quality preset.
4. Optional: enable `Use custom settings` to change output layers, resolution, random samples, and mutated samples in the app.
5. Click the fixed bottom `Start generating` button.
6. Wait for the preview and logs to update.

Generated files are saved beside the source image, for example:

```text
image.500.json
image.1000.json
image.3000.json
```

One image can generate multiple checkpoint JSON files. Prefer the highest-layer JSON that matches your template; for example, use `image.3000.json` or the final `image.json` with a 3000-layer template. Importing a 500-layer JSON into a 3000-layer template will look blurry.

Current preset differences:

| Preset | Output layers | Random samples | Use case |
| --- | ---: | ---: | --- |
| extremely fast | 500 | 30000 | Quick composition checks |
| fast | 1000 | 60000 | Quick usable drafts |
| balanced | 1800 | 120000 | Recommended default |
| slow | 2500 | 220000 | Final quality; starts using the 200k+ quality range |
| super slow | 3000 | 350000 | Best clarity, very slow |

## Quality And Custom Settings

Later presets are usually slower and cleaner.

- `extremely fast`: quick composition tests.
- `fast`: quick usable output.
- `balanced`: recommended default.
- `slow`: higher quality and 200k+ random samples.
- `super slow`: slowest bundled preset for final output.

Custom settings only affect the current run. Common fields:

- `Output layers`: maximum layer count.
- `Max resolution`: maximum processing resolution.
- `Random samples`: more candidates, slower generation.
- `Mutated samples`: more optimization, slower generation.
- `Save checkpoints`: JSON checkpoints to save, for example `500,1000,1500,3000`.

## Prepare FH6

1. Start Forza Horizon 6.
2. Open `Create Vinyl Group` / `Vinyl Group Editor`.
3. Load a template made from many simple sphere layers.
4. `Ungroup` the template.
5. Remember the exact layer count shown in game.
6. Keep this editor open while importing.

Recommended template size: 500 to 3000 layers.

## Import JSON

1. Open the `Import` page.
2. Click `Refresh` and select the running `forzahorizon6.exe`.
3. Enter the current in-game template layer count.
4. Add the generated `.json`, or click `Use generated JSON`.
5. Leave advanced address fields empty.
6. Click `Import JSON`.

The app locates and verifies the current FH6 layer table before writing. If the target cannot be verified safely, it stops before writing.

> FH needs 4 extra boundary layers to save the cover and apply bounds correctly.  
> Example: a 1000-layer JSON should use at least a 1004-layer template; a 3000-layer template can import about 2996 drawable shapes.

## Rules

- The template must be ungrouped.
- The layer count in the app must exactly match the game.
- Do not switch game menus while importing.
- After restarting the game, reloading the template, or changing layer count, import again with the new correct count.
- If JSON has fewer layers than the template, unused template layers are hidden.
- If JSON has more layers than the template, extra shapes are trimmed.
- If the imported image looks blurry, you probably imported a low-layer checkpoint or generated too few output layers.
- Transparent PNG backgrounds are not imported as visible backgrounds.

## Changelog

### v1.4.0 / 2026-05-21

- Updated the app version to `v1.4.0`; release packages now use `forza-painter-fh6-v1.4.0.zip`.
- Added an `Export detailed log` button that lets users choose where to save a diagnostic log capped at 50000 characters.
- Detailed logs now include raw helper/generator output, command lines, exit codes, selected process/template state, and current session details.
- Improved FH6 template auto-location by scanning large writable private memory regions in 4 MB chunks instead of skipping them.
- Changed FH6 layout scanning to prioritize larger writable private regions first, matching the working FH6-ready importer behavior more closely.
- Raised the FH6 template auto-locate scan limit to 120 seconds, with an outer app watchdog timeout of 160 seconds.
- Added stale game PID handling so the app refreshes the process list when the selected FH6 process no longer exists.

### v1.3.0 / 2026-05-21

- Updated the app version to `v1.3.0`; release packages now use `forza-painter-fh6-v1.3.0.zip`.
- Updated the bundled GPU/OpenCL generator to upstream `canary-26052101`.
- Added the upstream generator device-selection fix, which prioritizes NVIDIA GPUs with the most VRAM and helps avoid accidentally running generation on an integrated GPU.
- Generation logs now show the selected OpenCL device, making GPU selection easier to confirm.
- Adopted the upstream generator log wording change from `delta error` to `DeltaE`, reducing false error reports in generation logs.
- Improved FH6 template auto-locate failure handling so stale session cache is not reported as a newly verified template.

### v1.2.0 / 2026-05-20

- Updated the app version to `v1.2.0`; release packages now use `forza-painter-fh6-v1.2.0.zip`.
- Updated the bundled GPU/OpenCL generator to upstream `canary-26052001`, including the OpenCL slot deadlock fix, progressive scale decay, and occluded-geometry recycling.
- Added explicit `forceOpaqueShapes = true` to bundled and custom generation settings for compatibility with the current generator.
- Refreshed the README layout with a centered logo, clearer resource links, and a compact preview grid.

### v1.1.1 / 2026-05-20

- Added centralized version management. The window title, command-line `--version`, and release package name now use `v1.1.1`.
- Reorganized the repository layout: source code moved to `src/`, the generator moved to `bin/`, presets moved to `config/settings/`, and release scripts moved to `scripts/`.
- Updated the release script to build `forza-painter-fh6-v1.1.1.zip` and exclude caches, logs, and `__pycache__`.
- Merged license notices into the root `LICENSE`, including the bundled GPU/OpenCL generator notice.
- Added a `Stop current generation` button so the current GPU generator can be stopped safely.
- Added ETA display for generation progress, using rolling speed and smoothing to avoid large ETA jumps.
- Fixed a shutdown issue where the GPU generator could keep running after the app window was closed.
- Retuned bundled quality presets with clearer layer, random sample, and resolution tiers; added the `I hate my GPU` heavy preset.

### 2026-05-19

- The GPU/OpenCL generator was updated to the upstream canary build to improve transparent PNG edges and large overhang artifacts.
- Import and preview now normalize geometry JSON first, improving compatibility with common legacy forza-painter JSON field formats.

### 2026-05-18

- JSON generation now uses the bundled GPU/OpenCL generator to reduce artifacts from the old generator.
- The app now uses a standalone desktop window with generation, import, preview, and tutorial pages in one place.
- The Generate page has quality presets plus in-app custom settings, so users no longer need to edit config files manually.
- The Import page is simplified for normal users: select the game process, enter the template layer count, choose JSON, then import.
- Fixed an FH6 issue where the design was visible in the editor but saved with a blank cover, pasted blank onto the car, or appeared blank after copying to another vinyl.
- FH import now reserves 4 boundary layers so FH can calculate the saved cover and apply bounds correctly.
- Added environment checks and troubleshooting notes for Python, OpenCL, permissions, and optional preview dependencies.

## Troubleshooting

### GPU Generator Or OpenCL Error

Update the NVIDIA/AMD/Intel graphics driver. The bundled generator is `bin/forza-painter-geometrize-go.exe` and uses OpenCL.

### Python Or Dependency Error

Run:

```powershell
install_dependencies.bat
```

Then run:

```powershell
check_environment.bat
```

`Core OK` means the Python dependencies are installed.

### `_ARRAY_API not found`, NumPy, Or OpenCV Error

This is an optional preview dependency issue. It does not block JSON generation or FH6 import. Reinstall core dependencies first:

```powershell
python -m pip install -r requirements.txt
```

### `OpenProcess` Or Permission Error

Close the app and run `start_app.bat` as administrator.

JSON generation does not need administrator permission. FH6 import usually does.

### Game Process Not Found

Start FH6 first, then click `Refresh`. If it still does not appear, restart the app.

### No Safe Template Found

Check:

- You are in Vinyl Group Editor.
- The template is ungrouped.
- The layer count is exact.
- You did not switch menus after entering the count.

### Import Looks Cut Off

The template has too few layers. Use a larger template or generate fewer JSON layers.

## Files

Most users only need:

- `install_dependencies.bat`: install Python dependencies.
- `start_app.bat`: start the app.
- `check_environment.bat`: check the environment.
- `clean_runtime_data.bat`: remove runtime caches before publishing or re-zipping.
- `1. drag_image_file_here.bat`: optional shortcut for dragging an image into the app.

Do not publish runtime cache folders such as `webui-data`, `runtime`, `__pycache__`, or `dist`.

## Directory Layout

- `src/`: application source code; normal users do not need to open it.
- `bin/`: bundled GPU/OpenCL generator.
- `config/settings/`: generation quality presets.
- `assets/`: sample assets.
- `docs/screenshots/`: screenshots used by the README.
- `scripts/`: development and release scripts.
