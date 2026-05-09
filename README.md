# ha-lumagen

Home Assistant custom integration for a [Lumagen Radiance Pro](https://www.lumagen.com/) video processor.

This integration is a thin wrapper over [`pylumagen`](../pylumagen). All protocol work — parsing, state tracking, commands — lives in the library; the integration adds HA lifecycle, entities, and a config flow.

## Topology

```
Home Assistant              Lumagen Radiance Pro
  │                              ▲
  │  (native serial_proxy)       │
  ▼                              │
ESPHome integration ─── esphome://host:6053/?port_name=Lumagen&key=...
  │                              │
  ▼                              │
esphome-lumagen firmware ── USB  │
  │                              │
  └──────── USB-C → USB-B ───────┘
```

The ESPHome bridge ([`esphome-lumagen`](../esphome-lumagen)) exposes the Lumagen's USB-B serial port to Home Assistant via ESPHome's `serial_proxy` component. When you adopt the ESPHome device in HA, HA automatically lists its serial proxies alongside any physical `/dev/tty*` ports. This integration's config flow presents that list as a dropdown — no host/PSK fields to fill in.

Direct RS-232 (cabled from your HA host to the Lumagen's DB9) also works — the same dropdown will show the `/dev/tty*` entry.

## Requirements

- Home Assistant **2026.5** or newer (native serial_proxy surfacing in the `usb` integration)
- The [`esphome-lumagen`](../esphome-lumagen) firmware on a Waveshare ESP32-S3-POE-ETH (or a direct RS-232 cable)
- The ESPHome integration adopted in HA for the bridge device (if going the ESPHome route)
- Network connectivity between HA and the bridge

## Installation

### HACS (once added to a repo)

1. HACS → Integrations → menu → Custom repositories → add `https://github.com/frankrosano/ha-lumagen` as type *Integration*.
2. Install **Lumagen Radiance Pro**.
3. Restart Home Assistant.

### Manual

1. Copy `custom_components/lumagen` into your HA config directory's `custom_components/`.
2. Restart Home Assistant.

## Setup

1. Settings → Devices & services → **Add integration** → search for **Lumagen Radiance Pro**.
2. From the dropdown, pick the serial port for the Lumagen. ESPHome-proxied ports appear with their friendly name ("Lumagen") plus the bridge's hostname; physical ports appear with their `/dev/tty*` path.
3. The flow opens the port, queries `ZQS01` for the device info, and creates the config entry with the detected model and firmware in the title.

## Lumagen-side prerequisite: unsolicited reporting

For real-time updates rather than 60-second polling, enable Full v4 reporting on the Lumagen:

1. On the Lumagen remote or OSD, press `MENU`.
2. Navigate: **Other → I/O Setup → RS-232 Setup → Report mode changes**.
3. Cycle to **Full v4**.
4. Press `OK`, then `SAVE` to persist.

The integration works either way; this just makes it snappier.

## Exposed entities

- **Binary sensors**: Power, HDR active
- **Sensors** (diagnostic): Model, Firmware
- **Sensors** (primary): Current input, Input memory, Source/Output resolution, Source/Output refresh rate (Hz), Source/Content aspect, Colorspace (enum), HDR status (enum), Input status (enum), Source mode (enum: Interlaced / Progressive / No input)
- **Buttons**: Power on/Standby, full OSD nav (Menu/Exit/OK/Menu off/Up/Down/Left/Right), direct inputs 1–8 + Previous, all aspect presets (4:3, Letterbox, 16:9, 16:9 NZ, 1.85, 2.35, 2.40), Auto aspect on/off, Memory A–D, HDR setup, Test pattern, OSD on/off, Save to NVRAM, Query status
- **Selects**: Input (1–8), Aspect ratio (7 options), Memory (A–D)

## Status

Alpha / prototype. Not yet published to HACS default store.

## License

MIT. See [`LICENSE`](LICENSE).
