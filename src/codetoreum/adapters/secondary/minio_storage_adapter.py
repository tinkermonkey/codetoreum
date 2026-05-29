"""MinioStorageAdapter — production IStorage backed by Minio (S3-compatible).

Closes the artifact-storage gap of ``InMemoryStorageAdapter``:
agent execution logs, structured outputs, and other artifacts persist
to a real object store and survive server restart.  Presigned URLs
are real S3-style URLs (not the ``memory://`` placeholders the
in-memory adapter returned), so external tools can fetch artifacts
directly.

Design notes
------------
- INV-09: explicit inheritance from ``IStorage``.
- INV-11: no retry/circuit-breaker logic embedded — the synchronous
  ``minio.Minio`` client is wrapped with ``asyncio.to_thread`` so the
  adapter surface stays async without blocking the event loop, and
  the existing storage resilience decorator can wrap it like any other
  ``IStorage``.
- INV-10: ``upload`` / ``delete`` / ``copy`` emit ``ArtifactUploadedEvent``
  / ``ArtifactDeletedEvent`` frozen-dataclass domain events.
- INV-12: no imports of domain-internal modules.

Configuration
-------------
Environment variables consumed by ``AdapterResolver.resolve_storage``:
- ``MINIO_ENDPOINT`` — host:port (default ``localhost:9000``)
- ``MINIO_ACCESS_KEY`` — root user
- ``MINIO_SECRET_KEY`` — root password
- ``MINIO_BUCKET`` — bucket name (default ``codetoreum-artifacts``)
- ``MINIO_SECURE`` — ``true`` / ``false`` for HTTPS (default ``false``)
"""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codetoreum.domain.events.storage_events import ArtifactDeletedEvent, ArtifactUploadedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.exceptions import ResourceNotFoundError, StorageError
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.storage import IStorage, StorageObject

if TYPE_CHECKING:
    from minio import Minio

logger = logging.getLogger(__name__)


DEFAULT_BUCKET = "codetoreum-artifacts"


