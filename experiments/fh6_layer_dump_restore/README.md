# FH6 Layer Dump/Restore Experiment

This is an isolated experiment for testing whether FH6 vinyl layers can be
exported from game memory and restored later without understanding every shape
ID semantically.

It is not part of the normal app workflow and is intentionally not included in
release packages.

For reverse-engineering findings and current risk notes, see
[`DEVELOPMENT.md`](DEVELOPMENT.md).

## What It Does

- Locates the current FH6 vinyl layer table using the existing locator.
- Exports each layer pointer target as a fixed-size raw blob.
- Saves a small summary of known fields: position, scale, rotation, color,
  mask flag, and the current 1-byte shape-id field.
- Restores raw blobs back into the current template for testing.

## Important Risk

Raw layer blobs may contain unknown fields or pointers. Restoring a dump across
different game versions, different sessions, or different template structures
may fail or produce unstable behavior.

Start by testing this only in the same FH6 session:

1. Open FH6 Vinyl Group Editor.
2. Load and ungroup a template.
3. Export a dump.
4. Change a few layers in-game.
5. Restore the dump to the same template.

## Export

Run from the repository root:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py export --layer-count 1000 --output fh6-layer-dump.json
```

Optional flags:

```powershell
--pid 12345
--blob-size 0x140
--max-layers 100
```

## Safe Field Restore

Full raw blob restore crashed FH6 during testing. Do not use it for normal
testing.

The safer restore path only writes fields already used by the normal importer:

- position
- scale
- rotation
- color
- mask flag
- 1-byte shape ID field

Run:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py restore-known-fields --layer-count 226 --input fh6-layer-dump.json
```

For a larger current template, restore only the overlapping prefix:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py restore-known-fields --layer-count 548 --input fh6-layer-dump.json --allow-count-mismatch
```

## Raw Restore

Raw restore is disabled by default because it can crash FH6. It overwrites
unknown layer fields and may overwrite session-local pointers or internal state.

Only use it for manual crash-risk experiments:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py restore-raw --layer-count 1000 --input fh6-layer-dump.json --i-understand-this-can-crash-fh6
```

If the current template layer count differs from the dump, restore stops unless
you pass:

```powershell
--allow-count-mismatch
```

## Notes

- The dump stores raw layer bytes, not the same geometry JSON used by the image
  generator.
- This does not convert arbitrary shape IDs into generator `type 1` / `type 16`.
- The purpose is to prove whether same-structure FH6 layer backup/restore is
  viable before building UI support.

## Compare Dumps

Use this after exporting two states of the same template to identify candidate
offsets:

```powershell
python experiments\fh6_layer_dump_restore\fh6_layer_dump_restore.py compare-dumps --a before.json --b after.json --layer 0
```

For shape reverse engineering, the safest test is:

1. Export a dump.
2. Change one layer's shape in-game without changing the layer count.
3. Export another dump.
4. Compare only that layer.

This avoids the pointer noise that appears when comparing dumps across game
sessions or different template objects.
