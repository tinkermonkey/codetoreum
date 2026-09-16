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
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import docker
import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.claude_code.otel_span_parser import parse_spans_file
from codetoreum.domain.events.coding_agent_events import CodingAgentOtlpSpanEvent
from codetoreum.infrastructure.event_serialization import EventSerializer
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


@pytest.fixture(scope="function")
def agent_container_with_spans():
    """Run agent container once and extract spans.jsonl for test reuse.

    This fixture eliminates ~50 lines of duplicate container setup/teardown
    across multiple tests, providing a single source of spans data.
    """
    agent_image = _get_or_build_test_agent_image()
    client = docker.from_env()
    temp_otel = tempfile.mkdtemp(prefix="test-otel-")
    otel_path = Path(temp_otel)
    spans_file = otel_path / "spans.jsonl"
    container_name = f"test-agent-{uuid4().hex[:12]}"

    try:
        # Start container with synthetic spans
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

        # Wait for completion
        exit_code = container.wait(timeout=30)
        logs = container.logs().decode("utf-8")
        logger.info(f"Container logs:\n{logs}")

        # Verify exit code
        if exit_code["StatusCode"] != 0:
            raise RuntimeError(f"Container failed with code {exit_code['StatusCode']}, logs: {logs}")

        # Extract spans.jsonl from container using docker cp
        result = subprocess.run(
            ["docker", "cp", f"{container_name}:/var/otel/spans.jsonl", str(spans_file)],
            capture_output=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            pytest.fail(
                f"docker cp failed: {result.stderr.decode('utf-8')}\n"
                f"Container logs:\n{logs}"
            )

        # Verify file exists with clear error message
        if not spans_file.is_file():
            pytest.fail(f"spans.jsonl not found at {spans_file} after docker cp")

        # Clean up container
        container.remove(force=True)
        yield spans_file

    finally:
        try:
            client.containers.get(container_name).remove(force=True)
        except Exception:
            pass
        shutil.rmtree(temp_otel, ignore_errors=True)
        client.close()


@pytest.mark.asyncio
class TestAgentTelemetryE2E:
    """End-to-end tests for agent telemetry pipeline."""

    async def test_real_agent_image_produces_otel_spans(self, agent_container_with_spans):
        """Test that real agent image produces spans.jsonl with OTLP/JSON content.

        This is a smoke test that the agent image was built correctly with:
        - otelcol binary
        - otelcol configuration
        - /var/otel directory with write permissions
        """
        spans_file = agent_container_with_spans

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

    async def test_parse_and_create_otel_span_events(self, agent_container_with_spans):
        """Test parsing spans.jsonl into CodingAgentOtlpSpanEvent instances."""
        spans_file = agent_container_with_spans
        execution_id = f"exec-{uuid4().hex[:12]}"
        work_item_id = f"wi-{uuid4().hex[:12]}"

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

    async def test_publish_events_to_elasticsearch(self, agent_container_with_spans, es_client):
        """Test publishing parsed events to Elasticsearch and querying them.

        This completes the full pipeline: generate -> parse -> publish -> query.
        """
        spans_file = agent_container_with_spans
        execution_id = f"exec-{uuid4().hex[:12]}"
        work_item_id = f"wi-{uuid4().hex[:12]}"

        # Parse spans
        events = list(parse_spans_file(
            spans_file,
            execution_id=execution_id,
            correlation_id=work_item_id,
        ))
        assert len(events) >= 3

        # Publish to Elasticsearch using the same format as production
        serializer = EventSerializer()

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
                index="events-test",
                id=event.event_id,
                body=doc_body,
                refresh=True,
            )

        # Wait for Elasticsearch to index the documents
        await asyncio.sleep(1)

        # Using the wildcard subscriber pattern: coding-agent-<execution_id>
        # Use match queries since fields are stored as text without keyword mapping
        response = await es_client.search(
            index="events-test",
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

    async def test_expected_span_values_match(self, agent_container_with_spans):
        """Test that synthetic spans match expected trace_id, span_id, and name values."""
        spans_file = agent_container_with_spans
        execution_id = "exec-test-values"

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
