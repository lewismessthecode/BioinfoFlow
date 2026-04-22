"""Tests for BaseRepository bulk operations and error handling."""

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.repositories.base import BaseRepository


# Test model setup
class Base(DeclarativeBase):
    pass


class _TestModel(Base):
    __tablename__ = "test_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    value = Column(String(100), nullable=True)


class _TestModelRepository(BaseRepository[_TestModel]):
    model = _TestModel


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
def repository(async_session: AsyncSession):
    """Create a repository instance for testing."""
    return _TestModelRepository(async_session)


class TestBulkCreate:
    """Tests for bulk_create method."""

    @pytest.mark.asyncio
    async def test_bulk_create_empty_list(self, repository: _TestModelRepository):
        """Test bulk_create with empty list returns empty list."""
        result = await repository.bulk_create([])
        assert result == []

    @pytest.mark.asyncio
    async def test_bulk_create_single_item(
        self, repository: _TestModelRepository, async_session: AsyncSession
    ):
        """Test bulk_create with single item."""
        items = [{"name": "item1", "value": "value1"}]
        result = await repository.bulk_create(items)

        assert len(result) == 1
        assert result[0].name == "item1"
        assert result[0].value == "value1"
        assert result[0].id is not None

        # Verify it was actually saved to DB
        stmt = select(_TestModel).where(_TestModel.name == "item1")
        db_result = await async_session.execute(stmt)
        db_item = db_result.scalar_one_or_none()
        assert db_item is not None
        assert db_item.name == "item1"

    @pytest.mark.asyncio
    async def test_bulk_create_multiple_items(
        self, repository: _TestModelRepository, async_session: AsyncSession
    ):
        """Test bulk_create with multiple items."""
        items = [
            {"name": "item1", "value": "value1"},
            {"name": "item2", "value": "value2"},
            {"name": "item3", "value": "value3"},
        ]
        result = await repository.bulk_create(items)

        assert len(result) == 3
        assert [r.name for r in result] == ["item1", "item2", "item3"]
        assert all(r.id is not None for r in result)

        # Verify all were saved to DB
        stmt = select(_TestModel)
        db_result = await async_session.execute(stmt)
        db_items = db_result.scalars().all()
        assert len(db_items) == 3

    @pytest.mark.asyncio
    async def test_bulk_create_with_optional_fields(
        self, repository: _TestModelRepository
    ):
        """Test bulk_create with optional fields."""
        items = [
            {"name": "item1"},  # No value field
            {"name": "item2", "value": "value2"},
        ]
        result = await repository.bulk_create(items)

        assert len(result) == 2
        assert result[0].value is None
        assert result[1].value == "value2"

    @pytest.mark.asyncio
    async def test_bulk_create_transaction_rollback_on_error(
        self, repository: _TestModelRepository, async_session: AsyncSession
    ):
        """Test that bulk_create rolls back on error."""
        items = [
            {"name": "item1"},
            {"name": None},  # This will fail - NOT NULL constraint
            {"name": "item3"},
        ]

        with pytest.raises(Exception):
            await repository.bulk_create(items)

        # Verify nothing was committed to DB
        stmt = select(_TestModel)
        db_result = await async_session.execute(stmt)
        db_items = db_result.scalars().all()
        assert len(db_items) == 0

    @pytest.mark.asyncio
    async def test_bulk_create_invalid_field_raises_error(
        self, repository: _TestModelRepository
    ):
        """Test bulk_create with invalid field raises error."""
        items = [
            {"name": "item1", "invalid_field": "value"},
        ]

        with pytest.raises(TypeError):
            await repository.bulk_create(items)

    @pytest.mark.asyncio
    async def test_bulk_create_missing_required_field(
        self, repository: _TestModelRepository
    ):
        """Test bulk_create with missing required field raises error."""
        items = [
            {"value": "value1"},  # Missing required 'name' field
        ]

        with pytest.raises(Exception):
            await repository.bulk_create(items)


class TestAgentTraceBatching:
    """Tests for agent trace batching functionality using TestModel."""

    @pytest.mark.asyncio
    async def test_bulk_create_batching(
        self, repository: _TestModelRepository, async_session: AsyncSession
    ):
        """Test that bulk_create batches multiple items successfully."""
        # Simulate batch writes like trace recording
        items = [{"name": f"trace_{i}", "value": f"data_{i}"} for i in range(10)]

        # This should succeed with all items in one transaction
        result = await repository.bulk_create(items)
        assert len(result) == 10

        # Verify all were saved
        stmt = select(_TestModel)
        db_result = await async_session.execute(stmt)
        db_items = db_result.scalars().all()
        assert len(db_items) == 10

    @pytest.mark.asyncio
    async def test_bulk_create_atomic_transaction(
        self, repository: _TestModelRepository, async_session: AsyncSession
    ):
        """Test that bulk_create is atomic - all or nothing."""
        # Mix of valid and invalid items
        items = [
            {"name": "item1", "value": "value1"},
            {"name": "item2", "value": "value2"},
            {"name": None, "value": "value3"},  # Invalid - will fail
            {"name": "item4", "value": "value4"},
        ]

        # Should fail and rollback all
        with pytest.raises(Exception):
            await repository.bulk_create(items)

        # Verify nothing was saved
        stmt = select(_TestModel)
        db_result = await async_session.execute(stmt)
        assert len(db_result.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_bulk_create_performance(self, repository: _TestModelRepository):
        """Test that bulk_create handles larger batches."""
        # Simulate flushing 100 queued items at once
        items = [{"name": f"item_{i}", "value": f"value_{i}"} for i in range(100)]

        result = await repository.bulk_create(items)
        assert len(result) == 100
        assert all(r.id is not None for r in result)

    @pytest.mark.asyncio
    async def test_empty_bulk_create(self, repository: _TestModelRepository):
        """Test that empty bulk_create is safe."""
        result = await repository.bulk_create([])
        assert result == []
