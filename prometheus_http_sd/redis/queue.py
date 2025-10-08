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
        self.processing_queue_name = f"{queue_name}:processing"
        self._redis_client = None
        self._connected = False

    def _connect(self):
        if not self._connected:
            try:
                self._redis_client = redis.from_url(
                    self.redis_url, decode_responses=True
                )
                self._redis_client.ping()
                self._connected = True
                logger.info(f"Connected to Redis queue at {self.redis_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis queue: {e}")
                raise

    def is_job_queued_or_processing(self, full_path: str) -> bool:
        """Check if a job for the given full_path is already queued or being
        processed.

        Args:
            full_path: The full path of the job to check

        Returns:
            bool: True if job is queued or processing, False otherwise
        """
        try:
            if not self._connected:
                self._connect()

            jobs = self._redis_client.lrange(self.queue_name, 0, -1)
            main_queue_count = len(jobs)
            logger.debug(
                f"Checking {main_queue_count} jobs in main queue for "
                f"{full_path}"
            )

            for job_json in jobs:
                job = json.loads(job_json)
                if job.get("full_path") == full_path:
                    logger.info(f"Found job in main queue for {full_path}")
                    return True

            processing_jobs = self._redis_client.lrange(
                self.processing_queue_name, 0, -1
            )
            processing_count = len(processing_jobs)
            logger.debug(
                f"Checking {processing_count} jobs in processing queue for "
                f"{full_path}"
            )

            for job_json in processing_jobs:
                job = json.loads(job_json)
                if job.get("full_path") == full_path:
                    logger.info(
                        f"Found job in processing queue for {full_path}"
                    )
                    return True

            logger.debug(f"No existing job found for {full_path}")
            return False
        except Exception as e:
            logger.error(f"Error checking job status for {full_path}: {e}")
            return False

    def _update_queue_metrics(self):
        """Update Prometheus queue metrics."""
        try:
            if not self._connected:
                self._connect()

            # Get queue lengths
            main_queue_length = self._redis_client.llen(self.queue_name)
            processing_length = self._redis_client.llen(
                self.processing_queue_name
            )

            # Update metrics
            queue_job_gauge.labels(status="pending").set(main_queue_length)
            queue_job_gauge.labels(status="processing").set(processing_length)

        except Exception as e:
            logger.debug(f"Failed to update queue metrics: {e}")

    def is_available(self) -> bool:
        try:
            if not self._connected:
                self._connect()
            return self._redis_client.ping()
        except Exception:
            return False

    def enqueue_job(self, job_data: Dict[str, Any]) -> bool:
        try:
            if not self._connected:
                self._connect()

            job_id = f"{job_data['full_path']}:{int(time.time())}"
            job_data["job_id"] = job_id

            result = self._redis_client.lpush(
                self.queue_name, json.dumps(job_data)
            )
            logger.info(f"Enqueued job {job_id} for {job_data['full_path']}")

            # Update queue metrics
            self._update_queue_metrics()

            return bool(result)
        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            return False

    def dequeue_job(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        try:
            if not self._connected:
                self._connect()

            result = self._redis_client.brpop(self.queue_name, timeout=timeout)
            if result:
                _, job_json = result
                job_data = json.loads(job_json)

                self._redis_client.lpush(self.processing_queue_name, job_json)
                logger.debug(
                    f"Dequeued job {job_data.get('job_id', 'unknown')}"
                )

                # Update queue metrics
                self._update_queue_metrics()

                return job_data
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None

    def complete_job(self, job_data: Dict[str, Any]) -> bool:
        try:
            if not self._connected:
                self._connect()

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
        except Exception as e:
            logger.error(f"Failed to complete job: {e}")
            return False

    def get_queue_length(self) -> int:
        try:
            if not self._connected:
                self._connect()

            return self._redis_client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    def get_processing_length(self) -> int:
        try:
            if not self._connected:
                self._connect()

            return self._redis_client.llen(self.processing_queue_name)
        except Exception as e:
            logger.error(f"Failed to get processing length: {e}")
            return 0
