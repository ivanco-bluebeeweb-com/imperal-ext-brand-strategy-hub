"""Regression: panel renderer failures must be visible, not an endless loading overlay."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m


@pytest.mark.asyncio
async def test_brand_detail_panel_returns_visible_error_when_renderer_fails(monkeypatch):
    ctx = MockContext()

    async def broken_renderer(*args, **kwargs):
        raise RuntimeError("simulated renderer failure")

    monkeypatch.setattr(m, "_render_brand_detail_panel", broken_renderer)

    result = await m.brand_detail_panel(ctx, brand_id="climtec", tab="visual_system")
    rendered = repr(result)

    assert "Brand detail could not load" in rendered
    assert "brand=climtec" in rendered
    assert "error=RuntimeError" in rendered
