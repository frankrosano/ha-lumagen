---
inclusion: manual
---

# References — Lumagen Documentation

Lumagen primary-source docs (the `Tip0011` RS-232 PDF, the Radiance Pro manual, Crestron sample drivers, Pronto IR codes, RE'd firmware updater) live in the sibling repo at `../esphome-lumagen/References/`. The whole folder is gitignored.

For this repo, you almost never need them. Protocol facts belong in `pylumagen`, not here. The integration consumes the parsed `LumagenState` and the typed enums (`Aspect`, `Input`, `Memory`, `Colorspace`, `HdrStatus`, `InputStatus`, `SourceMode`) — it doesn't care how the wire format works.

If you find yourself needing to read `Tip0011` while editing `coordinator.py` or an entity file, that's a strong signal the change belongs in `pylumagen` instead.

The richer references doc with file-by-file detail lives at `../esphome-lumagen/.kiro/steering/references.md`.
