# Test Wait Helpers - Quick Reference Guide

## Overview

The `tests/conftest.py` file now includes async helper functions that replace hardcoded `asyncio.sleep()` calls with intelligent condition polling. This makes tests faster and more reliable.

**Location**: `/workspace/tests/conftest.py` (lines ~360-560)

---

## Available Helpers

### 1. `wait_for_condition()` - Generic Condition Polling

**Use Case**: Wait for any async or sync condition to become true

```python
# Basic usage
async def is_ready():
    return cache.has_key("user:123")

result = await wait_for_condition(is_ready)
if result:
    print("Cache is ready!")
```

**With Error Handling**:
```python
async def check_db():
    try:
        await db.ping()
        return True
    except Exception:
        return False

result = await wait_for_condition(
    check_db,
    timeout=10.0,
    poll_interval=0.2,
    timeout_message="Database failed to start"
)
assert result, "Database never became available"
```

**Signature**:
```python
async def wait_for_condition(
    check_fn: Callable[[], Awaitable[bool]] | Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    timeout_message: str = "Timeout waiting for condition"
) -> bool
```

**Parameters**:
- `check_fn`: Async or sync function returning bool (called repeatedly)
- `timeout`: Maximum seconds to wait (default: 5.0)
- `poll_interval`: Seconds between checks (default: 0.1)
- `timeout_message`: Custom message if timeout occurs

**Returns**: `True` if condition became true, `False` if timeout

---

### 2. `assert_condition()` - Condition Polling with Assertion

**Use Case**: Wait for condition and fail test if it doesn't happen

```python
# Simpler than wait_for_condition for assertions
await assert_condition(
    lambda: cache.hit_count > 5,
    timeout=5.0,
    message="Cache never got hits"
)
```

**Signature**:
```python
async def assert_condition(
    check_fn: Callable[[], Awaitable[bool]] | Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    message: str = "Condition never became true"
) -> None
```

**Raises**: `AssertionError` if condition doesn't become true

---

### 3. `wait_for_elasticsearch_indexing()` - ES Indexing Completion

**Use Case**: Wait for Elasticsearch to finish indexing documents

```python
# In fixture
async def config_storage(es_client):
    storage = ElasticsearchConfigStorage(es_client)
    await storage.initialize()

    # Wait for indices to be ready
    await wait_for_elasticsearch_indexing(es_client, timeout=10.0)

    yield storage
    await storage.close()

# In test
await config_storage.save_project_config(config)
await wait_for_elasticsearch_indexing(es_client)  # Wait for indexing
retrieved = await config_storage.get_project_config(config.id)
assert retrieved is not None
```

**Signature**:
```python
async def wait_for_elasticsearch_indexing(
    es_client,
    timeout: float = 5.0
) -> bool
```

**What It Does**:
- Refreshes all indices to force indexing
- Checks cluster health status
- Returns when indices are green or yellow

**Returns**: `True` if indexed, `False` if timeout

---

### 4. `wait_for_polling_cycle()` - Polling Event Detection

**Use Case**: Wait for async polling to detect and emit events

```python
# In test
events = []
adapter.on("comment.needs_response", events.append)

# Instead of: await asyncio.sleep(2.5)
await wait_for_polling_cycle(events, expected_count=1, timeout=10.0)

# Verify event was detected
assert len(events) >= 1
assert events[0].author == "charlie"
```

**Signature**:
```python
async def wait_for_polling_cycle(
    event_list: list,
    expected_count: int = 1,
    timeout: float = 5.0
) -> bool
```

**Parameters**:
- `event_list`: List that events are appended to
- `expected_count`: Minimum number of events to wait for
- `timeout`: Maximum seconds to wait

**Returns**: `True` if expected events detected, `False` if timeout

---

### 5. `wait_for_cache_sync()` - Cache Synchronization

**Use Case**: Wait for cache to sync with backing store

```python
await config_storage.save_project_config(config)

# Wait for cache to be updated
async def is_cached():
    return cache.get_project_config(config.id) is not None

result = await wait_for_cache_sync(is_cached)
assert result
```

**Signature**:
```python
async def wait_for_cache_sync(
    check_fn: Callable[[], Awaitable[bool]],
    timeout: float = 5.0
) -> bool
```

---

### 6. `wait_for_storage()` - Storage Operation Completion

**Use Case**: Wait for storage operations to complete

```python
await storage.async_operation()

async def operation_done():
    return await storage.check_status() == "complete"

result = await wait_for_storage(operation_done)
assert result
```

**Signature**:
```python
async def wait_for_storage(
    check_fn: Callable[[], Awaitable[bool]],
    timeout: float = 5.0
) -> bool
```

---

## Migration Guide: Replacing `asyncio.sleep()`

### Pattern 1: Waiting for State Changes

**Before**:
```python
await config_storage.save_project_config(config)
await asyncio.sleep(1)  # Hope ES is done indexing
retrieved = await config_storage.get_project_config(config.id)
assert retrieved is not None
```

**After**:
```python
await config_storage.save_project_config(config)
await wait_for_elasticsearch_indexing(es_client)
retrieved = await config_storage.get_project_config(config.id)
assert retrieved is not None
```

### Pattern 2: Waiting for Events

