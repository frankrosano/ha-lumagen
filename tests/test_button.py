"""Tests for the button platform's command wiring.

Exercises each description's ``press_fn`` against a mock client. The wire
strings those client methods produce are covered upstream in aiolumagen; what
matters here is that a given button reaches the method it claims to.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.lumagen.button import BUTTONS

_BY_KEY = {description.key: description for description in BUTTONS}


def test_button_keys_are_unique() -> None:
    """Duplicate keys would collide on unique_id and silently drop an entity."""
    keys = [description.key for description in BUTTONS]
    assert len(keys) == len(set(keys))


def test_every_button_declares_a_translation_key() -> None:
    """A missing translation_key shows the raw key as the entity name."""
    for description in BUTTONS:
        assert description.translation_key, description.key


async def test_restart_outputs_and_restart_inputs_hit_different_methods() -> None:
    """The regression this file exists for.

    These two sit next to each other, read almost identically, and act on
    opposite ends of the signal chain. Swapping them wouldn't raise — it would
    renegotiate the wrong link and look like the button doing nothing, since
    both produce a brief dropout.
    """
    client = MagicMock()
    client.restart_input = AsyncMock()
    client.restart_outputs = AsyncMock()

    await _BY_KEY["restart_outputs"].press_fn(client)
    client.restart_outputs.assert_awaited_once_with()
    client.restart_input.assert_not_awaited()

    client.restart_outputs.reset_mock()
    await _BY_KEY["restart_inputs"].press_fn(client)
    client.restart_input.assert_awaited_once_with("all")
    client.restart_outputs.assert_not_awaited()


def test_restart_outputs_takes_no_argument() -> None:
    """The underlying command is parameterless, so there's no per-output form.

    Pinned so nobody adds an input-style parameter that the device would read
    as trailing junk after a complete command.
    """
    assert "restart_outputs" in _BY_KEY
    # No sibling per-output keys should appear.
    assert [k for k in _BY_KEY if k.startswith("restart_output")] == [
        "restart_outputs"
    ]


@pytest.mark.parametrize(
    ("key", "method"),
    [
        ("show_aspect", "show_aspect"),
        ("clear_osd_message", "clear_message"),
        ("save", "save_config"),
        ("redetect_aspect", "reset_auto_aspect"),
        ("query_status", "query_full_status"),
    ],
)
async def test_client_method_buttons_dispatch_correctly(key: str, method: str) -> None:
    client = MagicMock()
    setattr(client, method, AsyncMock())
    await _BY_KEY[key].press_fn(client)
    getattr(client, method).assert_awaited_once()


async def test_save_uses_the_single_shot_command_not_the_two_key_sequence() -> None:
    """A save that loses its confirmation keystroke leaves a prompt on screen.

    Pinned because reverting to the remote-key sequence would still appear to
    work in testing and only fail when a byte is dropped.
    """
    client = MagicMock()
    client.save_config = AsyncMock()
    client.send_command = AsyncMock()
    await _BY_KEY["save"].press_fn(client)
    client.save_config.assert_awaited_once()
    client.send_command.assert_not_awaited()
