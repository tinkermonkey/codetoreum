# Codetoreum Dev Infrastructure

Exclusive development infrastructure for local Codetoreum bootstrap testing.

This `docker-compose.yml` brings up Elasticsearch and Redis instances that are:
- **Isolated** to Codetoreum only (no shared infrastructure contention)
- **Exclusive** (labeled `codetoreum.exclusive=true`)
- **Minimal** (single Elasticsearch node, single Redis database)
- **Fast** (named volumes persist data across restarts)

## Quick Start

### Start the dev-infra stack

```bash
docker-compose -f bootstrap/dev-infra/docker-compose.yml up -d
```

Verify both services are healthy:

```bash
docker-compose -f bootstrap/dev-infra/docker-compose.yml ps
```

Expected output (all `healthy`):
```
NAME                       STATUS
codetoreum-elasticsearch   Up (healthy)
codetoreum-redis           Up (healthy)
```

### Configure Codetoreum to use dev-infra

Set environment variables to point to the dev-infra services:

```bash
export ELASTICSEARCH_URL=http://localhost:9200
export REDIS_URL=redis://localhost:6379/0
```

Verify connectivity:

```bash
# Check Elasticsearch
curl -s http://localhost:9200/_cluster/health | jq .

# Check Redis
redis-cli ping
```

### Run bootstrap with dev-infra

Register the project:

```bash
.venv/bin/python bootstrap/register_project.py bootstrap/rounds.json
```

Or start the server:

```bash
python -m codetoreum.main
```

The infra-exclusivity checks (INV-21) will verify that:
1. ✅ Elasticsearch indices all start with `codetoreum-`
2. ✅ Redis keys all start with `codetoreum:`
3. ✅ Docker daemon has capacity headroom
4. ✅ GitHub token is valid and rate-limited

### Clean up dev-infra

Stop and remove containers:

```bash
docker-compose -f bootstrap/dev-infra/docker-compose.yml down
```

Remove data volumes (persistent data):

```bash
docker-compose -f bootstrap/dev-infra/docker-compose.yml down -v
```

## Infrastructure Details

### Elasticsearch

- **Container**: `codetoreum-elasticsearch`
- **Port**: `9200` (HTTP API)
- **Volume**: `codetoreum-es-data` (persistent)
- **Config**:
  - Single-node cluster (discovery.type=single-node)
  - Security disabled (local development only)
  - Memory: 512MB heap
  - Max bulk upload: 100MB

Index naming convention: `codetoreum-*`

Exclusivity check lists all indices; fails if any non-Codetoreum indices exist.

### Redis

- **Container**: `codetoreum-redis`
- **Port**: `6379` (standard Redis)
- **Volume**: `codetoreum-redis-data` (persistent, RDB + AOF)
- **Config**:
  - Single database (db 0; max_databases=1)
  - Memory limit: 256MB (LRU eviction)
  - Persistence: AOF enabled

Key naming convention: `codetoreum:*`

Exclusivity check scans all keys; fails if any keys lack the `codetoreum:` prefix.

## Troubleshooting

### Port already in use

If port 9200 or 6379 is occupied:

```bash
# Find what's using the port (Linux/macOS)
lsof -i :9200
lsof -i :6379

# Kill the process or modify docker-compose.yml ports
```

### Elasticsearch slow startup

Elasticsearch may take 15–30 seconds to be ready on first startup:

```bash
# Wait for health check
docker-compose -f bootstrap/dev-infra/docker-compose.yml logs elasticsearch
```

Look for: `"message":"Cluster health status changed from [RED] to [YELLOW]"`

### Redis persistence not working

Check volume permissions:

```bash
docker volume ls | grep codetoreum
docker volume inspect codetoreum-redis-data
```

### Shared infrastructure detected

If infra-exclusivity checks fail with:

```
Elasticsearch cluster is shared with other services.
```

Stop competing services:

```bash
docker ps | grep -E "elasticsearch|redis" | awk '{print $1}' | xargs docker stop
docker volume prune  # Optional: clean up unused volumes
```

## Bypassing checks for local development

For unit tests only, skip infra-exclusivity checks:

```bash
export CODETOREUM_INFRA_EXCLUSIVITY=skip
.venv/bin/python -m pytest tests/unit/bootstrap/
```

**WARNING**: The `skip` flag has no effect in CI (GitHub Actions, etc.) and should never be used in production-shaped environments.

## References

- [`bootstrap/ARCHITECTURE.md`](../ARCHITECTURE.md) — Bootstrap architecture and invariants
- [`documentation/architecture/invariants.md`](../../documentation/architecture/invariants.md) — INV-21 (infrastructure exclusivity)
- [`bootstrap/register_project.py`](../register_project.py) — Project registration (calls infra checks)
- [`src/codetoreum/infrastructure/bootstrap/infra_exclusivity.py`](../../src/codetoreum/infrastructure/bootstrap/infra_exclusivity.py) — Check implementation
