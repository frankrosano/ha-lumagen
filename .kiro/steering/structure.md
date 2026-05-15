# Project Structure

```
ha-lumagen/
├── pyproject.toml                       # dev metadata only (NOT shipped — deploy artifact is custom_components/lumagen/)
├── hacs.json                            # HACS manifest (name, country, min HA version)
├── README.md
├── LICENSE
├── custom_components/
│   └── lumagen/                         # ← the actual integration; this is what ships
│       ├── manifest.json                # domain, deps, requirements, quality scale
│       ├── const.py                     # DOMAIN, MANUFACTURER, CONF_*, PLATFORMS tuple, timeouts
│       ├── __init__.py                  # async_setup_entry / async_unload_entry / platform forwarding
│       ├── config_flow.py               # serial-port dropdown + ZQS01 device-info validation
│       ├── coordinator.py               # DataUpdateCoordinator wrapping pylumagen.LumagenClient
│       ├── entity.py                    # shared base class for Lumagen entities
│       ├── binary_sensor.py             # Power, HDR active
│       ├── sensor.py                    # Model/Firmware (diagnostic) + state sensors
│       ├── button.py                    # OSD nav, direct inputs, aspects, memories, etc.
│       ├── select.py                    # Input / Aspect / Memory selects
│       ├── strings.json                 # English UI strings (source of truth for translations)
│       └── translations/                # generated/translated locale JSON
└── tests/
    ├── conftest.py                      # shared fixtures (HA, mocked pylumagen client)
    ├── test_config_flow.py
    └── test_select.py
```

## Conventions

- **`custom_components/lumagen/` is the deployable artifact.** Anything outside it (root `pyproject.toml`, `tests/`, etc.) is dev tooling and does not ship to user installs.
- **Domain string lives in `const.py` only.** Always import `DOMAIN` from `.const` — never hardcode `"lumagen"` in entity unique_ids, service names, or storage keys.
- **`PLATFORMS` is the single source of truth** for what gets forwarded in `async_setup_entry` and unloaded in `async_unload_entry`. Adding a platform = add the file + add to the tuple.
- **`from __future__ import annotations`** at the top of every Python module.
- **No protocol logic in the integration.** If you find yourself parsing an `!` response or formatting a `ZQ` query in `coordinator.py` or `button.py`, that logic belongs in `pylumagen` instead.
- **Coordinator with `always_update=False`.** `LumagenState` implements `__eq__` so the coordinator can skip redundant entity writes — preserve that behavior.
- **Manifest `requirements` pins `pylumagen` from git.** During development, `[tool.uv.sources]` in the root `pyproject.toml` redirects to the sibling repo via path. End users always get the git pin.
- **Entity unique_ids** must include the config-entry-id or device-identifying string from the Lumagen's `ZQS01` response, never the friendly name (which the user can change).
- **Strings.** UI-facing copy goes in `strings.json` and the matching `translations/en.json`. Don't hardcode user-visible strings in Python.

## Testing

- Tests use `pytest-homeassistant-custom-component`, which spins up a fake HA core. Fixtures live in `tests/conftest.py`.
- `asyncio_mode = "auto"` — async tests don't need the `@pytest.mark.asyncio` decorator.
- Mock `pylumagen.LumagenClient` rather than running real serial I/O. The protocol layer is already tested in the `pylumagen` repo; here, test HA-side wiring (config flow, coordinator translation, entity attributes).

## Where Things Live (Cross-Repo)

| Concern | Location |
|---|---|
| Bytes on the wire, command formatting, state parsing | `pylumagen` |
| HA entities, config flow, coordinator, translations | This repo |
| ESP32 firmware bridging USB to network | `esphome-lumagen` |
| Lumagen protocol PDFs, Crestron driver, Pronto codes | `esphome-lumagen/References/` (gitignored) |

When in doubt: if it could be useful to a non-HA Python consumer, it goes in `pylumagen`. If it's HA-shaped (entity descriptions, platforms, config flows, translations), it goes here.
