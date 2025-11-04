# WebSocket Horizontal Scaling Guide

## Overview

This document describes the horizontal scaling architecture for the Codetoreum WebSocket system, including Redis pub/sub message distribution, connection pooling, and crash recovery.

## Architecture

### Single Instance (Before)
```
┌─────────────────────────────────┐
│     Codetoreum Server           │
│  ┌───────────────────────────┐  │
│  │  WebSocket Adapter        │  │
│  │  - In-memory connections  │  │
│  │  - Local broadcasting     │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
         ↕
    WebSocket Clients
```

### Multi-Instance (After)
```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│  Instance 1         │      │  Instance 2         │      │  Instance 3         │
│  ┌──────────────┐   │      │  ┌──────────────┐   │      │  ┌──────────────┐   │
│  │ WS Adapter   │   │      │  │ WS Adapter   │   │      │  │ WS Adapter   │   │
│  │ (100 conns)  │   │      │  │ (150 conns)  │   │      │  │ (200 conns)  │   │
│  └──────┬───────┘   │      │  └──────┬───────┘   │      │  └──────┬───────┘   │
└─────────┼───────────┘      └─────────┼───────────┘      └─────────┼───────────┘
          │                            │                            │
          └────────────────────────────┼────────────────────────────┘
                                       ↓
                        ┌──────────────────────────────┐
                        │      Redis Pub/Sub           │
                        │                              │
                        │  - Event distribution        │
                        │  - Connection state          │
                        │  - Control messages          │
                        └──────────────────────────────┘
```

## Features

### 1. Connection Pooling

Each server instance has a configurable maximum connection limit to prevent resource exhaustion.

**Configuration:**
```bash
export CODETOREUM_WS_MAX_CONNECTIONS=1000  # Max connections per instance
```

**Behavior:**
- When the limit is reached, new connections are rejected with code `1008`
- Clients receive: `"Max connections reached"`
- Statistics track rejections: `stats["connection_rejections"]`

**Load Balancing:**
Use a load balancer (Nginx, HAProxy, AWS ALB) to distribute connections across instances:

```nginx
upstream websocket_backend {
    least_conn;  # Route to instance with fewest connections
    server instance1.example.com:8000;
    server instance2.example.com:8000;
    server instance3.example.com:8000;
}

server {
    location /ws {
        proxy_pass http://websocket_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 2. Redis Pub/Sub Message Distribution

Events are published to Redis and distributed to all server instances, ensuring all connected clients receive events regardless of which instance they're connected to.

**How It Works:**

1. **Event Published:** Application publishes domain event
2. **Redis Distribution:** Event sent to Redis channel `websocket:events`
3. **Instance Reception:** All instances receive event from Redis
4. **Local Broadcast:** Each instance broadcasts to its local connections

**Configuration:**
```bash
export CODETOREUM_WS_ENABLE_REDIS_PUBSUB=true  # Enable Redis pub/sub (default)
```

**Redis Channels:**
- `websocket:events` - Domain events for broadcast
- `websocket:control` - Control messages (disconnect, etc.)

### 3. Connection State Persistence

Connection metadata is persisted to Redis for crash recovery and monitoring.

**Configuration:**
```bash
export CODETOREUM_WS_ENABLE_CONNECTION_PERSISTENCE=true  # Enable persistence (default)
```

**Persisted Data:**
```json
{
  "connection_id": "ws-12345",
  "subscriptions": [
    {
      "subscription_type": "workflow_events",
      "workflow_run_id": "wfr-123",
      "event_types": ["WorkflowStarted", "WorkflowCompleted"]
    }
  ],
  "last_heartbeat": 1699564800.123,
  "connected_at": 1699564500.456
}
```

**Redis Keys:**
- Format: `websocket:connection:{connection_id}`
- TTL: `2 × heartbeat_timeout` (default: 180 seconds)
- Automatically cleaned up on disconnect

**Use Cases:**
- **Monitoring:** Track active connections across all instances
- **Debugging:** Inspect connection state and subscriptions
- **Recovery:** Potential for reconnection with subscription restoration (future feature)

### 4. Heartbeat and Connection Health

Connections are monitored via heartbeat/ping-pong to detect stale connections.

**Configuration:**
```bash
export CODETOREUM_WS_HEARTBEAT_INTERVAL=30   # Ping every 30 seconds
export CODETOREUM_WS_HEARTBEAT_TIMEOUT=90    # Disconnect after 90 seconds
```

**Behavior:**
- Server sends `{"type": "ping"}` every `heartbeat_interval` seconds
- Client must respond with any message (e.g., `{"type": "pong"}`)
- If no response within `heartbeat_timeout`, connection is closed
- Client receives: `"Connection timeout - no heartbeat received"` (code `4000`)

**Client Implementation:**
```javascript
const ws = new WebSocket('ws://example.com/ws?token=...');

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'ping') {
        // Respond to heartbeat
        ws.send(JSON.stringify({ type: 'pong' }));
    } else if (message.type === 'event') {
        // Handle event
        handleEvent(message);
    }
};
```

### 5. Backpressure Handling

Per-client message buffering with flow control warnings and automatic disconnection for slow consumers.

**Configuration:**
```bash
export CODETOREUM_WS_MAX_BUFFER_SIZE=1000           # Max buffered messages
export CODETOREUM_WS_FLOW_CONTROL_THRESHOLD=0.8     # Warn at 80% capacity
export CODETOREUM_WS_DISCONNECT_ON_OVERFLOW=true    # Disconnect on overflow
```

**Behavior:**
1. Messages buffered if client can't keep up
2. Warning sent at 80% capacity: `{"type": "flow_control", "buffer_usage": 0.85}`
3. If buffer exceeds limit, client disconnected with code `4003`

**Client Handling:**
```javascript
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'flow_control') {
        console.warn(`Buffer at ${message.buffer_usage * 100}% capacity`);
        // Consider: pause subscriptions, increase processing speed, or reconnect
    }
};
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODETOREUM_WS_MAX_CONNECTIONS` | `1000` | Maximum concurrent connections per instance |
| `CODETOREUM_WS_MAX_BUFFER_SIZE` | `1000` | Maximum events buffered per client |
| `CODETOREUM_WS_FLOW_CONTROL_THRESHOLD` | `0.8` | Buffer warning threshold (0.0-1.0) |
| `CODETOREUM_WS_DISCONNECT_ON_OVERFLOW` | `true` | Disconnect clients on buffer overflow |
| `CODETOREUM_WS_HEARTBEAT_INTERVAL` | `30` | Heartbeat ping interval (seconds) |
| `CODETOREUM_WS_HEARTBEAT_TIMEOUT` | `90` | Connection timeout (seconds) |
| `CODETOREUM_WS_RATE_LIMIT_MESSAGES` | `100` | Max messages per time window |
| `CODETOREUM_WS_RATE_LIMIT_WINDOW` | `60` | Rate limit window (seconds) |
| `CODETOREUM_WS_ENABLE_REDIS_PUBSUB` | `true` | Enable Redis pub/sub for horizontal scaling |
| `CODETOREUM_WS_ENABLE_CONNECTION_PERSISTENCE` | `true` | Enable connection state persistence |

### Python Configuration

```python
from codetoreum.adapters.primary.websocket_adapter import (
    WebSocketAdapter,
    WebSocketConfig,
)
from codetoreum.adapters.secondary.redis_pubsub_adapter import RedisPubSubAdapter
from redis import asyncio as aioredis

