#!/usr/bin/env python3
"""
Test OTLP trace export to SigNoz
"""
import time
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# Create resource
resource = Resource(attributes={
    SERVICE_NAME: "test-otlp-export"
})

# Create tracer provider
provider = TracerProvider(resource=resource)

# Create OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint="192.168.0.245:4317",
    insecure=True,
)

# Create console exporter for local debugging
console_exporter = ConsoleSpanExporter()

# Add both exporters
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
provider.add_span_processor(BatchSpanProcessor(console_exporter))

# Set global tracer provider
trace.set_tracer_provider(provider)

# Get tracer
tracer = trace.get_tracer(__name__)

# Create test spans
print("Creating test spans...")
for i in range(5):
    with tracer.start_as_current_span(f"test-span-{i}"):
        print(f"  - Created span {i}")
        time.sleep(0.1)

print("\nWaiting 6 seconds for batch export...")
time.sleep(6)

print("\nForcing flush...")
provider.force_flush()

print("Done! Check SigNoz for traces from service: test-otlp-export")
