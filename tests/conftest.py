"""Shared fixtures for ha-lumagen tests.

``pytest-homeassistant-custom-component`` provides the ``hass`` fixture
and friends; we only add one knob: ``enable_custom_integrations`` is
required when the integration under test is a custom_components one.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Auto-apply the pytest-homeassistant-custom-component enabler."""
    yield
