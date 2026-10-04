"""Constants for the Lumagen Radiance Pro integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "lumagen"
MANUFACTURER: Final = "Lumagen, Inc."

CONF_URL: Final = "url"

# How often aiolumagen polls the device, in seconds. Most state arrives via
# the Lumagen's Full v5 push (`!I25`) in real time, but a handful of fields
# — sharpness, game mode, auto aspect, display Rec.2020 and source HDR
# metadata — are never pushed; the device only answers explicit queries for
# them. Those fields therefore lag by up to one poll interval when changed
# from the front-panel remote, which is why this is worth tuning.
#
# Lower = snappier, at the cost of more traffic on a 9600-baud link. The
# floor of 5s keeps a poll cycle comfortably shorter than the round trip
# for the five secondary queries plus their replies.
#
# 15s is the default because the 60s it replaced made front-panel changes
# feel broken rather than merely delayed. The cost is modest: while the
# device is on, a cycle issues six queries (ZQI25 plus the five secondary
# ones) totalling a few hundred bytes with replies — well under 2% of a
# 9600-baud link's capacity at this cadence. While the device is off,
# aiolumagen only issues the single power query per cycle.
CONF_POLL_INTERVAL: Final = "poll_interval"
DEFAULT_POLL_INTERVAL: Final = 15
MIN_POLL_INTERVAL: Final = 5
MAX_POLL_INTERVAL: Final = 600

# Service for power-user / advanced workflows: send any RS-232 string at the
# Lumagen and let the protocol parser feed unsolicited responses back into
# state. Useful for commands the integration doesn't expose as entities
# (e.g. ZY540-548 HDR test-pattern info frames during calibration).
SERVICE_SEND_RAW_COMMAND: Final = "send_raw_command"
ATTR_COMMAND: Final = "command"
ATTR_CR: Final = "cr"

# Services for the capabilities that take arguments, and so can't be buttons.
# The parameterless counterparts (clear the OSD, restart every input, show the
# aspect overlay) are buttons instead — more discoverable, and still callable
# from a script via button.press.
SERVICE_SEND_OSD_MESSAGE: Final = "send_osd_message"
SERVICE_SET_INPUT_LABEL: Final = "set_input_label"
SERVICE_RESTART_INPUT: Final = "restart_input"

ATTR_MESSAGE: Final = "message"
ATTR_LINE1: Final = "line1"
ATTR_LINE2: Final = "line2"
ATTR_DURATION: Final = "duration"
ATTR_CENTER: Final = "center"
ATTR_BLOCK_CHAR: Final = "block_char"
ATTR_INPUT: Final = "input"
ATTR_LABEL: Final = "label"
ATTR_MEMORY: Final = "memory"

# Input-memory banks a label can be written to. "ALL" writes A-D at once, which
# is the right default unless the banks are deliberately named differently.
INPUT_LABEL_MEMORIES: Final = ("ALL", "A", "B", "C", "D")

# The device's own duration vocabulary: 0-9, where 9 means "leave it up until
# cleared". Tip0011 doesn't quantify the lower values, so they're offered as
# opaque steps rather than mislabelled as seconds.
OSD_DURATION_MIN: Final = 0
OSD_DURATION_MAX: Final = 9

# Highest input the label and hotplug commands accept. Lower than the input
# *selection* range (1-19) because the device only defines labelling and
# per-input hotplug for the first eight.
MAX_ADDRESSABLE_INPUT: Final = 8

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
)

# ---------------------------------------------------------------------------
# Firmware updates
# ---------------------------------------------------------------------------

# Which releases the update entity offers. Beta is the default because Lumagen
# rarely posts Production builds — nearly every release since 030225 has been
# labelled Beta, so a Production-only default would almost never offer
# anything. The values equal aiolumagen.firmware.ReleaseChannel's, so an option
# value converts with ReleaseChannel(value). There is deliberately no "off":
# disabling the update entity already stops every check.
CONF_FIRMWARE_CHANNEL: Final = "firmware_channel"
FIRMWARE_CHANNEL_BETA: Final = "beta"
FIRMWARE_CHANNEL_PRODUCTION: Final = "production"
FIRMWARE_CHANNELS: Final = (FIRMWARE_CHANNEL_BETA, FIRMWARE_CHANNEL_PRODUCTION)
DEFAULT_FIRMWARE_CHANNEL: Final = FIRMWARE_CHANNEL_BETA

# Lumagen posts a release every month or two; a daily check is prompt enough
# and polite to a vendor site we scrape. The page is ~450 KB.
RELEASE_CHECK_INTERVAL: Final = timedelta(hours=24)
RELEASE_FETCH_TIMEOUT: Final = 30.0
# The updater zip is ~3 MB, fetched only when Install is pressed.
UPDATER_DOWNLOAD_TIMEOUT: Final = 180.0
# Size caps on what we'll read over HTTP. Both are ~8-10x the real sizes, so a
# redesign that grows the page won't trip them but a runaway response will.
# The archive's own caps (entry count, uncompressed EXE size) live in aiolumagen.
MAX_RELEASE_INDEX_BYTES: Final = 4 * 1024 * 1024
MAX_UPDATER_ZIP_BYTES: Final = 32 * 1024 * 1024

# Hosts the updater zip may be fetched from, checked (with https) on the listed
# URL and on every redirect hop before it is followed. The listing is on
# www.lumagen.com, whose /s/<zip> links answer 302 to Squarespace's asset CDN,
# static1.squarespace.com. Deliberately exact rather than *.squarespace.com:
# Squarespace subdomains also host other people's sites. If the CDN host ever
# moves, downloads fail closed with firmware_download_failed and the log names
# the refused URL — widen this list then, not speculatively.
FIRMWARE_DOWNLOAD_HOSTS: Final = frozenset(
    {"www.lumagen.com", "lumagen.com", "static1.squarespace.com"}
)
# The real chain is one hop; anything past a few is a loop or a misconfiguration.
FIRMWARE_DOWNLOAD_MAX_REDIRECTS: Final = 5

# Descriptive, so Lumagen can identify (and contact) the source of the checks.
FIRMWARE_USER_AGENT: Final = "ha-lumagen (+https://github.com/frankrosano/ha-lumagen)"

# The only transfer rate qualified on hardware: the vendor's own, and the one
# aiolumagen's flush barrier was designed for (aiolumagen.firmware
# DEFAULT_UPDATE_BAUDRATE). 115200 in particular is known-bad.
FIRMWARE_UPDATE_BAUDRATE: Final = 230400

# How long to wait for the Lumagen to report power-on after we ask for it.
FIRMWARE_POWER_ON_TIMEOUT: Final = 60.0

# Extra wait after the Lumagen reports power-on and before any firmware command.
#
# Derived rather than measured, then checked on hardware. aiolumagen's
# preflight (firmware/session.py, the standby gate) only checks that ZQS02
# reports "on"; it does not wait for the unit to finish coming up.
# FIRMWARE_UPDATE_PROTOCOL.md (lumagen-research) §I.2
# and §4.1 say standby services no updater commands and that the vendor's
# Tip0006 procedure opens with "Turn the Radiance power on", but give no
# duration. The only documented startup timing is the ~10 s window after
# power-on in which boot mode listens (§4.1's "…within 10 SECONDS" message;
# lumagen-research probe_proxy.py). 15 s is that window plus 5 s of margin —
# negligible against a transfer of several minutes. The install logs the
# observed power-on time: on a Radiance Pro 4242 the unit reported power-on
# 9.7 s after the request, and preflight passed first try after this settle.
FIRMWARE_POWER_ON_SETTLE: Final = 15.0

# Bound on the best-effort standby sent when an install is cancelled (HA
# stopping) after we auto-powered the unit but before the session started.
# Short, because it runs while the task is being cancelled.
FIRMWARE_CANCEL_STANDBY_TIMEOUT: Final = 5.0

# After a promoted update the unit powers itself down (Z97). This bounds the
# wait for the client to reconnect and see standby before powering it back on.
FIRMWARE_POST_UPDATE_STANDBY_TIMEOUT: Final = 180.0

# How often to re-ask for power state while waiting on a transition. The
# client's own poll may be minutes apart; this keeps the wait responsive.
FIRMWARE_POWER_QUERY_INTERVAL: Final = 5.0

# How long to wait for a device-info response during config-flow validation.
VALIDATION_TIMEOUT: Final = 5.0
