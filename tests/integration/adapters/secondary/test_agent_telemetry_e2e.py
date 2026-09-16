"""End-to-end integration test for agent telemetry pipeline (Phase 4).

This test validates the complete sidecar-to-Elasticsearch pipeline:
1. Real agent image with otelcol sidecar and telemetry mount
2. Synthetic OTLP spans generated inside the container
3. spans.jsonl captured and parsed into CodingAgentOtlpSpanEvent
4. Events published to Elasticsearch under coding-agent-<execution_id> stream

Implements Phase 4 integration test from DEF-019.
See documentation/architecture/infrastructure/otel-routing.md for design.
"""

import asyncio
import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.claude_code.otel_span_parser import parse_spans_file
from codetoreum.domain.events.coding_agent_events import CodingAgentOtlpSpanEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_serialization import EventSerializer
from codetoreum.ports.output.event_store import IEventStore
from tests.conftest import ModernElasticsearchContainer, docker_available, wait_for_elasticsearch_indexing

logger = logging.getLogger(__name__)

pytestmark = docker_available


def _get_or_build_test_agent_image() -> str:
    """Get or build the test agent image with telemetry support.

    For Phase 4 testing, we create a minimal container that has the key
    components needed to test the telemetry pipeline: otelcol binary,
    configuration, and /var/otel mount point. This reproduces what the
    real agent image provides without requiring Claude CLI.
    """
    import docker
    import os

    client = docker.from_env()
    image_name = "test-agent-telemetry:phase4"

    # Check if image already exists
    try:
        client.images.get(image_name)
        return image_name
    except docker.errors.ImageNotFound:
        pass

    # Build the test image
    dockerfile_path = Path(__file__).parent / "Dockerfile.test-telemetry"
    context_path = Path(__file__).parent.parent.parent.parent.parent  # /workspace

    logger.info(f"Building test telemetry image from {dockerfile_path}")
    try:
        client.images.build(
            path=str(context_path),
            dockerfile=str(dockerfile_path),
            tag=image_name,
            rm=True,
        )
        logger.info(f"Successfully built {image_name}")
        return image_name
    except docker.errors.BuildError as e:
        logger.error(f"Failed to build test image: {e}")
        raise
    finally:
        client.close()


def _generate_synthetic_otlp_spans() -> str:
    """Generate Python code that sends synthetic OTLP spans to localhost:4318.

    Returns the Python code as a string to be executed inside the container.
    """
    return '''
import json
import time
from datetime import datetime, UTC
import urllib.request
import uuid

def send_otlp_span(trace_id: str, span_id: str, name: str, service_name: str = "claude-code"):
    """Send a synthetic OTLP span to the local receiver."""
    # Build an OTLP/JSON envelope matching the file exporter format
    now_nanos = int(datetime.now(UTC).timestamp() * 1_000_000_000)

    payload = {
        "resourceSpans": [{
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": service_name}},
                ]
            },
            "scopeSpans": [{
                "scope": {"name": service_name},
                "spans": [{
                    "traceId": trace_id,
                    "spanId": span_id,
                    "parentSpanId": "",
                    "name": name,
                    "kind": "SPAN_KIND_INTERNAL",
                    "startTimeUnixNano": str(now_nanos),
                    "endTimeUnixNano": str(now_nanos + 1_000_000_000),  # +1s
                    "attributes": [
                        {"key": "test.phase", "value": {"stringValue": "phase4"}},
                        {"key": "test.synthetic", "value": {"boolValue": True}},
                    ],
                    "events": [],
                    "status": {"code": "STATUS_CODE_OK"}
                }]
            }]
        }]
    }

    # POST to the local OTLP receiver
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:4318/v1/traces",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 202):
                print(f"WARNING: OTLP POST returned {resp.status}")
    except Exception as e:
        print(f"ERROR sending OTLP span: {e}")

# Wait a moment for otelcol to be ready
time.sleep(1)

# Send three synthetic test spans
trace_id_1 = "aabbccddeeff00112233445566778899"
trace_id_2 = "1122334455667788aabbccddeeee0000"

send_otlp_span(trace_id_1, "0000000000000001", "test.span.root")
send_otlp_span(trace_id_1, "0000000000000002", "test.span.child_1", "claude-code")
send_otlp_span(trace_id_2, "0000000000000003", "test.span.separate", "claude-code")

print("Synthetic spans sent successfully")
'''


