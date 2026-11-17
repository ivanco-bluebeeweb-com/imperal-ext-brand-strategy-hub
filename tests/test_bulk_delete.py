import pytest
from unittest.mock import AsyncMock, MagicMock
from schemas import BulkDeleteBrandProfilesParams, BulkDeleteResult
from main import bulk_delete_brand_profiles


@pytest.mark.asyncio
async def test_bulk_delete_empty_brand_ids():
    ctx = MagicMock()
    params = BulkDeleteBrandProfilesParams(brand_ids=[])
    result = await bulk_delete_brand_profiles(ctx, params)
    assert result.status == "error"
    assert "No brand IDs provided" in result.error


@pytest.mark.asyncio
async def test_bulk_delete_success():
    ctx = MagicMock()
    ctx.store = MagicMock()

    # Brand 1 exists, Brand 2 exists
    async def mock_get(collection, doc_id):
        if collection == "brand_profiles" and doc_id in ("brand-1", "brand-2"):
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.data = {"brand_name": f"Brand {doc_id}"}
            return mock_doc
        return None

    # Empty dependent collections
    mock_page = MagicMock()
    mock_page.data = []
    ctx.store.get = AsyncMock(side_effect=mock_get)
    ctx.store.query = AsyncMock(return_value=mock_page)
    ctx.store.delete = AsyncMock()

    params = BulkDeleteBrandProfilesParams(brand_ids=["brand-1", "brand-2"])
    result = await bulk_delete_brand_profiles(ctx, params)

    assert result.status == "success"
    assert isinstance(result.data, BulkDeleteResult)
    assert result.data.deleted_count == 2
    assert "brand-1" in result.data.deleted_ids
    assert "brand-2" in result.data.deleted_ids
    assert len(result.data.failed_ids) == 0


@pytest.mark.asyncio
async def test_bulk_delete_partial_failure():
    ctx = MagicMock()
    ctx.store = MagicMock()

    async def mock_get(collection, doc_id):
        if collection == "brand_profiles" and doc_id == "brand-1":
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.data = {"brand_name": "Brand 1"}
            return mock_doc
        return None

    mock_page = MagicMock()
    mock_page.data = []
    ctx.store.get = AsyncMock(side_effect=mock_get)
    ctx.store.query = AsyncMock(return_value=mock_page)
    ctx.store.delete = AsyncMock()

    params = BulkDeleteBrandProfilesParams(brand_ids=["brand-1", "brand-missing"])
    result = await bulk_delete_brand_profiles(ctx, params)

    assert result.status == "success"
    assert result.data.deleted_count == 1
    assert "brand-1" in result.data.deleted_ids
    assert "brand-missing" in result.data.failed_ids
    assert len(result.data.errors) == 1
