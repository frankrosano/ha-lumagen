# Tech Stack

## Language & Runtime

- **Python 3.14+** (matches HA core's pinned interpreter)
- Async throughout — every public coroutine in `pylumagen` is awaited from HA's event loop
- `from __future__ import annotations` at the top of every module

## Home Assistant

- Minimum HA core: **2026.5.0** (`hacs.json`). This is hard — the integration relies on the `usb` integration surfacing ESPHome `serial_proxy` ports in its discovery list.
- `manifest.json` declares:
  - `dependencies: ["usb"]` — needed for the serial-port dropdown
  - `after_dependencies: ["esphome"]` — so adopted ESPHome devices have set up before us
  - `iot_class: "local_push"` — Lumagen `Full v4` reporting is the primary path; polling is fallback
  - `config_flow: true`, `integration_type: "device"`, `quality_scale: "bronze"`

## Runtime Dependency

```
pylumagen@git+https://github.com/frankrosano/pylumagen.git@main
```

The integration imports from `pylumagen` directly (client, state, exceptions, enums). During development, `pyproject.toml` overrides this with `[tool.uv.sources]` pointing at the sibling `../pylumagen` repo via `editable = true`.

## Dev Dependencies

In the `dev` group of `pyproject.toml`:

- `pytest-homeassistant-custom-component >= 0.13` — pulls in HA core + pytest fixtures pinned to a real release
- `aiousbwatcher` — pulled explicitly because HA's `usb` integration imports it (it's an optional extra on the `homeassistant` package)
- `pylumagen` (editable, via uv source override) — needed because integration code imports it
- `ruff >= 0.7`, `mypy >= 1.11`

## Tooling Configuration

- **Ruff**: `line-length = 100`, `target-version = "py314"`, lint rules: `E F W I UP B C4 SIM RUF`
- **Mypy**: `python_version = "3.14"`, `strict = false` (HA's stubs aren't strict-clean — keep false until they are), `warn_unreachable = true`
- **Pytest**: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `addopts = "-ra --strict-markers --strict-config"`

## Common Commands

```bash
uv sync                # install + sync .venv
uv run pytest          # run the test suite (uses pytest-homeassistant-custom-component)
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy custom_components/lumagen   # type check
```

To test against a real Lumagen during development, point the integration at the sibling `pylumagen` checkout (already wired via `[tool.uv.sources]`) and copy `custom_components/lumagen/` into your HA config dir's `custom_components/`.

## Exception Handling Contract (from `pylumagen`)

| `pylumagen` exception | Translation |
|---|---|
| `LumagenConnectionError` | Raise `ConfigEntryNotReady` from `async_setup_entry`, or mark device unavailable from the coordinator |
| `LumagenTimeoutError` | Raise `UpdateFailed` from `_async_update_data` |
| `LumagenCommandError` | Log a warning; don't surface to the user |

No `LumagenAuthError` — Lumagen has no auth. ESPHome PSK errors arrive as `LumagenConnectionError`.

## Distribution

- HACS custom repository (not yet in default store): `https://github.com/frankrosano/ha-lumagen`, type *Integration*
- The deployable artifact is `custom_components/lumagen/` — the top-level `pyproject.toml` is dev metadata only, not shipped
