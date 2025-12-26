# Debug Guide for Redis-Based Architecture

This guide explains how to use the debug feature to troubleshoot issues with target generation in the Redis-based architecture.

## Overview

The debug feature provides detailed information about:
- Job processing status
- Error details when target generation fails
- Cache status and timing information
- Whether a job is currently being processed

## Hard Reload

When you need to force a complete cache refresh and regeneration of targets, use the `?reload=true` parameter. This is useful when:
- You've updated your target generator scripts
- You want to clear cached errors
- You need to force an immediate refresh regardless of cache state

### How to Use Hard Reload

Add `?reload=true` to any target request URL to trigger a hard reload.

```bash
# Force reload for a specific target
curl http://127.0.0.1:8080/targets/my-service?reload=true

# Force reload with additional parameters
curl "http://127.0.0.1:8080/targets/my-service?env=prod&reload=true"
```

### Hard Reload Response

The reload endpoint returns status information about what was cleared:

```json
{
  "status": "reload_initiated",
  "message": "Cache cleared and job enqueued for regeneration. Please try again without ?reload=true",
  "path": "/targets/my-service?",
  "cache_cleared": true,
  "error_cache_cleared": false
}
```

**Response Fields:**
- `status`: Always `reload_initiated` on success
- `message`: Instructions for the next step
- `path`: The target path that was reloaded
- `cache_cleared`: Whether normal cache was cleared (true if cache existed)
- `error_cache_cleared`: Whether error cache was cleared (true if error existed)

### After Hard Reload

After triggering a hard reload:
1. A job is automatically enqueued for regeneration
2. Wait a moment for the worker to process the job
3. Make a normal request (without `?reload=true`) to get fresh targets

```bash
# 1. Trigger hard reload
curl http://127.0.0.1:8080/targets/my-service?reload=true
# Response: {"status": "reload_initiated", ...}

# 2. Wait a moment, then fetch fresh targets
curl http://127.0.0.1:8080/targets/my-service
# Response: Fresh target data (or cache miss if still processing)
```

## How to Access Debug Information

Add `?debug=true` to any target request URL to see debug information.

### Example

```bash
# Normal request
curl http://127.0.0.1:8080/targets/my-service

# Debug request
curl http://127.0.0.1:8080/targets/my-service?debug=true
```

## Debug Response Types

The debug endpoint returns different types of information depending on the state of the job.

### 1. Successful Generation with Debug Info

When a job has completed successfully, debug will show the normal cache information:

```json
{
  "requested_path": "/targets/my-service",
  "debug_info": {
    "normal_cache": {
      "status": "success",
      "updated_timestamp": "2024-01-15T10:30:45.123456",
      "results": [
        {
          "targets": ["10.0.1.1:9100", "10.0.1.2:9100"],
          "labels": {"job": "node-exporter"}
        }
      ],
      "cache_age_seconds": "45.2s ago"
    }
  }
}
```

### 2. Error Details

When target generation fails, debug will show detailed error information:

```json
{
  "requested_path": "/targets/my-service",
  "debug_info": {
    "error_details": {
      "timestamp": "2024-01-15T10:30:45.123456",
      "timestamp_human": "2024-01-15 10:30:45",
      "error_type": "TimeoutError",
      "error_message": "Generator exceeded timeout limit",
      "full_path": "/targets/my-service",
      "traceback": "Traceback (most recent call last):\n  File ..."
    }
  }
}
```

### 3. Job Currently Processing

When a job is being processed by a worker:

```json
{
  "status": "processing",
  "message": "Job is currently being processed by a worker. Please wait a moment and try again.",
  "suggestion": "Wait a few seconds and retry with ?debug=true"
}
```

### 4. No Debug Information Available

When no cached data exists and no job is being processed:

```json
{
  "requested_path": "/targets/my-service",
  "status": "no_debug_info",
  "message": "No error information available yet. Please trigger job processing first.",
  "suggestion": "Try the request without ?debug=true first to trigger job processing, then retry with ?debug=true"
}
```

