import json
import logging
import redis
import time
from typing import Any, Dict, List, Optional
from ..metrics import queue_job_gauge, stale_jobs_cleaned

logger = logging.getLogger(__name__)


class RedisJobQueue:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        queue_name: str = "target_generation_queue",
    ):
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.processing_queue_name = f"{queue_name}:processing"
        self._redis_client = redis.from_url(
            self.redis_url, decode_responses=True
        )
        self._redis_client.ping()
        logger.info(f"Connected to Redis queue at {self.redis_url}")

    def is_job_queued_or_processing(self, full_path: str) -> bool:
        """Check if a job for the given full_path is already queued.

        Args:
            full_path: The full path of the job to check

        Returns:
            bool: True if job is queued, False otherwise
        """
        jobs = self._redis_client.lrange(self.queue_name, 0, -1)
        main_queue_count = len(jobs)
        logger.debug(
            f"Checking {main_queue_count} jobs in queue for " f"{full_path}"
        )

        for job_json in jobs:
            job = json.loads(job_json)
            if job.get("full_path") == full_path:
                logger.info(f"Found job in queue for {full_path}")
                return True

        processing_jobs = self._redis_client.lrange(
            self.processing_queue_name, 0, -1
        )
        processing_queue_count = len(processing_jobs)
        logger.debug(
            f"Checking {processing_queue_count} jobs in processing queue for "
            f"{full_path}"
        )

        for job_json in processing_jobs:
            job = json.loads(job_json)
            if job.get("full_path") == full_path:
                logger.info(f"Found job in processing queue for {full_path}")
                return True

        logger.debug(f"No existing job found for {full_path}")
        return False

    def _update_queue_metrics(self):
        """Update Prometheus queue metrics."""
        # Get queue length
        queue_length = self._redis_client.llen(self.queue_name)
        processing_length = self._redis_client.llen(self.processing_queue_name)

        # Update metrics
        queue_job_gauge.labels(status="pending").set(queue_length)
        queue_job_gauge.labels(status="processing").set(processing_length)

    def enqueue_job(self, job_data: Dict[str, Any]) -> bool:
        job_id = f"{job_data['full_path']}:{int(time.time())}"
        job_data["job_id"] = job_id

        result = self._redis_client.lpush(
            self.queue_name, json.dumps(job_data)
        )
        logger.info(f"Enqueued job {job_id} for {job_data['full_path']}")

        # Update queue metrics
        self._update_queue_metrics()

        return bool(result)

    def dequeue_job(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        result = self._redis_client.brpop(self.queue_name, timeout=timeout)
        if result:
            _, job_json = result
            job_data = json.loads(job_json)

            # Add processing start timestamp before pushing to processing queue
            job_data["processing_started_at"] = time.time()
            processing_job_json = json.dumps(job_data)

            self._redis_client.lpush(
                self.processing_queue_name, processing_job_json
            )
            logger.debug(f"Dequeued job {job_data.get('job_id', 'unknown')}")

            # Update queue metrics
            self._update_queue_metrics()

            return job_data
        return None

    def complete_job(self, job_data: Dict[str, Any]) -> bool:
        job_id = job_data.get("job_id", "unknown")

        # Get all jobs in processing queue and find the one with matching
        # job_id
        processing_jobs = self._redis_client.lrange(
            self.processing_queue_name, 0, -1
        )
        for job_json in processing_jobs:
            try:
                job = json.loads(job_json)
                if job.get("job_id") == job_id:
                    # Remove this specific job
                    result = self._redis_client.lrem(
                        self.processing_queue_name, 1, job_json
                    )
                    logger.debug(f"Completed job {job_id}")

                    # Update queue metrics
                    self._update_queue_metrics()

                    return bool(result)
            except json.JSONDecodeError:
                continue

        logger.warning(f"Job {job_id} not found in processing queue")
        return False

    def get_stale_jobs(
        self, stale_threshold_seconds: float
    ) -> List[Dict[str, Any]]:
        stale_jobs = []
        current_time = time.time()

        processing_jobs = self._redis_client.lrange(
            self.processing_queue_name, 0, -1
        )

        for job_json in processing_jobs:
            try:
                job = json.loads(job_json)
                processing_started_at = job.get("processing_started_at")

                if processing_started_at is None:
                    # Legacy job without timestamp - consider it stale
                    logger.warning(
                        f"Found job without processing_started_at: "
                        f"{job.get('job_id', 'unknown')}"
                    )
                    job["_raw_json"] = job_json
                    stale_jobs.append(job)
                elif (
                    current_time - processing_started_at
                    > stale_threshold_seconds
                ):
                    logger.debug(
                        f"Found stale job {job.get('job_id', 'unknown')} "
                        f"with age {current_time - processing_started_at:.1f}s"
                    )
                    job["_raw_json"] = job_json
                    stale_jobs.append(job)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode job JSON: {job_json}")
                continue

        return stale_jobs

    def remove_stale_job(self, job_data: Dict[str, Any]) -> bool:
        job_id = job_data.get("job_id", "unknown")
        raw_json = job_data.get("_raw_json")

        if not raw_json:
            return False

        removed = self._redis_client.lrem(
            self.processing_queue_name, 1, raw_json
        )
        if removed:
            logger.info(f"Removed stale job {job_id}")
            stale_jobs_cleaned.inc()
            self._update_queue_metrics()
            return True

        logger.warning(f"Failed to remove stale job {job_id}")
        return False