# Load from environment
config = WebSocketConfig.from_env()

# Or configure manually
config = WebSocketConfig(
    max_connections=1000,
    max_buffer_size=1000,
    heartbeat_interval=30,
    heartbeat_timeout=90,
    enable_redis_pubsub=True,
    enable_connection_persistence=True,
)

# Initialize Redis
redis_client = await aioredis.from_url("redis://localhost:6379")
redis_pubsub = RedisPubSubAdapter(redis_client)

# Create WebSocket adapter
ws_adapter = WebSocketAdapter(
    config=config,
    redis_pubsub=redis_pubsub,
    redis_client=redis_client,
)
```

## Deployment Scenarios

### Scenario 1: Single Instance (Development)

**Setup:**
```bash
# Disable Redis features for local development
export CODETOREUM_WS_ENABLE_REDIS_PUBSUB=false
export CODETOREUM_WS_ENABLE_CONNECTION_PERSISTENCE=false
export CODETOREUM_WS_MAX_CONNECTIONS=100

# Start server
python -m codetoreum.main
```

**Use Case:** Local development, testing

### Scenario 2: Small Production (2-3 Instances)

**Setup:**
```bash
# Enable Redis features
export CODETOREUM_WS_ENABLE_REDIS_PUBSUB=true
export CODETOREUM_WS_ENABLE_CONNECTION_PERSISTENCE=true
export CODETOREUM_WS_MAX_CONNECTIONS=500

# Redis connection
export CODETOREUM_REDIS_URL=redis://redis.example.com:6379

# Start multiple instances
docker-compose up --scale codetoreum=3
```

**Load Balancer:**
```yaml
# docker-compose.yml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf

  codetoreum:
    image: codetoreum:latest
    environment:
      - CODETOREUM_WS_ENABLE_REDIS_PUBSUB=true
      - CODETOREUM_REDIS_URL=redis://redis:6379
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

**Use Case:** Small to medium production deployments

### Scenario 3: Large Production (Auto-Scaling)

**Setup with Kubernetes:**

