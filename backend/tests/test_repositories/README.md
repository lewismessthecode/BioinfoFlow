# Repository Tests

## Test Coverage

This directory contains comprehensive tests for repository-level operations.

### test_base_repository.py

Tests for `BaseRepository` bulk operations and error handling (11 tests, all passing).

#### TestBulkCreate (7 tests)
- `test_bulk_create_empty_list` - Handles empty input gracefully
- `test_bulk_create_single_item` - Creates and persists single item
- `test_bulk_create_multiple_items` - Batches multiple items in one transaction
- `test_bulk_create_with_optional_fields` - Handles optional fields correctly
- `test_bulk_create_transaction_rollback_on_error` - Verifies atomic rollback on failure
- `test_bulk_create_invalid_field_raises_error` - Validates field names
- `test_bulk_create_missing_required_field` - Enforces required fields

#### TestAgentTraceBatching (4 tests)
- `test_bulk_create_batching` - Batches 10 items successfully
- `test_bulk_create_atomic_transaction` - All-or-nothing transaction semantics
- `test_bulk_create_performance` - Handles 100-item batch
- `test_empty_bulk_create` - Safe empty batch handling

## Running Tests

```bash
# Run all repository tests
uv run pytest tests/test_repositories/ -v

# Run specific test file
uv run pytest tests/test_repositories/test_base_repository.py -v

# Run specific test
uv run pytest tests/test_repositories/test_base_repository.py::TestBulkCreate::test_bulk_create_transaction_rollback_on_error -v
```

## Implementation Details

### BaseRepository.bulk_create()

The `bulk_create` method in `app/repositories/base.py` provides:

1. **Batch Operations**: Create multiple records in a single database transaction
2. **Error Handling**: Automatic rollback on validation or constraint errors
3. **Type Safety**: Leverages SQLAlchemy model typing via Generic[ModelT]

### AgentTraceRecorder Batching

The `AgentTraceRecorder` in `app/services/agent/trace.py` uses `bulk_create` to:

1. **Queue tool traces** during parallel execution (via `queue_tool()`)
2. **Flush batches** at the end of agent turns (via `flush()`)
3. **Prevent race conditions** - avoids UNIQUE constraint errors from parallel tool execution

## Test Methodology

All tests use:
- In-memory SQLite database (`sqlite+aiosqlite:///:memory:`)
- pytest-asyncio for async test support
- Test-specific models (prefixed with `_` to avoid collection as tests)
- Isolated sessions per test for clean state
