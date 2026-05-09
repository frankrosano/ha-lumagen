"""Tests for the aspect-ratio mapping helpers in select.py.

The Lumagen doesn't report which aspect preset is currently selected;
we snap the detected content aspect to the closest preset label as a
best-effort display. These tests pin that mapping.
"""

from __future__ import annotations

import pytest

from custom_components.lumagen.select import _closest_aspect_label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("133", "4:3"),     # exactly 1.33
        ("178", "16:9"),    # exactly 1.78
        ("185", "1.85"),    # exactly 1.85
        ("235", "2.35"),    # exactly 2.35
        ("240", "2.40"),    # exactly 2.40
        ("180", "16:9"),    # between 1.78 and 1.85 — closer to 16:9
        ("238", "2.40"),    # between 2.35 and 2.40 — closer to 2.40
        ("175", "16:9"),    # slightly under 1.78 still rounds to 16:9
        ("250", "2.40"),    # above 2.40 clamps to the top entry
        ("100", "4:3"),     # well below 1.33 clamps to the bottom entry
    ],
)
def test_closest_aspect_label(raw: str, expected: str) -> None:
    assert _closest_aspect_label(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "abc", "not-a-number"])
def test_closest_aspect_label_handles_garbage(raw: str | None) -> None:
    assert _closest_aspect_label(raw) is None
