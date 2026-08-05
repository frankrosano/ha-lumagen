"""Tests for the binary_sensor platform's state wiring."""

from __future__ import annotations

from aiolumagen import LumagenState

from custom_components.lumagen.binary_sensor import BINARY_SENSORS

_BY_KEY = {description.key: description for description in BINARY_SENSORS}


def test_binary_sensor_keys_are_unique() -> None:
    keys = [description.key for description in BINARY_SENSORS]
    assert len(keys) == len(set(keys))


def test_nls_active_reads_the_bool_not_the_wire_letter() -> None:
    """NLS is reported as 'N' when engaged and '-' when normal.

    That letter reads like "no", which is exactly the trap. aiolumagen resolves
    it to a bool, so this entity just has to pass it through — but the test is
    worth having because a future refactor reaching for the raw field would
    invert the sensor.
    """
    assert _BY_KEY["nls_active"].value_fn(LumagenState(nls_active=True)) is True
    assert _BY_KEY["nls_active"].value_fn(LumagenState(nls_active=False)) is False


def test_nls_active_unknown_before_first_status_line() -> None:
    assert _BY_KEY["nls_active"].value_fn(LumagenState()) is None