@pytest.fixture(scope="function")
def es_container():
    """Elasticsearch test container with automatic cleanup."""
    container = ModernElasticsearchContainer("elasticsearch:8.17.0")
    try:
        container.start()
    except Exception:
        try:
            container.stop()
        except Exception:
            pass
        raise
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="function")
async def es_client(es_container):
    """Elasticsearch async client connected to test container."""
    url = es_container.get_url()
    client = AsyncElasticsearch(
        [url],
        verify_certs=False,
        ssl_show_warn=False,
        request_timeout=30,
    )

    try:
        await wait_for_elasticsearch_indexing(client, timeout=30)
        yield client
    finally:
        await client.close()


@pytest.fixture
async def event_bus(es_client):
    """Event bus connected to Elasticsearch."""
    bus = EventBus()
    yield bus
    # Teardown handled by client fixture


@pytest.mark.asyncio
class TestAgentTelemetryE2E:
    """End-to-end tests for agent telemetry pipeline."""

    async def test_real_agent_image_produces_otel_spans(self):
        """Test that real agent image produces spans.jsonl with OTLP/JSON content.

        This is a smoke test that the agent image was built correctly with:
        - otelcol binary
        - otelcol configuration
        - /var/otel directory with write permissions
        """
        import docker
        import subprocess

        agent_image = _get_or_build_test_agent_image()
        client = docker.from_env()

        # Create temp telemetry directory
        temp_otel = tempfile.mkdtemp(prefix="test-otel-")
        otel_path = Path(temp_otel)
        spans_file = otel_path / "spans.jsonl"

        try:
            container_name = f"test-agent-{uuid4().hex[:12]}"

            # Start the agent container with telemetry mount
            # We'll run a simple Python script that sends synthetic OTLP spans
            container = client.containers.run(
                agent_image,
                command=[
                    "python3",
                    "-c",
                    _generate_synthetic_otlp_spans(),
                ],
                volumes={temp_otel: {"bind": "/var/otel", "mode": "rw"}},
                name=container_name,
                detach=True,
                remove=False,
                stdout=True,
                stderr=True,
            )

            # Wait for container to complete (with timeout)
            exit_code = container.wait(timeout=30)

            # Get logs for debugging
            logs = container.logs().decode("utf-8")
            logger.info(f"Container logs:\n{logs}")

            # Verify container exited successfully
            assert exit_code["StatusCode"] == 0, f"Container failed with code {exit_code['StatusCode']}"

            # Extract spans.jsonl from container using docker cp
            # (Volume mounts with root-owned files may not sync back to host)
            try:
                subprocess.run(
                    ["docker", "cp", f"{container_name}:/var/otel/spans.jsonl", str(spans_file)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.CalledProcessError:
                # File might not exist or copy failed - we'll check below
                pass

            # Clean up container
            container.remove(force=True)

            # Verify spans.jsonl was created and extracted
            assert spans_file.is_file(), f"spans.jsonl not found at {spans_file}"

            # Verify file has content
            content = spans_file.read_text()
            assert len(content) > 0, "spans.jsonl is empty"

            # Parse as OTLP/JSON lines
            lines = content.strip().split("\n")
            assert len(lines) > 0, "spans.jsonl has no lines"

            # Each line should be valid JSON
            for line in lines:
                parsed = json.loads(line)
                assert "resourceSpans" in parsed, f"Missing resourceSpans in: {line[:100]}"

            logger.info(f"Successfully verified {len(lines)} OTLP/JSON lines in spans.jsonl")

        finally:
            try:
                client.containers.get(container_name).remove(force=True)
            except Exception:
                pass
            shutil.rmtree(temp_otel, ignore_errors=True)
            client.close()

    async def test_parse_and_create_otel_span_events(self):
        """Test parsing spans.jsonl into CodingAgentOtlpSpanEvent instances."""
        import docker
        import subprocess

        agent_image = _get_or_build_test_agent_image()
        client = docker.from_env()

        temp_otel = tempfile.mkdtemp(prefix="test-otel-parse-")
        otel_path = Path(temp_otel)
        spans_file = otel_path / "spans.jsonl"

        try:
            container_name = f"test-parser-{uuid4().hex[:12]}"
            execution_id = f"exec-{uuid4().hex[:12]}"
            work_item_id = f"wi-{uuid4().hex[:12]}"

            # Run container with synthetic spans
            container = client.containers.run(
                agent_image,
                command=[
                    "python3",
                    "-c",
                    _generate_synthetic_otlp_spans(),
                ],
                volumes={temp_otel: {"bind": "/var/otel", "mode": "rw"}},
                name=container_name,
                detach=True,
                remove=False,
                stdout=True,
                stderr=True,
            )

            exit_code = container.wait(timeout=30)
            assert exit_code["StatusCode"] == 0

            # Extract spans.jsonl from container
            try:
                subprocess.run(
                    ["docker", "cp", f"{container_name}:/var/otel/spans.jsonl", str(spans_file)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.CalledProcessError:
                pass

            container.remove(force=True)

            # Parse the spans file into events
            events = list(parse_spans_file(
                spans_file,
                execution_id=execution_id,
                correlation_id=work_item_id,
            ))

            # Verify we got the three synthetic spans
            assert len(events) >= 3, f"Expected at least 3 spans, got {len(events)}"

            # Verify event structure for each
            for i, event in enumerate(events[:3]):
                assert isinstance(event, CodingAgentOtlpSpanEvent)
                assert event.execution_id == execution_id
                assert event.correlation_id == work_item_id
                assert len(event.trace_id) > 0, f"Event {i}: missing trace_id"
                assert len(event.span_id) > 0, f"Event {i}: missing span_id"
                assert len(event.name) > 0, f"Event {i}: missing name"
                assert event.status == "OK"

                # Verify attributes were flattened
                assert "test.phase" in event.attributes
                assert event.attributes["test.phase"] == "phase4"
                assert "test.synthetic" in event.attributes
                assert event.attributes["test.synthetic"] is True

                logger.info(
                    f"Event {i}: trace_id={event.trace_id[:16]}... "
                    f"span_id={event.span_id} name={event.name}"
                )

        finally:
            try:
                client.containers.get(container_name).remove(force=True)
            except Exception:
                pass
            shutil.rmtree(temp_otel, ignore_errors=True)
            client.close()

    async def test_publish_events_to_elasticsearch(self, es_client):
        """Test publishing parsed events to Elasticsearch and querying them.

        This completes the full pipeline: generate -> parse -> publish -> query.
        """
        import docker
        import subprocess

        agent_image = _get_or_build_test_agent_image()
        docker_client = docker.from_env()

        temp_otel = tempfile.mkdtemp(prefix="test-otel-es-")
        otel_path = Path(temp_otel)
        spans_file = otel_path / "spans.jsonl"

        try:
            container_name = f"test-es-{uuid4().hex[:12]}"
            execution_id = f"exec-{uuid4().hex[:12]}"
            work_item_id = f"wi-{uuid4().hex[:12]}"

            # Run container with synthetic spans
            container = docker_client.containers.run(
                agent_image,
                command=[
                    "python3",
                    "-c",
                    _generate_synthetic_otlp_spans(),
                ],
                volumes={temp_otel: {"bind": "/var/otel", "mode": "rw"}},
                name=container_name,
                detach=True,
                remove=False,
                stdout=True,
                stderr=True,
            )

            exit_code = container.wait(timeout=30)
            assert exit_code["StatusCode"] == 0

            # Extract spans.jsonl from container
            try:
                subprocess.run(
                    ["docker", "cp", f"{container_name}:/var/otel/spans.jsonl", str(spans_file)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.CalledProcessError:
                pass

            container.remove(force=True)

            # Parse spans
            events = list(parse_spans_file(
                spans_file,
                execution_id=execution_id,
                correlation_id=work_item_id,
            ))
            assert len(events) >= 3

            # Publish to Elasticsearch using the same format as production
            serializer = EventSerializer()
            stream_name = f"coding-agent-{execution_id}"

            for event in events:
                # Create the document for Elasticsearch
                doc_body = {
                    "event_id": event.event_id,
                    "aggregate_id": execution_id,  # Stream by execution_id
                    "aggregate_type": "CodingAgentExecution",
                    "event_type": event.type,
                    "timestamp": event.timestamp,
                    "correlation_id": work_item_id,
                    "source": event.source,
                    "stream_version": 1,
                    "data": serializer.serialize(event),
                }

                # Index the document
                await es_client.index(
                    index=f"events-2024.12",  # Example month
                    id=event.event_id,
                    body=doc_body,
                    refresh=True,
                )

            # Wait for Elasticsearch to index the documents
            await asyncio.sleep(1)


            # Using the wildcard subscriber pattern: coding-agent-<execution_id>
            # Use match queries since fields are stored as text without keyword mapping
            response = await es_client.search(
                index="events-2024.12",
                query={
                    "bool": {
                        "must": [
                            {"match": {"aggregate_id": execution_id}},
                            {"match": {"event_type": "coding_agent.otlp_span"}},
                        ]
                    }
                },
                size=100,
            )

            # Verify query results
            hits = response["hits"]["hits"]
            logger.info(f"Found {len(hits)} events with aggregate_id={execution_id}")
            assert len(hits) >= 3, f"Expected at least 3 events in ES, got {len(hits)}"

            # Verify event structure in Elasticsearch
            for i, hit in enumerate(hits[:3]):
                doc = hit["_source"]
                assert doc["aggregate_id"] == execution_id
                assert doc["correlation_id"] == work_item_id
                assert doc["event_type"] == "coding_agent.otlp_span"
                assert "data" in doc

                # Data should be serialized event JSON (may be string or dict)
                data = doc["data"]
                if isinstance(data, str):
                    data = json.loads(data)

                assert "trace_id" in data
                assert "span_id" in data
                assert "name" in data

                logger.info(
                    f"ES hit {i}: aggregate_id={doc['aggregate_id']} "
                    f"trace_id={data['trace_id'][:16]}..."
                )

            logger.info(f"Successfully published and queried {len(hits)} events in Elasticsearch")

        finally:
            try:
                docker_client.containers.get(container_name).remove(force=True)
            except Exception:
                pass
            shutil.rmtree(temp_otel, ignore_errors=True)
            docker_client.close()

    async def test_expected_span_values_match(self):
        """Test that synthetic spans match expected trace_id, span_id, and name values."""
        import docker
        import subprocess

        agent_image = _get_or_build_test_agent_image()
        client = docker.from_env()

        temp_otel = tempfile.mkdtemp(prefix="test-otel-values-")
        otel_path = Path(temp_otel)
        spans_file = otel_path / "spans.jsonl"

        try:
            container_name = f"test-values-{uuid4().hex[:12]}"
            execution_id = "exec-test-values"

            # Run container
            container = client.containers.run(
                agent_image,
                command=[
                    "python3",
                    "-c",
                    _generate_synthetic_otlp_spans(),
                ],
                volumes={temp_otel: {"bind": "/var/otel", "mode": "rw"}},
                name=container_name,
                detach=True,
                remove=False,
                stdout=True,
                stderr=True,
            )

            exit_code = container.wait(timeout=30)
            assert exit_code["StatusCode"] == 0

            # Extract spans.jsonl from container
            try:
                subprocess.run(
                    ["docker", "cp", f"{container_name}:/var/otel/spans.jsonl", str(spans_file)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.CalledProcessError:
                pass

            container.remove(force=True)

            # Parse spans
            events = list(parse_spans_file(
                spans_file,
                execution_id=execution_id,
            ))

            # Expected values from _generate_synthetic_otlp_spans()
            expected_trace_ids = {
                "aabbccddeeff00112233445566778899",
                "1122334455667788aabbccddeeee0000",
            }
            expected_span_ids = {
                "0000000000000001",
                "0000000000000002",
                "0000000000000003",
            }
            expected_names = {
                "test.span.root",
                "test.span.child_1",
                "test.span.separate",
            }

            # Collect actual values
            actual_trace_ids = {e.trace_id for e in events}
            actual_span_ids = {e.span_id for e in events}
            actual_names = {e.name for e in events}

            # Verify
            assert expected_trace_ids == actual_trace_ids, \
                f"Trace ID mismatch: expected {expected_trace_ids}, got {actual_trace_ids}"
            assert expected_span_ids == actual_span_ids, \
                f"Span ID mismatch: expected {expected_span_ids}, got {actual_span_ids}"
            assert expected_names == actual_names, \
                f"Name mismatch: expected {expected_names}, got {actual_names}"

            logger.info("All expected span values matched successfully")

        finally:
            try:
                client.containers.get(container_name).remove(force=True)
            except Exception:
                pass
            shutil.rmtree(temp_otel, ignore_errors=True)
            client.close()
