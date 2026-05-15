# Product

`ha-lumagen` is a Home Assistant custom integration for a Lumagen Radiance Pro video processor.

## Scope

A thin wrapper over [`pylumagen`](../pylumagen). All Lumagen protocol work — parsing, command formatting, state tracking, polling, reconnection — lives in the library. This integration owns:

- Home Assistant lifecycle (`async_setup_entry`, platform forwarding, unload)
- Config flow (port selection from HA's serial dropdown, device-info validation via `ZQS01`)
- Coordinator (wraps `pylumagen.LumagenClient`, surfaces state to entities)
- Entities: binary sensors, sensors, buttons, selects
- Translations and strings

## Topology

```
Home Assistant              Lumagen Radiance Pro
  │                              ▲
  │  (HA's native serial_proxy)  │
  ▼                              │
ESPHome integration ─── esphome://host:6053/?port_name=Lumagen&key=...
  │                              │
  ▼                              │
esphome-lumagen firmware ── USB  │
  │                              │
  └──────── USB-C → USB-B ───────┘
```

Direct RS-232 from the HA host's `/dev/tty*` also works — same dropdown, same flow.

## Requirements

- **Home Assistant 2026.5+** (required for native `serial_proxy` surfacing in the `usb` integration — older versions won't show the proxied port in the dropdown)
- Either the `esphome-lumagen` bridge (adopted in HA's ESPHome integration) **or** a direct RS-232 cable from HA host to the Lumagen's DB9

## Exposed Entities

- **Binary sensors**: Power, HDR active
- **Diagnostic sensors**: Model, Firmware
- **Primary sensors**: Current input, Input memory, Source/Output resolution, Source/Output refresh rate (Hz), Source/Content aspect, Colorspace (enum), HDR status (enum), Input status (enum), Source mode (enum: Interlaced / Progressive / No input)
- **Buttons**: Power on/Standby, full OSD nav (Menu/Exit/OK/Menu off/Up/Down/Left/Right), direct inputs 1–8 + Previous, all aspect presets (4:3, Letterbox, 16:9, 16:9 NZ, 1.85, 2.35, 2.40), Auto aspect on/off, Memory A–D, HDR setup, Test pattern, OSD on/off, Save to NVRAM, Query status
- **Selects**: Input (1–8), Aspect ratio (7 options), Memory (A–D)

## Status

Alpha. HACS quality scale: bronze. Not yet in the HACS default store.
