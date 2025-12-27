# Redis-Based Architecture

This document describes the new Redis-based architecture for Prometheus HTTP SD, designed for scalability and separation of concerns.

## Architecture Overview

The application is now split into two main components:

1. **Server Component**: Handles HTTP requests and enqueues jobs
2. **Worker Component**: Processes jobs from Redis queue and stores results

## Components

### Redis Modules (`prometheus_http_sd/redis/`)

- **`cache.py`**: Redis-based cache for storing target generation results
- **`queue.py`**: Redis-based job queue for distributing tasks to workers
- **`server.py`**: Redis-based server component for HTTP API and job enqueueing
- **`worker.py`**: Redis-based worker component for processing jobs from queue

## Usage

### Prerequisites

1. **Redis Server**: Must be running and accessible
2. **Target Directory**: Contains your target generators

### Starting the Components

#### 1. Start Redis Server
```bash
redis-server
```

#### 2. Start Server Component
```bash
# Using default settings
poetry run prometheus-http-sd-server /path/to/targets

# Or with custom options
poetry run prometheus-http-sd-server \
  --host 0.0.0.0 \
  --port 8080 \
  --redis-url redis://localhost:6379/0 \
  --cache-seconds 3600 \
  /path/to/targets
```

#### 3. Start Worker Component(s)
```bash
# Single worker with custom ID
poetry run prometheus-http-sd-worker --worker-id worker-1 /path/to/targets

# Worker pool (multiple workers)
poetry run prometheus-http-sd-worker --num-workers 4 /path/to/targets

# With custom Redis URL
poetry run prometheus-http-sd-worker \
  --redis-url redis://localhost:6379/0 \
  --num-workers 4 \
  /path/to/targets
```

### Scaling

#### Horizontal Scaling
- **Multiple Servers**: Run multiple server instances behind a load balancer
- **Multiple Workers**: Run worker pools on different machines
- **Redis Clustering**: Use Redis Cluster for high availability

#### Vertical Scaling
- **Server**: Increase `--threads` and `--connection-limit`
- **Workers**: Increase `--num-workers`

## Configuration

### CLI Options

All configuration is done through CLI arguments. CLI arguments take precedence and override any defaults.

#### Server Options
- `--host`, `--port`: Server binding (default: 127.0.0.1:8080)
- `--redis-url`: Redis connection URL (default: redis://localhost:6379/0)
- `--cache-seconds`: Cache expiration time (default: 300)
- `--connection-limit`: Server connection limit (default: 1000)
- `--threads`: Server threads (default: 64)
- `--url_prefix`: Global URL prefix (default: "")

#### Worker Options
- `--worker-id`: Unique worker identifier (creates single worker with custom ID)
- `--num-workers`: Number of workers in pool (default: 4, ignored when --worker-id is specified)
- `--redis-url`: Redis connection URL (default: redis://localhost:6379/0)
- `--log-level`: Python logging level (default: 20)

## Data Flow

1. **HTTP Request** → Server receives request for `/targets/example`
2. **Cache Check** → Server checks Redis cache for existing result
3. **Cache Hit** → Return cached result immediately
4. **Cache Miss** → Enqueue job to Redis queue
5. **Job Processing** → Worker picks up job from queue
6. **Target Generation** → Worker runs target generator
7. **Cache Store** → Worker stores result in Redis cache
8. **Future Requests** → Server returns cached result

### Hard Reload Flow

When `?reload=true` is passed:
1. **Clear Cache** → Server deletes normal cache and error cache for the path
2. **Enqueue Job** → Server enqueues a new job for regeneration
3. **Return Status** → Server returns reload confirmation
4. **Job Processing** → Worker processes the job and stores fresh results
5. **Future Requests** → Subsequent requests return fresh cached data

## Monitoring

### Metrics
- **`httpsd_path_requests_total`**: Request count by path and status
- **`httpsd_path_request_duration_seconds`**: Request duration histogram
- **`httpsd_path_last_generated_targets`**: Last generated target count

### Redis Monitoring
- **Queue Length**: `redis-cli llen target_generation_queue`
- **Processing Length**: `redis-cli llen target_generation_queue:processing`
- **Cache Keys**: `redis-cli keys "*"`

## API Query Parameters

The targets endpoint supports the following query parameters:

| Parameter | Description |
|-----------|-------------|
| `reload=true` | Force a hard reload: clears cache and enqueues regeneration job |
| `debug=true` | Returns debug information about cache state and errors |
| Custom params | Any other parameters are passed to your target generator |

### Example Requests

```bash
# Normal request
curl http://127.0.0.1:8080/targets/my-service

# Force cache refresh
curl http://127.0.0.1:8080/targets/my-service?reload=true

# Debug information
curl http://127.0.0.1:8080/targets/my-service?debug=true

# With custom parameters for generator
curl "http://127.0.0.1:8080/targets/my-service?env=prod&region=us-east-1"
```

## Benefits

1. **Scalability**: Scale server and workers independently
2. **Reliability**: Redis provides persistence and high availability
3. **Performance**: Cached results served immediately
4. **Separation**: Clear separation of HTTP handling and job processing
5. **Monitoring**: Comprehensive metrics and Redis monitoring
6. **Simplicity**: Simple CLI-based configuration without complex environment variable management

## Migration from Monolithic Mode

The original monolithic mode is still available via:
```bash
poetry run prometheus-http-sd serve /path/to/targets
```

For Redis-based architecture, use the new commands:
```bash
# Terminal 1: Start server
poetry run prometheus-http-sd-server /path/to/targets

# Terminal 2: Start workers
poetry run prometheus-http-sd-worker --num-workers 4 /path/to/targets
```
