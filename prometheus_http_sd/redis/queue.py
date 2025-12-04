import json
import logging
import redis
import time
from typing import Any, Dict, Optional
from ..metrics import queue_job_gauge

logger = logging.getLogger(__name__)


class RedisJobQueue:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        queue_name: str = "target_generation_queue",
    ):
        self.redis_url = redis_url
        self.queue_name = queue_name
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

        logger.debug(f"No existing job found for {full_path}")
        return False

    def _update_queue_metrics(self):
        """Update Prometheus queue metrics."""
        # Get queue length
        queue_length = self._redis_client.llen(self.queue_name)

        # Update metrics
        queue_job_gauge.labels(status="pending").set(queue_length)

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

            logger.debug(f"Dequeued job {job_data.get('job_id', 'unknown')}")

            # Update queue metrics
            self._update_queue_metrics()

            return job_data
        return None
