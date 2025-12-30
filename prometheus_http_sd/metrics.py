from prometheus_client import Counter, Gauge, Histogram, Info, Summary
from .version import VERSION

# Version info metric
version_info = Info(
    "httpsd_version",
    "prometheus_http_sd version info",
)
version_info.info({"version": VERSION})

# Request metrics
target_path_requests_total = Counter(
    "httpsd_path_requests_total",
    "The total count of a path being requested, status label can be"
    " success/fail",
    ["path", "status", "l1_dir", "l2_dir"],
)

target_path_request_duration_seconds = Histogram(
    "httpsd_target_path_request_duration_seconds",
    "The bucket of request duration in seconds",
    ["path"],
)

path_last_generated_targets = Gauge(
    "httpsd_path_last_generated_targets",
    "Generated targets count in last request",
    ["path"],
)

# Generator metrics
generator_latency = Summary(
    "sd_generator_duration_seconds",
    "Run generator for full_path time",
    ["full_path", "status"],
)

# Queue metrics
queue_job_gauge = Gauge(
    "httpsd_update_queue_jobs", "Current jobs pending in the queue", ["status"]
)

finished_jobs = Counter("httpsd_finished_jobs", "Already finished jobs")

# Cache metrics
cache_operations = Counter(
    "httpsd_cache_operations_total",
    "Total cache operations",
    ["operation"],
)

dispatcher_started_counter = Counter(
    "httpsd_dispatcher_started_total",
    "How many times has the dispatcher has been started?",
)

# Worker metrics
worker_jobs_processed = Counter(
    "httpsd_redis_worker_jobs_processed_total",
    "Total jobs processed by workers",
    ["worker_id", "status"],
)

worker_started_counter = Counter(
    "httpsd_redis_worker_started_total",
    "How many times have workers been started?",
    ["worker_id"],
)

# Stale job cleaner metrics
stale_jobs_cleaned = Counter(
    "httpsd_redis_stale_jobs_cleaned_total",
    "Total stale jobs removed from processing queue",
)