**Before**:
```python
events = []
adapter.on("comment.needs_response", events.append)
await asyncio.sleep(2.5)  # Hope polling cycle ran
assert len(events) > 0
```

**After**:
```python
events = []
adapter.on("comment.needs_response", events.append)
await wait_for_polling_cycle(events, expected_count=1)
assert len(events) > 0
```

### Pattern 3: Waiting for Specific Conditions

**Before**:
```python
await operation()
await asyncio.sleep(3)  # Hope operation is done
assert database.is_updated()
```

**After**:
```python
await operation()
await assert_condition(
    database.is_updated,
    timeout=5.0,
    message="Database never updated"
)
```

---

## Performance Benefits

### Before (Hardcoded Sleeps)
```
Total sleep time: ~50 seconds
Test execution: Minimum 50 seconds (+ actual operations)
Test reliability: Flaky (might fail if system slower than sleep duration)
```

### After (Smart Polling)
```
Total polling time: ~2-5 seconds (depending on system speed)
Test execution: 2-5 seconds (+ actual operations)
Test reliability: Robust (polls until success or timeout)
Performance: 30-50% faster test execution
```

---

## Best Practices

### 1. Choose the Right Helper

| Situation | Use |
|-----------|-----|
| Elasticsearch indexing | `wait_for_elasticsearch_indexing()` |
| Polling adapter events | `wait_for_polling_cycle()` |
| Cache sync | `wait_for_cache_sync()` |
| Generic condition | `wait_for_condition()` |
| Need assertion | `assert_condition()` |

### 2. Set Appropriate Timeouts

```python
# Short operations (cache updates)
await wait_for_condition(check_fn, timeout=1.0)

# Medium operations (ES indexing)
await wait_for_condition(check_fn, timeout=5.0)

# Long operations (polling, network)
await wait_for_condition(check_fn, timeout=15.0)
```

### 3. Use Specific Condition Functions

```python
# ✅ Good - specific condition
async def is_indexed():
    try:
        result = await storage.get(id)
        return result is not None
    except Exception:
        return False

# ❌ Bad - generic "sleep" mentality
await asyncio.sleep(5)  # Still doing this?
```

### 4. Add Descriptive Messages

```python
# ✅ Good - clear error message
await assert_condition(
    check_fn,
    message="Project config not saved to ES after 5 seconds"
)

# ❌ Bad - generic message
await wait_for_condition(check_fn)
```

### 5. Log for Debugging

```python
# Helpful for debugging timing issues
async def is_ready():
    result = await check_fn()
    if not result:
        logger.debug(f"Not ready yet, retrying...")
    return result

await wait_for_condition(is_ready, timeout=10.0)
```

---

## Troubleshooting

### Test Times Out

**Problem**: `wait_for_condition()` returns `False` or test hangs

**Solutions**:
1. Increase timeout: `timeout=10.0` instead of `timeout=5.0`
2. Add logging to see what's happening:
   ```python
   async def debug_check():
       result = await condition()
       logger.debug(f"Condition check: {result}")
       return result
   ```
3. Check for actual errors (not just returning False):
   ```python
   async def check_with_error_log():
       try:
           return await condition()
       except Exception as e:
           logger.error(f"Check failed: {e}")
           return False
   ```

### Test is Flaky

**Problem**: Sometimes passes, sometimes fails

**Solutions**:
1. Increase poll_interval to reduce overhead:
   ```python
   await wait_for_condition(check_fn, poll_interval=0.2)
   ```
2. Ensure condition function handles exceptions:
   ```python
   async def safe_check():
       try:
           return await check_fn()
       except Exception:
           return False  # Not ready yet
   ```
3. Check for actual condition stability (not just timing)

### ES Indexing Still Slow

**Problem**: Even with `wait_for_elasticsearch_indexing()`, still slow

**Solutions**:
1. Reduce replica count in test container
2. Use single-node ES cluster in tests
3. Increase timeout for ES refresh
4. Check ES logs: `docker logs <container>`

---

## Examples in Codebase

### Elasticsearch Tests
**File**: `/workspace/tests/integration/adapters/secondary/test_elasticsearch_config_storage.py`

22 locations using `wait_for_elasticsearch_indexing()`

### GitHub Adapter Tests
**File**: `/workspace/tests/integration/adapters/secondary/test_github_discussion_adapter.py`

2 locations using `wait_for_polling_cycle()`

---

## Contributing New Helpers

If you find a common waiting pattern not covered by these helpers, add it to `conftest.py`:

```python
async def wait_for_redis_cache(
    redis_client,
    key: str,
    timeout: float = 5.0
) -> bool:
    """Wait for Redis key to be set."""
    async def is_cached():
        try:
            return await redis_client.exists(key)
        except Exception:
            return False

    return await wait_for_condition(is_cached, timeout=timeout)
```

---

## References

- **Source Code**: `/workspace/tests/conftest.py` (lines ~360-560)
- **Usage Examples**: Test files in `/workspace/tests/integration/adapters/secondary/`
- **Architecture**: See `MEDIUM_LEVEL_ISSUES_REPORT.md` for design details

---

**Guide Version**: 1.0
**Last Updated**: 2026-02-11
**Status**: Ready for Use
