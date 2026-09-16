"""End-to-end integration test for agent telemetry pipeline (Phase 4).

This test validates the complete real-agent-to-Elasticsearch pipeline:
1. Real agent image (Dockerfile.agent) with otelcol sidecar and production entrypoint
2. Synthetic OTLP spans generated inside the container
3. spans.jsonl captured and parsed into CodingAgentOtlpSpanEvent
4. Events published to Elasticsearch under coding-agent-<execution_id> stream
5. Events persisted via ElasticsearchEventStore with production naming conventions

Implements Phase 4 integration test from DEF-019.
See documentation/architecture/infrastructure/otel-routing.md for design.
"""

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import docker
import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.claude_code.otel_span_parser import parse_spans_file
from codetoreum.adapters.secondary.elasticsearch_event_store import (
    ElasticsearchEventStore,
)
from codetoreum.domain.events.coding_agent_events import CodingAgentOtlpSpanEvent
from tests.conftest import ModernElasticsearchContainer, docker_available, wait_for_elasticsearch_indexing

logger = logging.getLogger(__name__)

pytestmark = docker_available


def _get_or_build_real_agent_image() -> str:
    """Get or build the real agent image (Dockerfile.agent).

    This builds the actual production agent image that includes:
    - Claude CLI
    - Git CLI
    - GitHub CLI
    - OpenTelemetry Collector binary
    - Production entrypoint script (scripts/agent-entrypoint.sh)
    - /var/otel mount point for telemetry capture
    """
    client = docker.from_env()
    image_name = "codetoreum-agent:e2e-test"

    # Check if image already exists (skip rebuild if present)
    try:
        client.images.get(image_name)
        logger.info(f"Using existing agent image: {image_name}")
        return image_name
    except docker.errors.ImageNotFound:
        pass

    # Build the real agent image from Dockerfile.agent
    dockerfile_path = Path(__file__).parent.parent.parent.parent.parent / "Dockerfile.agent"
    context_path = Path(__file__).parent.parent.parent.parent.parent  # /workspace

    logger.info(f"Building real agent image from {dockerfile_path}")
    try:
        client.images.build(
            path=str(context_path),
            dockerfile=str(dockerfile_path),
            tag=image_name,
            rm=True,
            buildargs={
                "DOCKER_GID": "0",  # Use root group (safer for test containers)
            },
        )
        logger.info(f"Successfully built real agent image: {image_name}")
        return image_name
    except docker.errors.BuildError as e:
        logger.error(f"Failed to build real agent image: {e}")
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
async def event_store_with_es(es_client):
    """Create and initialize an ElasticsearchEventStore for testing."""
    event_store = ElasticsearchEventStore(
        es_client=es_client,
        index_prefix="events",
        create_index_template=True,
        enable_async_persistence=True,
        async_queue_max_size=1000,
        shutdown_drain_timeout_seconds=5.0,
        bulk_refresh=True,  # Force refresh for test reliability
    )
    await event_store.initialize()
    try:
        yield event_store
    finally:
        await event_store.close()


