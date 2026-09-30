"""Synthetic firmware fixtures shared by the update / install tests.

Everything here is invented: the HTML mimics the shape of the vendor's
Squarespace release page (nesting, labels, the "Update time" sentence) with
made-up note text, and the zip holds dummy bytes. No vendor material.
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

from aiolumagen import LumagenState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumagen.const import CONF_URL, DOMAIN

CLIENT_FACTORY = "custom_components.lumagen.coordinator.create_lumagen_client"
# The shape HA itself hands us for an ESPHome serial_proxy. It must reach the
# firmware session verbatim.
HASS_URL = "esphome-hass://esphome/01TESTENTRY?port_name=Lumagen"


def _entry(revision: str, label: str, posted: str, notes: str, minutes: int | None) -> str:
    update_time = (
        f"<br><strong><em>Update time ~{minutes} minutes @230k from previous firmware."
        "</em></strong>"
        if minutes is not None
        else ""
    )
    return (
        f'<li><p><a href="/s/radiance_pro{revision}.zip">Download</a></p>'
        f"<ul><li><p><strong>{label} {revision}-</strong><em>Posted {posted}</em>"
        f"&nbsp; {notes}{update_time}</p></li></ul></li>"
    )


def release_page(*entries: tuple[str, str, str, str, int | None]) -> str:
    """Build a release page, newest first as the vendor lists it."""
    body = "".join(_entry(*e) for e in entries)
    return f"<html><body><ul>{body}</ul><p>Synthetic footer.</p></body></html>"


DEFAULT_PAGE = release_page(
    ("030326", "Beta", "042826", "Invented beta note about widgets.", 5),
    ("030225", "Production", "031025", "Invented production note.", 1),
)


def updater_zip(exe_name: str = "radiance_pro030326.exe", extra: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(exe_name, b"MZ" + b"\0" * 64)
        if extra:
            zf.writestr("Tip0006_Synthetic.pdf", b"%PDF-synthetic")
    return buf.getvalue()


def make_client(firmware: str = "030225", power_on: bool | None = True) -> MagicMock:
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.send_command = AsyncMock()
    client.power_on = AsyncMock()
    client.standby = AsyncMock()
    client.query_power = AsyncMock()
    for query in (
        "query_sharpness",
        "query_game_mode",
        "query_auto_aspect",
        "query_display_rec2020",
        "query_source_hdr_status",
        "query_input_labels",
    ):
        setattr(client, query, AsyncMock())
    client.connected = True
    client.available = True
    client.subscribe = MagicMock(return_value=lambda: None)
    client.state = LumagenState(model="RadiancePro", firmware=firmware, power_on=power_on)
    return client


async def setup_entry(
    hass: HomeAssistant,
    client: MagicMock,
    *,
    options: dict[str, object] | None = None,
    url: str = HASS_URL,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: url},
        options=options or {},
        unique_id="test_lumagen",
        title="Lumagen RadiancePro",
    )
    entry.add_to_hass(hass)
    with patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def notification_messages(hass: HomeAssistant) -> list[str]:
    """Messages of every persistent notification currently posted."""
    from homeassistant.components import persistent_notification

    stored = persistent_notification._async_get_or_create_notifications(hass)
    return [n["message"] for n in stored.values()]
