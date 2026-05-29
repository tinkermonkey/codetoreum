"""Unit tests for MinioStorageAdapter using a mocked minio.Minio client.

These tests do NOT spin up Minio.  They mock the minio client surface so
the adapter's IStorage contract, event emission, error mapping, and
async-thread wrapping are validated without a live S3 endpoint.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.secondary.minio_storage_adapter import (
    MinioStorageAdapter,
    _is_not_found,
)
from codetoreum.domain.events.storage_events import ArtifactDeletedEvent, ArtifactUploadedEvent
from codetoreum.ports.exceptions import ResourceNotFoundError, StorageError


class _CapturingEmitter:
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)

    # The IEventEmitter port has additional methods (on, off, etc.)
    # but the adapter only calls emit().  Stubbing the rest would be
    # noise; the adapter ignores them.
    def on(self, *args, **kwargs) -> None:
        pass

    def off(self, *args, **kwargs) -> None:
        pass


class _FakeMinioObject:
    """Match the duck-type surface MinioStorageAdapter expects on list/stat results."""

    def __init__(
        self,
        object_name: str,
        size: int = 0,
        last_modified: datetime | None = None,
        is_dir: bool = False,
        etag: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.object_name = object_name
        self.size = size
        self.last_modified = last_modified or datetime.now(UTC)
        self.is_dir = is_dir
        self.etag = etag
        self.content_type = content_type
        self.metadata = metadata or {}


def _fake_minio_client() -> MagicMock:
    """Build a MagicMock standing in for minio.Minio."""

    client = MagicMock()
    storage: dict[str, dict] = {}

    def bucket_exists(_bucket: str) -> bool:
        return True

    def make_bucket(_bucket: str) -> None:
        pass

    def put_object(_bucket, key, stream, length, content_type=None, metadata=None):
        storage[key] = {
            "content": stream.read(),
            "content_type": content_type or "application/octet-stream",
            "metadata": dict(metadata or {}),
            "size": length,
            "last_modified": datetime.now(UTC),
        }

    def fput_object(_bucket, key, file_path, content_type=None, metadata=None):
        with open(file_path, "rb") as fh:
            content = fh.read()
        storage[key] = {
            "content": content,
            "content_type": content_type or "application/octet-stream",
            "metadata": dict(metadata or {}),
            "size": len(content),
            "last_modified": datetime.now(UTC),
        }

    def get_object(_bucket, key):
        if key not in storage:
            raise _FakeS3Error("NoSuchKey", 404)
        return _FakeResponse(storage[key]["content"])

    def fget_object(_bucket, key, file_path):
        if key not in storage:
            raise _FakeS3Error("NoSuchKey", 404)
        Path(file_path).write_bytes(storage[key]["content"])

    def stat_object(_bucket, key):
        if key not in storage:
            raise _FakeS3Error("NoSuchKey", 404)
        rec = storage[key]
        return SimpleNamespace(
            size=rec["size"],
            content_type=rec["content_type"],
            metadata=rec["metadata"],
            last_modified=rec["last_modified"],
            etag=f"etag-{key}",
        )

    def remove_object(_bucket, key):
        storage.pop(key, None)

    def remove_objects(_bucket, delete_objects):
        for obj in delete_objects:
            storage.pop(obj.object_name, None)
        return []  # No errors

    def list_objects(_bucket, prefix=None, recursive=True):
        items = []
        for key, rec in storage.items():
            if prefix and not key.startswith(prefix):
                continue
            items.append(
                _FakeMinioObject(
                    object_name=key,
                    size=rec["size"],
                    last_modified=rec["last_modified"],
                    content_type=rec["content_type"],
                    etag=f"etag-{key}",
                )
            )
        return iter(items)

    def copy_object(_bucket, dest_key, copy_source, metadata=None, metadata_directive=None):
        src_key = copy_source.object_name
        if src_key not in storage:
            raise _FakeS3Error("NoSuchKey", 404)
        new_record = dict(storage[src_key])
        if (metadata is not None and metadata_directive == "REPLACE") or metadata is not None:
            new_record["metadata"] = dict(metadata)
        new_record["last_modified"] = datetime.now(UTC)
        storage[dest_key] = new_record

    def presigned_get_object(_bucket, key, expires):
        return f"https://example.com/get/{key}?expires={int(expires.total_seconds())}"

    def presigned_put_object(_bucket, key, expires):
        return f"https://example.com/put/{key}?expires={int(expires.total_seconds())}"

    client.bucket_exists.side_effect = bucket_exists
    client.make_bucket.side_effect = make_bucket
    client.put_object.side_effect = put_object
    client.fput_object.side_effect = fput_object
    client.get_object.side_effect = get_object
    client.fget_object.side_effect = fget_object
    client.stat_object.side_effect = stat_object
    client.remove_object.side_effect = remove_object
    client.remove_objects.side_effect = remove_objects
    client.list_objects.side_effect = list_objects
    client.copy_object.side_effect = copy_object
    client.presigned_get_object.side_effect = presigned_get_object
    client.presigned_put_object.side_effect = presigned_put_object
    client._storage = storage  # Expose for tests
    return client


class _FakeS3Error(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        return self._content

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


# Patch CopySource since minio.commonconfig is imported lazily
@pytest.fixture(autouse=True)
def _patch_minio_commonconfig(monkeypatch):
    """Stub minio.commonconfig.CopySource so copy_object code paths work."""

    class _StubCopySource:
        def __init__(self, bucket: str, object_name: str) -> None:
            self.bucket = bucket
            self.object_name = object_name

    import sys
    import types

    common = types.ModuleType("minio.commonconfig")
    common.CopySource = _StubCopySource
    common.REPLACE = "REPLACE"
    monkeypatch.setitem(sys.modules, "minio.commonconfig", common)

    # Also patch deleteobjects
    delete_mod = types.ModuleType("minio.deleteobjects")

    class _StubDeleteObject:
        def __init__(self, object_name: str) -> None:
            self.object_name = object_name

    delete_mod.DeleteObject = _StubDeleteObject
    monkeypatch.setitem(sys.modules, "minio.deleteobjects", delete_mod)


@pytest.fixture
def emitter() -> _CapturingEmitter:
    return _CapturingEmitter()


@pytest.fixture
def client():
    return _fake_minio_client()


@pytest.fixture
def adapter(client, emitter: _CapturingEmitter) -> MinioStorageAdapter:
    return MinioStorageAdapter(
        client=client,
        bucket="test-bucket",
        event_emitter=emitter,
        ensure_bucket=False,  # Avoid extra bucket_exists call in tests
    )


class TestUploadDownload:
    @pytest.mark.asyncio
    async def test_upload_then_download_round_trips_bytes(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("logs/run-1.txt", b"hello world", content_type="text/plain")
        content = await adapter.download("logs/run-1.txt")
        assert content == b"hello world"

    @pytest.mark.asyncio
    async def test_upload_emits_artifact_uploaded_event(
        self,
        adapter: MinioStorageAdapter,
        emitter: _CapturingEmitter,
    ) -> None:
        await adapter.upload("k", b"hi", content_type="text/plain")
        assert any(isinstance(e, ArtifactUploadedEvent) for e in emitter.events)
        event = next(e for e in emitter.events if isinstance(e, ArtifactUploadedEvent))
        assert event.key == "k"
        assert event.size_bytes == 2
        assert event.content_type == "text/plain"
        assert event.source == "minio"

    @pytest.mark.asyncio
    async def test_download_missing_raises_resource_not_found(self, adapter: MinioStorageAdapter) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.download("does-not-exist")

    @pytest.mark.asyncio
    async def test_upload_from_file_persists_content(
        self,
        adapter: MinioStorageAdapter,
        tmp_path: Path,
    ) -> None:
        local = tmp_path / "x.txt"
        local.write_text("content")
        await adapter.upload_from_file("k", local, content_type="text/plain")
        assert await adapter.download("k") == b"content"

    @pytest.mark.asyncio
    async def test_upload_from_file_missing_raises_resource_not_found(
        self,
        adapter: MinioStorageAdapter,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.upload_from_file("k", tmp_path / "missing.txt")


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing_emits_event(
        self,
        adapter: MinioStorageAdapter,
        emitter: _CapturingEmitter,
    ) -> None:
        await adapter.upload("k", b"x", content_type="text/plain")
        emitter.events.clear()
        await adapter.delete("k")
        assert any(isinstance(e, ArtifactDeletedEvent) for e in emitter.events)
        assert await adapter.exists("k") is False

    @pytest.mark.asyncio
    async def test_delete_missing_raises_resource_not_found(self, adapter: MinioStorageAdapter) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.delete("missing")

    @pytest.mark.asyncio
    async def test_delete_many_removes_objects(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("a", b"1", content_type="text/plain")
        await adapter.upload("b", b"2", content_type="text/plain")
        await adapter.delete_many(["a", "b", "missing"])
        assert await adapter.exists("a") is False
        assert await adapter.exists("b") is False


class TestPresignedUrls:
    @pytest.mark.asyncio
    async def test_get_url_is_real_http(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("k", b"x", content_type="text/plain")
        url = await adapter.generate_presigned_url("k", expires_in=900, method="GET")
        assert url.startswith("https://example.com/get/k?expires=900")

    @pytest.mark.asyncio
    async def test_put_url_supported(self, adapter: MinioStorageAdapter) -> None:
        url = await adapter.generate_presigned_url("future-key", expires_in=300, method="PUT")
        assert url.startswith("https://example.com/put/future-key")

    @pytest.mark.asyncio
    async def test_unsupported_method_raises_storage_error(self, adapter: MinioStorageAdapter) -> None:
        with pytest.raises(StorageError):
            await adapter.generate_presigned_url("k", method="DELETE")


class TestListAndQuery:
    @pytest.mark.asyncio
    async def test_list_files_filters_by_prefix(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("logs/a", b"a", content_type="text/plain")
        await adapter.upload("logs/b", b"b", content_type="text/plain")
        await adapter.upload("other/c", b"c", content_type="text/plain")
        results = await adapter.list_files(prefix="logs/")
        assert sorted(r.key for r in results) == ["logs/a", "logs/b"]

    @pytest.mark.asyncio
    async def test_exists_returns_true_only_when_present(self, adapter: MinioStorageAdapter) -> None:
        assert await adapter.exists("nope") is False
        await adapter.upload("yes", b"x", content_type="text/plain")
        assert await adapter.exists("yes") is True

    @pytest.mark.asyncio
    async def test_get_size_and_content_type(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("k", b"hello", content_type="text/markdown")
        assert await adapter.get_size("k") == 5
        assert await adapter.get_content_type("k") == "text/markdown"

    @pytest.mark.asyncio
    async def test_get_storage_info_reports_counts(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("a", b"123", content_type="text/plain")
        await adapter.upload("b", b"4567", content_type="text/plain")
        info = await adapter.get_storage_info()
        assert info["provider"] == "minio"
        assert info["object_count"] == 2
        assert info["total_size_bytes"] == 7


class TestCopyMove:
    @pytest.mark.asyncio
    async def test_copy_creates_new_object(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("src", b"hello", content_type="text/plain")
        await adapter.copy("src", "dest")
        assert await adapter.exists("src") is True
        assert await adapter.exists("dest") is True

    @pytest.mark.asyncio
    async def test_move_removes_source(self, adapter: MinioStorageAdapter) -> None:
        await adapter.upload("src", b"x", content_type="text/plain")
        await adapter.move("src", "dest")
        assert await adapter.exists("src") is False
        assert await adapter.exists("dest") is True


class TestBucketBootstrap:
    @pytest.mark.asyncio
    async def test_ensure_bucket_creates_when_missing(self, emitter: _CapturingEmitter) -> None:
        client = _fake_minio_client()
        client.bucket_exists.side_effect = lambda _b: False
        adapter = MinioStorageAdapter(client=client, bucket="new-bucket", event_emitter=emitter)
        await adapter.upload("k", b"x", content_type="text/plain")
        client.make_bucket.assert_called_with("new-bucket")


class TestErrorHelpers:
    def test_is_not_found_recognizes_s3_codes(self) -> None:
        assert _is_not_found(_FakeS3Error("NoSuchKey", 404)) is True
        assert _is_not_found(_FakeS3Error("NoSuchObject", 404)) is True
        assert _is_not_found(_FakeS3Error("AccessDenied", 403)) is False