## Common Debug Scenarios

### Scenario 1: First Time Request

When you request a target path for the first time:

```bash
curl http://127.0.0.1:8080/targets/my-service
# Returns: {"error": "cache miss"}

curl http://127.0.0.1:8080/targets/my-service?debug=true
# Returns: no_debug_info status
```

**What to do:**
1. Make the request without `?debug=true` first to trigger job processing
2. Wait a few seconds for the worker to process the job
3. Retry with `?debug=true` to see the results or error details

### Scenario 2: Job Processing

When a job is actively being processed:

```bash
curl http://127.0.0.1:8080/targets/my-service?debug=true
# Returns: status "processing"
```

**What to do:**
- Wait a few seconds
- Retry the request
- The job should complete and you'll see results or error details

### Scenario 3: Successful Generation

After a successful job completes:

```bash
curl http://127.0.0.1:8080/targets/my-service
# Returns: JSON array of targets

curl http://127.0.0.1:8080/targets/my-service?debug=true
# Returns: debug_info with normal_cache showing success status
```

### Scenario 4: Generation Failed

When target generation fails:

```bash
curl http://127.0.0.1:8080/targets/my-service
# Returns: {"error": "cache miss"} (if error was not cached yet)

curl http://127.0.0.1:8080/targets/my-service?debug=true
# Returns: error_details with full traceback and error information
```

**What to do:**
- Check the error type and message in `error_details`
- Review the traceback to identify the issue
- Fix the target generator script
- Retry the request

### Scenario 5: Expired Cache

When cache expires and needs refresh:

```bash
curl http://127.0.0.1:8080/targets/my-service
# Returns: {"error": "cache expired"}

curl http://127.0.0.1:8080/targets/my-service?debug=true
# Returns: debug_info showing normal_cache with cache_age_seconds
```

**What to do:**
- The system automatically enqueues a refresh job
- Wait for the refresh to complete
- Retry the request

## Understanding Cache States

### Cache Hit
- **Condition**: Valid, non-expired data exists in cache
- **Response**: Returns cached targets immediately
- **Debug**: Shows `normal_cache` with cache age

### Cache Miss
- **Condition**: No data exists in cache
- **Response**: Returns `{"error": "cache miss"}`
- **Action**: Enqueues job for processing
- **Debug**: Shows `no_debug_info` initially

### Cache Expired
- **Condition**: Data exists but has expired
- **Response**: Returns `{"error": "cache expired"}`
- **Action**: Enqueues job to refresh cache
- **Debug**: Shows `normal_cache` with cache age and expiry status

### Cache Error
- **Condition**: Previous generation failed and error is cached
- **Response**: Returns `{"error": "cache miss"}`
- **Debug**: Shows `error_details` with full error information

## Monitoring Job Status

You can check if a job is queued or being processed using the Redis CLI:

```bash
# Check main queue
redis-cli llen target_generation_queue

# Check processing queue
redis-cli llen target_generation_queue:processing

# List jobs in main queue
redis-cli lrange target_generation_queue 0 -1

# List jobs being processed
redis-cli lrange target_generation_queue:processing 0 -1
```

## Metrics for Debugging

Monitor these Prometheus metrics for debugging:

- `httpsd_path_requests_total{status="cache-not-exist"}` - Cache misses
- `httpsd_path_requests_total{status="cache-expired"}` - Cache expirations
- `httpsd_path_requests_total{status="success"}` - Successful requests
- `httpsd_path_requests_total{status="fail"}` - Failed requests
- `httpsd_cache_operations_total{operation="hit"}` - Cache hits
- `httpsd_cache_operations_total{operation="miss"}` - Cache misses
- `httpsd_cache_operations_total{operation="expired"}` - Cache expiry
- `httpsd_redis_worker_jobs_processed_total` - Jobs processed by workers
- `httpsd_update_queue_jobs{status="pending"}` - Pending jobs
- `httpsd_update_queue_jobs{status="processing"}` - Jobs being processed

