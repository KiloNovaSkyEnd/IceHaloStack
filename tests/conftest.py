"""Shared deterministic fixtures for the complete regression suite."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def reference_image(tmp_path):
    """Small real image path used by Tk and processing integration tests."""
    height, width = 72, 108
    x = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    rgb = np.stack(
        [np.broadcast_to(x, (height, width)), np.broadcast_to(y, (height, width)),
         np.full((height, width), 96, dtype=np.uint8)],
        axis=-1,
    )
    path = tmp_path / "reference.png"
    Image.fromarray(rgb, "RGB").save(path)
    return str(path)
