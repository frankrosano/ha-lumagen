---
inclusion: manual
---

# References — Lumagen Documentation

Lumagen primary-source docs (the `Tip0011` RS-232 PDF, the Radiance Pro manual, Crestron sample drivers, Pronto IR codes, the reverse-engineered firmware updater and its flash captures) live in the sibling repo `lumagen-research` (`../lumagen-research`). That repo is **private**, because the material is largely under Lumagen, Inc.'s copyright.

It was previously a gitignored `References/` folder inside `esphome-lumagen`, so any `References/x` path in older notes now means `../lumagen-research/x`.

For this repo, you almost never need them. Protocol facts belong in `aiolumagen` (the sibling repo), not here. The integration consumes the parsed `LumagenState` and the typed enums (`Aspect`, `Input`, `Memory`, `Colorspace`, `HdrStatus`, `InputStatus`, `SourceMode`) — it doesn't care how the wire format works.

If you find yourself needing to read `Tip0011` while editing `coordinator.py` or an entity file, that's a strong signal the change belongs in `aiolumagen` instead.

This repo is public: never copy a PDF, firmware blob, vendor EXE or capture out of `lumagen-research` into it. Cite by filename if a reference is genuinely needed.

The file-by-file inventory, with the rules for handling this material, lives in the research repo itself at `../lumagen-research/.kiro/steering/references.md`.