## Troubleshooting Tips

### Issue: Jobs Not Processing

**Symptoms:**
- Requests return "cache miss" repeatedly
- No debug information available
- Workers appear idle

**Solutions:**
1. Check that workers are running:
   ```bash
   curl http://127.0.0.1:8081/metrics
   ```

2. Check Redis queue status:
   ```bash
   redis-cli llen target_generation_queue
   ```

3. Check worker logs for errors

4. Verify Redis connection from both server and workers

### Issue: Jobs Stuck in Processing

**Symptoms:**
- Jobs remain in processing queue
- Requests hang or time out

**Solutions:**
1. Check worker logs for errors
2. Check if worker process is still running
3. Review worker timeout settings
4. Manually clear stuck jobs from Redis if needed:
   ```bash
   redis-cli lpop target_generation_queue:processing
   ```

### Issue: Errors Not Showing in Debug

**Symptoms:**
- Target generation fails
- Debug shows no error information

**Solutions:**
1. Make sure you've made a request without `?debug=true` first
2. Wait for the job to complete processing
3. Check worker logs directly
4. Verify error caching is enabled

### Issue: Stale Cache After Updating Generator

**Symptoms:**
- You updated your target generator script
- Old/outdated targets are still being returned
- Cache hasn't expired yet

**Solutions:**
1. Force a hard reload to clear cache and regenerate:
   ```bash
   curl http://127.0.0.1:8080/targets/my-service?reload=true
   ```
2. Wait for the worker to process the regeneration job
3. Make a normal request to get fresh targets

## Integration with Prometheus

Prometheus will automatically retry failed HTTP SD requests:

- **On success**: Prometheus updates target list
- **On error**: Prometheus keeps using current target list
- **Retry logic**: Prometheus retries according to HTTP SD config

This means you have time to fix errors without losing targets.

## Best Practices

1. **Always test your generators** using `prometheus-http-sd check` before deployment
2. **Monitor metrics** to detect issues early
3. **Use debug mode** during development and troubleshooting
4. **Check logs** for detailed error information
5. **Set appropriate cache expiration** times based on your update frequency
6. **Monitor Redis queue lengths** to detect processing bottlenecks
7. **Use unique worker IDs** when running multiple workers for easier tracking

## Example: Complete Debugging Workflow

```bash
# 1. Request target (first time, cache miss)
curl http://127.0.0.1:8080/targets/my-service
# Response: {"error": "cache miss"}

# 2. Check debug (no info yet)
curl http://127.0.0.1:8080/targets/my-service?debug=true
# Response: no_debug_info status

# 3. Wait for worker to process (or check queue status)
redis-cli llen target_generation_queue:processing

# 4. Check debug again (should show processing or completed)
curl http://127.0.0.1:8080/targets/my-service?debug=true

# If error occurred:
# Response: error_details with full traceback
# Fix your generator script based on error

# If successful:
# Response: normal_cache with results
# 5. Request again (cache hit)
curl http://127.0.0.1:8080/targets/my-service
# Response: JSON array of targets
```

## Example: Hard Reload Workflow

Use this workflow when you've updated your generator and need fresh targets immediately:

```bash
# 1. Trigger hard reload to clear cache and enqueue regeneration
curl http://127.0.0.1:8080/targets/my-service?reload=true
# Response: {"status": "reload_initiated", "cache_cleared": true, ...}

# 2. Wait for worker to process the job
sleep 2

# 3. Request fresh targets
curl http://127.0.0.1:8080/targets/my-service
# Response: Fresh JSON array of targets

# 4. (Optional) Verify with debug
curl http://127.0.0.1:8080/targets/my-service?debug=true
# Response: Shows updated cache timestamp
```

## See Also

- [Redis Architecture Documentation](./redis-architecture.md)
- [Metrics Documentation](./metrics.txt)
- [README](../README.md)

