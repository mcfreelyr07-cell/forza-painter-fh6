# FH6 Layer Dump/Restore Development Notes

This document records the reverse-engineering state for the experimental FH6
layer dump/restore tool. It is not release documentation and should not be
included in normal user-facing workflows.

## Current Status

- Exporting fixed-size `0x140` layer blobs works.
- Restoring only known visual fields works without crashing in the tested
  session.
- Full raw blob restore crashed FH6 and must remain gated.
- Shape restore is only partially understood.
- Same-session shape pointer copying can change visible shapes, but it can
  leave the editor or shape picker in an unstable state.

Do not save a design after experimental writes unless the test explicitly
requires it. Restart FH6 before returning to normal app testing.

## Known Stable Fields

These fields are already used by the normal importer or have behaved like
ordinary per-layer visual data during testing.

| Field | Offset | Size | Notes |
| --- | ---: | ---: | --- |
| Position | `0x18` | 8 | Two little-endian `float32` values. |
| Scale | `0x28` | 8 | Two little-endian `float32` values. |
| Rotation | `0x50` | 4 | One little-endian `float32` value. |
| Color | `0x74` | 4 | RGBA bytes. |
| Mask flag | `0x78` | 1 | Mask state changed successfully. |
| Shape ID byte | `0x7A` | 1 | Changes with shape, but is not enough by itself. |

`restore-known-fields` writes only these fields.

## Shape Findings

Controlled same-session test:

1. Exported `fh6-layer-dump-226-before-shape-change.json`.
2. User changed only the first visible layer shape in game.
3. Exported `fh6-layer-dump-226-after-shape-change.json`.
4. Compared only layer index `0`.

Observed layer `0` differences:

| Offset | Before | After | Current interpretation |
| --- | --- | --- | --- |
| `0x58` | `04 00 00 00` | `08 00 00 00` | Candidate vertex/shape count, but unstable after writes. |
| `0x7A` | `6D` | `72` | Shape ID byte. |
| `0xA8` | `0x0000024488e8c210` | `0x00000246b62a7990` | Shape resource or mesh object pointer. |

Copy test:

- Source: layer `0` from `fh6-layer-dump-226-after-shape-change.json`.
- Target: layers `1..225` in the same live FH6 session.
- Written fields: `0x58`, `0x7A`, `0xA8`.
- Result: visible shapes unified in game.
- Post-write readback: all 226 layers had `shape_id_byte = 114` and
  `shape_resource_pointer = 0x246b62a7990`.
- Post-write readback: `0x58` did not remain uniform, so FH6 appears to mutate
  or recompute it.

The shape resource pointer is session-local. It must not be copied from an old
dump into a new game session unless it is first verified to be readable and
valid in the current process.

## Unsafe Or Failed Approaches

Do not use these as normal workflows:

- Full raw restore across templates or sessions.
- Copying stale `0xA8` pointers from old dumps.
- Writing large unknown ranges to chase shape state.
- Saving a design after shape pointer experiments.
- Continuing normal testing after the shape picker or preset list looks wrong.

The observed crash after opening or switching shapes is consistent with the
editor hitting corrupted or incompatible state from experimental writes. Treat
the current FH6 session as contaminated after any shape-pointer write.

## Commands

Export a controlled before dump:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py export --layer-count 226 --output runtime\experiments\fh6-layer-dump-226-before-shape-change.json --max-seconds 60
```

After changing one layer's shape in game, export after:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py export --layer-count 226 --output runtime\experiments\fh6-layer-dump-226-after-shape-change.json --max-seconds 60
```

Compare only the changed layer:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py compare-dumps --a runtime\experiments\fh6-layer-dump-226-before-shape-change.json --b runtime\experiments\fh6-layer-dump-226-after-shape-change.json --layer 0 --top 200 --examples 1
```

Dry-run copying the changed shape to other layers:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py copy-shape-from-layer --layer-count 226 --source-layer 0 --source-dump runtime\experiments\fh6-layer-dump-226-after-shape-change.json --target-start 1 --target-end 225 --dry-run --max-seconds 60
```

Actual same-session shape copy:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py copy-shape-from-layer --layer-count 226 --source-layer 0 --source-dump runtime\experiments\fh6-layer-dump-226-after-shape-change.json --target-start 1 --target-end 225 --max-seconds 60
```

## Next Research Steps

Before doing more writes:

1. Restart FH6 and reload a clean test template.
2. Export a clean baseline.
3. Change exactly one layer shape.
4. Export immediately.
5. Compare only that layer.

Recommended next checks:

- Identify whether `0xA8` can be derived from a clean in-session shape library
  instead of being copied from an edited layer.
- Determine whether `0x58` is an input field, a cache field, or a derived
  per-shape value.
- Find whether additional dirty flags or cache invalidation fields are required
  after changing `0x7A` and `0xA8`.
- Avoid touching the shape picker data structures directly.

## Main App Boundary

Do not merge this experiment into the normal importer yet.

The main app should keep using its current supported shape workflow until shape
restore can be made safe across a clean FH6 session and a clean template. The
experiment can inform future work, but the production importer should not write
session-local shape resource pointers.