```yaml
# websocket-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: codetoreum-websocket
spec:
  replicas: 5  # Adjust based on load
  selector:
    matchLabels:
      app: codetoreum-websocket
  template:
    metadata:
      labels:
        app: codetoreum-websocket
    spec:
      containers:
      - name: codetoreum
        image: codetoreum:latest
        env:
        - name: CODETOREUM_WS_MAX_CONNECTIONS
          value: "1000"
        - name: CODETOREUM_WS_ENABLE_REDIS_PUBSUB
          value: "true"
        - name: CODETOREUM_REDIS_URL
          value: "redis://redis-cluster:6379"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: codetoreum-websocket
spec:
  selector:
    app: codetoreum-websocket
  ports:
  - port: 8000
    targetPort: 8000
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: codetoreum-websocket-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: codetoreum-websocket
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Use Case:** Large production deployments with auto-scaling

## Monitoring

### Metrics to Track

1. **Connection Metrics:**
   - `websocket.connections.total` - Total connections ever created
   - `websocket.connections.current` - Current active connections
   - `websocket.connections.rejected` - Connections rejected (limit reached)

2. **Message Metrics:**
   - `websocket.messages.sent` - Messages sent to clients
   - `websocket.messages.received` - Messages received from clients
   - `websocket.flow_control.warnings` - Flow control warnings sent
   - `websocket.disconnections.overflow` - Disconnections due to buffer overflow

3. **Redis Metrics:**
   - `redis.pubsub.messages.published` - Events published to Redis
   - `redis.pubsub.messages.received` - Events received from Redis
   - `redis.pubsub.errors` - Redis pub/sub errors

### Getting Statistics

```python
# Get WebSocket adapter statistics
stats = ws_adapter.manager.stats
print(f"Current connections: {stats['current_connections']}")
print(f"Total connections: {stats['total_connections']}")
print(f"Rejected connections: {stats['connection_rejections']}")

# Get Redis pub/sub statistics
pubsub_stats = redis_pubsub.get_stats()
print(f"Messages published: {pubsub_stats['messages_published']}")
print(f"Messages received: {pubsub_stats['messages_received']}")
```

## Troubleshooting

### Issue: Clients not receiving events

**Symptoms:**
- Events published but clients don't receive them
- Only some clients receive events

**Diagnosis:**
1. Check Redis pub/sub is enabled: `CODETOREUM_WS_ENABLE_REDIS_PUBSUB=true`
2. Verify Redis connection is working
3. Check Redis pub/sub statistics for errors
4. Verify client subscriptions are set up correctly

**Solution:**
```bash
# Check Redis connectivity
redis-cli ping  # Should return PONG

# Check Redis pub/sub channels
redis-cli PUBSUB CHANNELS websocket:*

# Check for errors in logs
grep "Redis" /var/log/codetoreum.log
```

### Issue: High connection rejections

**Symptoms:**
- Many clients can't connect
- `connection_rejections` metric is high

**Diagnosis:**
1. Check `max_connections` setting
2. Check if connections are leaking (not being cleaned up)
3. Check if load balancer is distributing evenly

**Solution:**
```bash
# Increase connection limit
export CODETOREUM_WS_MAX_CONNECTIONS=2000

# Scale up instances
kubectl scale deployment codetoreum-websocket --replicas=10

# Check connection distribution
redis-cli KEYS "websocket:connection:*" | wc -l
```

### Issue: High memory usage

**Symptoms:**
- Server memory usage increasing over time
- OOM kills in production

**Diagnosis:**
1. Check for connection leaks
2. Check buffer sizes (`max_buffer_size`)
3. Check if connections are properly cleaned up on disconnect

**Solution:**
```bash
# Reduce buffer sizes
export CODETOREUM_WS_MAX_BUFFER_SIZE=500

# Enable aggressive overflow disconnection
export CODETOREUM_WS_DISCONNECT_ON_OVERFLOW=true

# Monitor connection cleanup
watch -n 1 'redis-cli KEYS "websocket:connection:*" | wc -l'
```

## Best Practices

1. **Connection Limits:**
   - Set `max_connections` based on available memory (roughly 1MB per connection)
   - Use horizontal scaling rather than increasing per-instance limits

2. **Redis Configuration:**
   - Use Redis Sentinel or Redis Cluster for high availability
   - Monitor Redis memory usage and set appropriate `maxmemory` limits
   - Use separate Redis instances for pub/sub and persistence if needed

3. **Load Balancing:**
   - Use sticky sessions if client reconnection is critical
   - Distribute based on `least_conn` for even connection distribution
   - Set appropriate timeouts on load balancer

4. **Client Implementation:**
   - Implement automatic reconnection with exponential backoff
   - Handle flow control warnings gracefully
   - Respond to heartbeat pings promptly
   - Close connections when no longer needed

5. **Monitoring:**
   - Set up alerts for high rejection rates
   - Monitor Redis pub/sub lag
   - Track connection distribution across instances
   - Monitor message delivery latency

## Future Enhancements

1. **Sticky Sessions:** Route reconnecting clients to same instance
2. **Subscription Replay:** Restore subscriptions on reconnection
3. **Message Persistence:** Queue messages for offline clients
4. **Geographic Distribution:** Multi-region Redis pub/sub
5. **WebSocket Compression:** Reduce bandwidth usage

## References

- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [Redis Pub/Sub Documentation](https://redis.io/docs/manual/pubsub/)
- [WebSocket Protocol RFC 6455](https://tools.ietf.org/html/rfc6455)
