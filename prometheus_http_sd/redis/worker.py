import logging
import signal
import threading
import time
import traceback
from datetime import datetime
from flask import Flask
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from ..config import config
from ..sd import generate
from .cache import RedisCache
from .queue import RedisJobQueue
from ..metrics import (
    generator_latency,
    finished_jobs,
    worker_jobs_processed,
    worker_started_counter,
)

logger = logging.getLogger(__name__)


class WorkerMetricsServer:
    """Flask-based server to expose worker metrics."""

    def __init__(self, port: int = 8081, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self.app = None
        self.thread = None
        self.running = False

    def _create_app(self):
        """Create Flask application for worker metrics."""
        app = Flask(__name__)

        # Add prometheus wsgi middleware to route /metrics requests
        prometheus_wsgi_app = make_wsgi_app()
        app.wsgi_app = DispatcherMiddleware(
            app.wsgi_app,
            {
                "/metrics": prometheus_wsgi_app,
            },
        )

        @app.route("/")
        def health():
            """Health check endpoint."""
            return {"status": "healthy", "service": "worker-metrics"}

        return app

    def start(self):
        """Start the metrics server in a separate thread."""
        if self.running:
            logger.warning("Metrics server is already running")
            return

        self.running = True

        try:
            self.app = self._create_app()

            # Start Flask app in a separate thread
            self.thread = threading.Thread(
                target=lambda: self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                ),
                daemon=True,
            )
            self.thread.start()
            logger.info(f"Worker metrics server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            self.running = False

    def stop(self):
        """Stop the metrics server."""
        if self.running:
            logger.info("Stopping worker metrics server")
            self.running = False
            # Flask app will stop when the thread ends


class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.running = False
        self.cache = RedisCache(config.redis_url)
        self.queue = RedisJobQueue(config.redis_url)
        self._stop_event = threading.Event()

    def start(self):
        if self.running:
            logger.warning(f"Worker {self.worker_id} is already running")
            return

        self.running = True
        logger.info(f"Starting worker {self.worker_id}")

        # Track worker startup
        worker_started_counter.labels(worker_id=self.worker_id).inc()

        try:
            self._run()
        except KeyboardInterrupt:
            logger.info(f"Worker {self.worker_id} interrupted by user")
        finally:
            self.stop()

    def stop(self):
        if not self.running:
            return

        logger.info(f"Stopping worker {self.worker_id}")
        self.running = False
        self._stop_event.set()

    def _run(self):
        while self.running and not self._stop_event.is_set():
            try:
                job_data = self.queue.dequeue_job(timeout=1)

                if job_data:
                    self._process_job(job_data)
                else:
                    continue

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} error in main loop: {e}"
                )
                time.sleep(1)

    def _process_job(self, job_data: dict):
        job_id = job_data.get("job_id", "unknown")
        full_path = job_data.get("full_path", "")
        path = job_data.get("path", "")
        extra_args = job_data.get("extra_args", {})

        logger.info(
            f"Worker {self.worker_id} processing job {job_id} for path: {path}"
        )
        start_time = time.time()

        try:
            # Track generator latency
            with generator_latency.labels(
                full_path=full_path, status="success"
            ).time():
                targets = generate(config.root_dir, path, **extra_args)

            # Store result in cache
            cache_data = {"updated_timestamp": time.time(), "results": targets}

            if self.cache.set(
                full_path, cache_data, config.cache_expire_seconds
            ):
                duration = time.time() - start_time
                logger.info(
                    f"Worker {self.worker_id} completed job {job_id} "
                    f"in {duration:.2f}s"
                )
                finished_jobs.inc()
                worker_jobs_processed.labels(
                    worker_id=self.worker_id, status="success"
                ).inc()
            else:
                logger.error(
                    f"Worker {self.worker_id} failed to cache results "
                    f"for job {job_id}"
                )
                worker_jobs_processed.labels(
                    worker_id=self.worker_id, status="cache_error"
                ).inc()

        except Exception as e:
            with generator_latency.labels(
                full_path=full_path, status="error"
            ).time():
                pass

            # Capture error details for debugging
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
                "worker_id": self.worker_id,
                "job_id": job_id,
                "path": path,
                "extra_args": extra_args,
                "timestamp": datetime.now().isoformat(),
                "processing_time": time.time() - start_time,
            }

            logger.error(
                f"Worker {self.worker_id} failed to process job {job_id} "
                f"for path '{path}': {e}"
            )

            # Cache the error result for debugging
            error_cache_key = f"error:{full_path}"
            error_cache_data = {
                "updated_timestamp": time.time(),
                "error_details": error_details,
                "status": "error",
            }

            # Store error in cache with longer expiration (1 hour)
            self.cache.set(error_cache_key, error_cache_data, 3600)
            logger.debug(
                f"Cached error details for {full_path} under key "
                f"{error_cache_key}"
            )

            worker_jobs_processed.labels(
                worker_id=self.worker_id, status="error"
            ).inc()


class WorkerPool:
    def __init__(
        self,
        num_workers: int = 4,
        first_worker_id: str = None,
        metrics_port: int = 8081,
        metrics_host: str = "0.0.0.0",
    ):
        self.num_workers = num_workers
        self.first_worker_id = first_worker_id
        self.metrics_port = metrics_port
        self.metrics_host = metrics_host
        self.workers = []
        self.threads = []
        self.running = False
        self.metrics_server = WorkerMetricsServer(
            metrics_port, host=metrics_host
        )

    def start(self):
        if self.running:
            logger.warning("Worker pool is already running")
            return

        self.running = True
        logger.info(f"Starting worker pool with {self.num_workers} workers")

        # Start metrics server
        self.metrics_server.start()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        for i in range(self.num_workers):
            if i == 0 and self.first_worker_id:
                worker_id = self.first_worker_id
            else:
                worker_id = f"worker-{i}"
            worker = Worker(worker_id)
            self.workers.append(worker)

            thread = threading.Thread(target=worker.start, daemon=True)
            thread.start()
            self.threads.append(thread)

        logger.info(f"Worker pool started with {len(self.workers)} workers")

    def _signal_handler(self, signum, frame):
        logger.info(f"Worker pool received signal {signum}, shutting down...")
        self.stop()

    def stop(self):
        if not self.running:
            return

        logger.info("Stopping worker pool")
        self.running = False

        # Stop metrics server
        self.metrics_server.stop()

        for worker in self.workers:
            worker.stop()

        for thread in self.threads:
            thread.join(timeout=5)

        logger.info("Worker pool stopped")

    def wait(self):
        for thread in self.threads:
            thread.join()
