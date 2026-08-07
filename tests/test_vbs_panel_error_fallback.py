"""Regression: panel renderer failures must be visible, not an endless loading overlay."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import CreateBrandProfileParams


async def _brand(ctx) -> str:
    result = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    return result.data.id


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


@pytest.mark.asyncio
async def test_visual_system_storage_failure_stays_inside_visual_system_tab(monkeypatch):
    ctx = MockContext()
    brand_id = await _brand(ctx)
    original_workspace_read = m._workspace_for_brand

    async def broken_workspace_read(*args, **kwargs):
        raise RuntimeError("simulated VBS storage failure")

    monkeypatch.setattr(m, "_workspace_for_brand", broken_workspace_read)
    result = await m.brand_detail_panel(ctx, brand_id=brand_id, tab="visual_system")
    rendered = repr(result)

    assert "Visual System data could not load" in rendered
    assert f"brand={brand_id}" in rendered
    assert "stage=workspace: RuntimeError" in rendered

    monkeypatch.setattr(m, "_workspace_for_brand", original_workspace_read)
    profile = await m.brand_detail_panel(ctx, brand_id=brand_id, tab="profile")
    assert "Positioning" in repr(profile)