@pytest.fixture(scope="function")
def agent_container_with_real_image():
    """Run real agent container with synthetic spans and extract spans.jsonl.

    Uses the actual Dockerfile.agent and production entrypoint script
    (scripts/agent-entrypoint.sh), exercising the real sidecar-launch,
    health-check, and trap logic.
    """
    agent_image = _get_or_build_real_agent_image()
    client = docker.from_env()
    temp_otel = tempfile.mkdtemp(prefix="e2e-otel-")
    otel_path = Path(temp_otel)
    spans_file = otel_path / "spans.jsonl"
    container_name = f"e2e-agent-{uuid4().hex[:12]}"

    try:
        # Start container with synthetic spans using the real image
        # The real entrypoint will:
        # - Validate git CLI and gitconfig
        # - Fix gh CLI multi-account migration issues
        # - Validate Docker socket access
        # - Start OpenTelemetry Collector sidecar with health checks
        # - Run the requested command (python script to generate spans)
        # - Trap EXIT to shut down the collector gracefully
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
        exit_code = container.wait(timeout=60)  # Longer timeout for real image startup
        logs = container.logs().decode("utf-8")
        logger.info(f"Real agent container logs:\n{logs}")

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
    """End-to-end tests for agent telemetry pipeline with real agent image and event store."""

    async def test_real_agent_image_with_event_store_persistence(
        self,
        agent_container_with_real_image,
        event_store_with_es,
        es_client,
    ) -> None:
        """Test complete real pipeline: real agent → spans.jsonl → ElasticsearchEventStore.

        This exercises the production code path end-to-end:
        1. Real Dockerfile.agent with production entrypoint (scripts/agent-entrypoint.sh)
        2. Production OpenTelemetry Collector sidecar with health checks and traps
        3. Parses spans.jsonl into CodingAgentOtlpSpanEvent
        4. Persists via ElasticsearchEventStore with correct stream naming (coding-agent-<execution_id>)
        5. Uses production index naming (events-YYYY.MM based on timestamp)

        Validates requirements from done-means item 4, FR5/US6.
        """
        spans_file = agent_container_with_real_image
        execution_id = f"exec-{uuid4().hex[:12]}"
        work_item_id = f"wi-{uuid4().hex[:12]}"
        stream_id = f"coding-agent-{execution_id}"  # Production stream naming

        # Parse spans from the real agent container
        events = list(parse_spans_file(
            spans_file,
            execution_id=execution_id,
            correlation_id=work_item_id,
        ))
        assert len(events) >= 3, f"Expected at least 3 spans from real agent, got {len(events)}"

        # Persist events using the real ElasticsearchEventStore
        await event_store_with_es.append(stream_id, events)

        # Wait for async persistence to complete
        await event_store_with_es.wait_for_async_queue(timeout_seconds=10.0)

        # Give Elasticsearch time for refresh
        await asyncio.sleep(2)

        # Query back the events using the production stream naming
        persisted_events = await event_store_with_es.get_events(stream_id)
        logger.info(f"Retrieved {len(persisted_events)} events from event store with stream_id={stream_id}")
        assert len(persisted_events) >= 3, f"Expected at least 3 persisted events, got {len(persisted_events)}"

        # Verify event types and structure
        for event in persisted_events:
            assert event.type == "coding_agent.otlp_span"
            assert hasattr(event, "execution_id")
            assert event.execution_id == execution_id

        # Verify through raw Elasticsearch query using production index naming pattern
        # Production indices use events-YYYY.MM format based on event timestamp
        response = await es_client.search(
            index="events-*",  # Wildcard search across all event indices
            query={
                "bool": {
                    "must": [
                        {"term": {"aggregate_id": stream_id}},  # Stream ID: coding-agent-<execution_id>
                        {"term": {"event_type": "coding_agent.otlp_span"}},
                    ]
                }
            },
            size=100,
        )

        hits = response["hits"]["hits"]
        assert len(hits) >= 3, f"Expected at least 3 span events in ES, got {len(hits)}"

        # Verify index naming follows production convention (events-YYYY.MM)
        for hit in hits:
            index_name = hit["_index"]
            assert index_name.startswith("events-"), f"Index {index_name} doesn't match pattern events-YYYY.MM"
            # Pattern should be events-2025.09 or similar
            assert re.match(r"events-\d{4}\.\d{2}", index_name), f"Index {index_name} doesn't match events-YYYY.MM"

        # Verify stream naming convention in documents
        for hit in hits:
            doc = hit["_source"]
            assert doc["aggregate_id"] == stream_id, f"Expected stream_id {stream_id}, got {doc['aggregate_id']}"
            assert doc["aggregate_id"].startswith("coding-agent-"), "Stream ID should have coding-agent- prefix"

        logger.info(
            f"✓ Real agent image test passed: {len(persisted_events)} spans persisted via ElasticsearchEventStore "
            f"to production indices (events-YYYY.MM) with stream naming (coding-agent-<execution_id>)"
        )

    async def test_real_agent_image_produces_otel_spans(self, agent_container_with_real_image):
        """Test that real agent image produces spans.jsonl with OTLP/JSON content.

        Validates that Dockerfile.agent with production entrypoint exercises:
        - OpenTelemetry Collector sidecar startup and health checks
        - Collector shutdown traps on container exit
        - /var/otel directory write permissions
        """
        spans_file = agent_container_with_real_image

        # Verify file has content
        content = spans_file.read_text()
        assert len(content) > 0, "spans.jsonl is empty"

        # Parse as OTLP/JSON lines
        lines = content.strip().split("\n")
        assert len(lines) > 0, "spans.jsonl has no lines"

        # Each line should be valid JSON with resourceSpans
        for line in lines:
            parsed = json.loads(line)
            assert "resourceSpans" in parsed, f"Missing resourceSpans in: {line[:100]}"

        logger.info(f"✓ Real agent image produced {len(lines)} OTLP/JSON spans in spans.jsonl")

    async def test_parse_and_create_otel_span_events(self, agent_container_with_real_image):
        """Test parsing spans.jsonl into CodingAgentOtlpSpanEvent instances."""
        spans_file = agent_container_with_real_image
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

        logger.info(f"✓ Successfully created {len(events)} CodingAgentOtlpSpanEvent instances")

    async def test_expected_span_values_match(self, agent_container_with_real_image):
        """Test that synthetic spans match expected trace_id, span_id, and name values."""
        spans_file = agent_container_with_real_image
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

        logger.info("✓ All expected span values matched successfully")
