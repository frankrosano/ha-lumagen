"""Shared fixtures for ha-lumagen tests.

``pytest-homeassistant-custom-component`` provides the ``hass`` fixture
and friends; we add two knobs: ``enable_custom_integrations`` is required
when the integration under test is a custom_components one, and every test
gets a mocked lumagen.com release page so a whole-entry setup (which adds
the firmware update entity, which triggers a release check) never reaches
for the network.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from aiolumagen.firmware import RELEASES_URL
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .firmware_helpers import DEFAULT_PAGE


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Auto-apply the pytest-homeassistant-custom-component enabler."""
    yield


@pytest.fixture(autouse=True)
def mock_release_index(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve a small synthetic release page: Beta 030326, Production 030225."""
    aioclient_mock.get(RELEASES_URL, text=DEFAULT_PAGE)
    return aioclient_mock