class MinioStorageAdapter(IStorage):
    """Production IStorage implementation backed by Minio (S3-compatible).

    The synchronous ``minio.Minio`` client is wrapped with
    ``asyncio.to_thread`` so the adapter exposes the async ``IStorage``
    surface without blocking the event loop.
    """

    def __init__(
        self,
        client: Minio,
        bucket: str = DEFAULT_BUCKET,
        event_emitter: IEventEmitter | None = None,
        event_bus: EventBus | None = None,
        ensure_bucket: bool = True,
    ) -> None:
        """Initialize the adapter.

        Args:
            client: Configured ``minio.Minio`` client instance.
            bucket: Name of the bucket to use for artifact storage.
            event_emitter: Optional emitter for ArtifactUploaded/Deleted events.
            event_bus: Optional event bus for subscribing to ContainerExecutionCompletedEvent.
            ensure_bucket: When True (default), create the bucket if it
                does not already exist.  Set to False if the operator
                has provisioned the bucket out-of-band.
        """
        self._client = client
        self._bucket = bucket
        self._event_emitter = event_emitter
        self._event_bus = event_bus
        self._bucket_ready = False
        self._bucket_ready_lock = threading.Lock()
        self._ensure_bucket_on_first_call = ensure_bucket

    # ------------------------------------------------------------------
    # IStorage
    # ------------------------------------------------------------------

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        await self._ensure_bucket()
        resolved_content_type = content_type or "application/octet-stream"
        size = len(content)
        try:
            await asyncio.to_thread(
                self._put_object_bytes,
                key,
                content,
                resolved_content_type,
                metadata,
            )
        except Exception as e:
            logger.error(
                f"Minio upload failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_UPLOAD_FAILED"},
            )
            raise StorageError(f"Minio upload failed: {e}") from e

        self._emit(
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=datetime.now(UTC).isoformat(),
                source="minio",
                key=key,
                size_bytes=size,
                content_type=resolved_content_type,
                project_id=(metadata or {}).get("project_id"),
            )
        )

    async def upload_from_file(
        self,
        key: str,
        file_path: Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if not file_path.exists():
            raise ResourceNotFoundError("File", str(file_path))
        resolved_content_type = content_type or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        await self._ensure_bucket()
        try:
            await asyncio.to_thread(
                self._client.fput_object,
                self._bucket,
                key,
                str(file_path),
                content_type=resolved_content_type,
                metadata=metadata,
            )
        except Exception as e:
            logger.error(
                f"Minio fput_object failed for key={key} path={file_path}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_UPLOAD_FAILED"},
            )
            raise StorageError(f"Minio upload failed: {e}") from e

        size = file_path.stat().st_size
        self._emit(
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=datetime.now(UTC).isoformat(),
                source="minio",
                key=key,
                size_bytes=size,
                content_type=resolved_content_type,
                project_id=(metadata or {}).get("project_id"),
            )
        )

    async def download(self, key: str) -> bytes:
        await self._ensure_bucket()
        try:
            return await asyncio.to_thread(self._get_object_bytes, key)
        except _NotFound:
            raise ResourceNotFoundError("Artifact", key)
        except Exception as e:
            logger.error(
                f"Minio download failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_DOWNLOAD_FAILED"},
            )
            raise StorageError(f"Minio download failed: {e}") from e

    async def download_to_file(self, key: str, file_path: Path) -> None:
        await self._ensure_bucket()
        try:
            await asyncio.to_thread(self._client.fget_object, self._bucket, key, str(file_path))
        except _NotFound:
            raise ResourceNotFoundError("Artifact", key)
        except Exception as e:
            if _is_not_found(e):
                raise ResourceNotFoundError("Artifact", key) from e
            logger.error(
                f"Minio fget_object failed for key={key} path={file_path}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_DOWNLOAD_FAILED"},
            )
            raise StorageError(f"Minio download failed: {e}") from e

    async def delete(self, key: str) -> None:
        await self._ensure_bucket()
        # Verify presence first so callers get ResourceNotFoundError per the
        # IStorage contract (Minio's remove_object is idempotent).
        if not await self.exists(key):
            raise ResourceNotFoundError("Artifact", key)
        try:
            await asyncio.to_thread(self._client.remove_object, self._bucket, key)
        except Exception as e:
            logger.error(
                f"Minio remove_object failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_DELETE_FAILED"},
            )
            raise StorageError(f"Minio delete failed: {e}") from e
        self._emit(
            ArtifactDeletedEvent(
                type="storage.artifact_deleted",
                timestamp=datetime.now(UTC).isoformat(),
                source="minio",
                key=key,
                project_id=None,
            )
        )

    async def delete_many(self, keys: list[str]) -> None:
        await self._ensure_bucket()
        if not keys:
            return
        from minio.deleteobjects import DeleteObject

        delete_objects = [DeleteObject(k) for k in keys]
        try:
            # remove_objects returns an iterator of errors; consume it.
            errors = await asyncio.to_thread(lambda: list(self._client.remove_objects(self._bucket, delete_objects)))
        except Exception as e:
            logger.error(
                f"Minio remove_objects failed: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_DELETE_FAILED"},
            )
            raise StorageError(f"Minio delete_many failed: {e}") from e

        for err in errors:
            logger.warning(
                f"Minio delete_many partial failure: object={err.object_name} message={err.message}",
            )

        # Emit one ArtifactDeletedEvent per successfully-deleted key.
        failed_keys = {err.object_name for err in errors}
        for key in keys:
            if key in failed_keys:
                continue
            self._emit(
                ArtifactDeletedEvent(
                    type="storage.artifact_deleted",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="minio",
                    key=key,
                    project_id=None,
                )
            )

    async def list_files(
        self,
        prefix: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[StorageObject]:
        await self._ensure_bucket()
        try:
            objects = await asyncio.to_thread(self._list_objects_to_list, prefix)
        except Exception as e:
            logger.error(
                f"Minio list_objects failed prefix={prefix}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_LIST_FAILED"},
            )
            raise StorageError(f"Minio list failed: {e}") from e

        # Sort by key for stable pagination, then apply offset/limit.
        objects.sort(key=lambda o: o.object_name or "")
        sliced = objects[offset : offset + limit]
        return [
            StorageObject(
                key=o.object_name or "",
                size=int(o.size or 0),
                last_modified=o.last_modified or datetime.now(UTC),
                content_type=getattr(o, "content_type", None),
                metadata={},
                etag=getattr(o, "etag", None),
            )
            for o in sliced
        ]

    async def exists(self, key: str) -> bool:
        await self._ensure_bucket()
        try:
            await asyncio.to_thread(self._client.stat_object, self._bucket, key)
            return True
        except Exception as e:
            if _is_not_found(e):
                return False
            logger.error(
                f"Minio stat_object failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_QUERY_FAILED"},
            )
            raise StorageError(f"Minio exists failed: {e}") from e

    async def get_metadata(self, key: str) -> dict[str, Any]:
        await self._ensure_bucket()
        try:
            stat = await asyncio.to_thread(self._client.stat_object, self._bucket, key)
        except Exception as e:
            if _is_not_found(e):
                raise ResourceNotFoundError("Object", key) from e
            logger.error(
                f"Minio stat_object failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_QUERY_FAILED"},
            )
            raise StorageError(f"Minio get_metadata failed: {e}") from e
        return {
            "size": int(stat.size or 0),
            "content_type": getattr(stat, "content_type", "application/octet-stream"),
            "metadata": dict(stat.metadata or {}),
            "last_modified": stat.last_modified,
            "etag": getattr(stat, "etag", None),
        }

    async def update_metadata(
        self,
        key: str,
        metadata: dict[str, str],
    ) -> None:
        """Update metadata by overwriting the object with copy-in-place."""
        await self._ensure_bucket()
        if not await self.exists(key):
            raise ResourceNotFoundError("Object", key)
        from minio.commonconfig import REPLACE, CopySource

        try:
            await asyncio.to_thread(
                self._client.copy_object,
                self._bucket,
                key,
                CopySource(self._bucket, key),
                metadata=metadata,
                metadata_directive=REPLACE,
            )
        except Exception as e:
            logger.error(
                f"Minio update_metadata copy_object failed for key={key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_UPDATE_METADATA_FAILED"},
            )
            raise StorageError(f"Minio update_metadata failed: {e}") from e

    async def copy(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        await self._ensure_bucket()
        if not await self.exists(source_key):
            raise ResourceNotFoundError("Source", source_key)
        from minio.commonconfig import CopySource

        try:
            await asyncio.to_thread(
                self._client.copy_object,
                self._bucket,
                destination_key,
                CopySource(self._bucket, source_key),
            )
        except Exception as e:
            logger.error(
                f"Minio copy_object failed source={source_key} dest={destination_key}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_COPY_FAILED"},
            )
            raise StorageError(f"Minio copy failed: {e}") from e

        try:
            meta = await self.get_metadata(destination_key)
            size = int(meta.get("size", 0))
            content_type = str(meta.get("content_type") or "application/octet-stream")
        except StorageError:
            size = 0
            content_type = "application/octet-stream"

        self._emit(
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=datetime.now(UTC).isoformat(),
                source="minio",
                key=destination_key,
                size_bytes=size,
                content_type=content_type,
                project_id=None,
            )
        )

    async def move(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        await self.copy(source_key, destination_key)
        await self.delete(source_key)

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET",
    ) -> str:
        await self._ensure_bucket()
        expires = timedelta(seconds=expires_in)
        method_upper = method.upper()
        try:
            if method_upper == "GET":
                return await asyncio.to_thread(
                    self._client.presigned_get_object,
                    self._bucket,
                    key,
                    expires,
                )
            if method_upper == "PUT":
                return await asyncio.to_thread(
                    self._client.presigned_put_object,
                    self._bucket,
                    key,
                    expires,
                )
            msg = f"Unsupported presigned URL method: {method}"
            raise StorageError(msg)
        except StorageError:
            raise
        except Exception as e:
            if _is_not_found(e):
                raise ResourceNotFoundError("Object", key) from e
            logger.error(
                f"Minio presigned URL generation failed key={key} method={method}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_PRESIGNED_URL_FAILED"},
            )
            raise StorageError(f"Minio presigned URL failed: {e}") from e

    async def get_size(self, key: str) -> int:
        meta = await self.get_metadata(key)
        return int(meta["size"])

    async def get_content_type(self, key: str) -> str:
        meta = await self.get_metadata(key)
        return str(meta["content_type"])

    async def list_prefixes(
        self,
        prefix: str | None = None,
        delimiter: str = "/",
    ) -> list[str]:
        await self._ensure_bucket()
        try:
            results = await asyncio.to_thread(
                lambda: list(
                    self._client.list_objects(
                        self._bucket,
                        prefix=prefix,
                        recursive=False,
                    )
                )
            )
        except Exception as e:
            logger.error(
                f"Minio list_prefixes failed prefix={prefix}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_LIST_FAILED"},
            )
            raise StorageError(f"Minio list_prefixes failed: {e}") from e

        prefixes = sorted({obj.object_name for obj in results if obj.is_dir})
        return list(prefixes)

    async def get_storage_info(self) -> dict[str, Any]:
        await self._ensure_bucket()
        try:
            count, total = await asyncio.to_thread(self._count_and_size)
        except Exception as e:
            logger.error(
                f"Minio get_storage_info failed: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_QUERY_FAILED"},
            )
            raise StorageError(f"Minio get_storage_info failed: {e}") from e

        return {
            "provider": "minio",
            "bucket": self._bucket,
            "object_count": count,
            "total_size_bytes": total,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_bucket(self) -> None:
        with self._bucket_ready_lock:
            if self._bucket_ready:
                return
        if not self._ensure_bucket_on_first_call:
            with self._bucket_ready_lock:
                self._bucket_ready = True
            return

        try:
            exists = await asyncio.to_thread(self._client.bucket_exists, self._bucket)
            if not exists:
                await asyncio.to_thread(self._client.make_bucket, self._bucket)
                logger.info(f"Created Minio bucket {self._bucket}")
        except Exception as e:
            logger.error(
                f"Failed to ensure Minio bucket {self._bucket} exists: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_BUCKET_INIT_FAILED"},
            )
            raise StorageError(f"Minio bucket init failed: {e}") from e
        with self._bucket_ready_lock:
            self._bucket_ready = True

    def _put_object_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str] | None,
    ) -> None:
        stream = io.BytesIO(content)
        self._client.put_object(
            self._bucket,
            key,
            stream,
            length=len(content),
            content_type=content_type,
            metadata=metadata,
        )

    def _get_object_bytes(self, key: str) -> bytes:
        response = None
        try:
            response = self._client.get_object(self._bucket, key)
            return response.read()
        except Exception as e:
            if _is_not_found(e):
                raise _NotFound(key) from e
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def _list_objects_to_list(self, prefix: str | None) -> list[Any]:
        return list(
            self._client.list_objects(
                self._bucket,
                prefix=prefix,
                recursive=True,
            )
        )

    def _count_and_size(self) -> tuple[int, int]:
        count = 0
        total = 0
        for obj in self._client.list_objects(self._bucket, recursive=True):
            count += 1
            total += int(obj.size or 0)
        return count, total

    def _emit(self, event: Any) -> None:
        if self._event_emitter is None:
            return
        try:
            self._event_emitter.emit(event)
        except Exception as e:
            logger.error(
                f"Minio storage adapter failed to emit {type(event).__name__}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_STORAGE_EVENT_EMISSION_FAILED"},
            )


# ----------------------------------------------------------------------
# Error helpers
# ----------------------------------------------------------------------


class _NotFound(Exception):
    """Internal sentinel for object-not-found from Minio."""


def _is_not_found(exc: BaseException) -> bool:
    """Detect Minio's various not-found error shapes."""
    # minio.error.S3Error has a .code like 'NoSuchKey'
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in {"NoSuchKey", "NoSuchObject", "404"}:
        return True
    # minio raises S3Error with status_code 404 too
    status = getattr(exc, "status_code", None)
    if status == 404:
        return True
    name = exc.__class__.__name__
    return name in {"NoSuchKey", "NoSuchObject"}
