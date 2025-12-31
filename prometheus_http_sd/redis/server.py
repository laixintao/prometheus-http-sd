import logging
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from urllib.parse import urlencode

from ..config import config
from ..sd import run_python
from ..version import VERSION
from .cache import RedisCache
from .queue import RedisJobQueue
from ..dispather import CacheNotExist, CacheExpired
from ..metrics import (
    cache_operations,
    path_last_generated_targets,
    target_path_requests_total,
    target_path_request_duration_seconds,
)

logger = logging.getLogger(__name__)


class ServerDispatcher:
    def __init__(self, cache_expire_seconds: int):
        self.cache_expire_seconds = cache_expire_seconds
        self.cache = RedisCache(config.redis_url)
        self.queue = RedisJobQueue(config.redis_url)

    def _enqueue_job(
        self, full_path: str, path: str, extra_args: dict, reason: str = ""
    ):
        if self.is_job_processing(full_path):
            logger.info(
                f"Job already queued/processing for {full_path}, "
                f"skipping duplicate"
            )
            return

        job_data = {
            "full_path": full_path,
            "path": path,
            "extra_args": extra_args,
        }

        if self.queue.enqueue_job(job_data):
            logger.info(f"Enqueued job for {full_path} ({reason})")
        else:
            logger.error(f"Failed to enqueue job for {full_path}")

    def get_targets(self, path: str, full_path: str, **extra_args):
        data = self.cache.get(full_path)
        if data:
            updated_timestamp = data["updated_timestamp"]
            current = datetime.now().timestamp()
            if current - updated_timestamp <= self.cache_expire_seconds:
                logger.info(f"Cache hit for {full_path}")
                cache_operations.labels(operation="hit").inc()
                return data["results"]
            else:
                logger.info(
                    f"Cache expired for {full_path} "
                    f"(age: {current - updated_timestamp:.1f}s)"
                )
                cache_operations.labels(operation="expired").inc()
                # Enqueue new job to refresh expired cache
                self._enqueue_job(full_path, path, extra_args, "cache expired")
                raise CacheExpired(
                    updated_timestamp=updated_timestamp,
                    cache_excepire_seconds=self.cache_expire_seconds,
                )

        # Cache miss - enqueue job for workers to process
        cache_operations.labels(operation="miss").inc()
        self._enqueue_job(full_path, path, extra_args, "cache miss")
        raise CacheNotExist()

    def get_debug_info(self, full_path: str):
        """Get debug information for failed jobs and normal cache results."""
        debug_info = {}

        # Check for error cache
        error_cache_key = f"error:{full_path}"
        logger.debug(
            f"Looking for error debug info with key: {error_cache_key}"
        )

        error_data = self.cache.get(error_cache_key)
        logger.debug(f"Error cache data: {error_data}")

        if error_data and error_data.get("status") == "error":
            error_details = error_data.get("error_details", {})
            # Add human-readable timestamp if available
            if "timestamp" in error_details:
                try:
                    error_details["timestamp_human"] = datetime.fromisoformat(
                        error_details["timestamp"]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    error_details["timestamp_human"] = error_details[
                        "timestamp"
                    ]
            debug_info["error_details"] = error_details

        # Check for normal cache result
        normal_cache_data = self.cache.get(full_path)
        logger.debug(f"Normal cache data: {normal_cache_data}")

        if normal_cache_data:
            updated_timestamp = normal_cache_data.get("updated_timestamp")
            cache_age_seconds = (
                time.time() - updated_timestamp if updated_timestamp else None
            )

            debug_info["normal_cache"] = {
                "status": "success",
                "updated_timestamp": (
                    datetime.fromtimestamp(updated_timestamp).isoformat()
                    if updated_timestamp
                    else None
                ),
                "results": normal_cache_data.get("results"),
                "cache_age_seconds": (
                    f"{cache_age_seconds:.1f}s ago"
                    if cache_age_seconds
                    else None
                ),
            }

        if debug_info:
            return debug_info

        return None

    def is_job_processing(self, full_path: str):
        return self.queue.is_job_queued_or_processing(full_path)

    def hard_reload(
        self,
        path: str,
        full_path: str,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
        **extra_args,
    ):
        # Clear normal cache
        cache_deleted = self.cache.delete(full_path)
        if cache_deleted:
            logger.info(f"Cleared cache for {full_path}")

        # Clear error cache
        error_cache_key = f"error:{full_path}"
        error_cache_deleted = self.cache.delete(error_cache_key)
        if error_cache_deleted:
            logger.info(f"Cleared error cache for {full_path}")

        # Enqueue new job to regenerate
        self._enqueue_job(
            full_path,
            path,
            extra_args,
            "hard reload requested by user",
        )

        # Wait for worker to complete
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if result is in cache
            data = self.cache.get(full_path)
            if data:
                logger.info(
                    f"Hard reload completed for {full_path} "
                    f"in {time.time() - start_time:.2f}s"
                )
                return {
                    "status": "reload_complete",
                    "path": full_path,
                    "results": data["results"],
                    "processing_time": f"{time.time() - start_time:.2f}s",
                }

            # Check if there was an error
            error_data = self.cache.get(error_cache_key)
            if error_data and error_data.get("status") == "error":
                logger.error(f"Hard reload failed for {full_path}")
                return {
                    "status": "reload_error",
                    "path": full_path,
                    "error": error_data.get("error_details", {}),
                    "processing_time": f"{time.time() - start_time:.2f}s",
                }

            time.sleep(poll_interval)

        # Timeout reached
        logger.warning(f"Hard reload timeout for {full_path} after {timeout}s")
        return {
            "status": "reload_timeout",
            "message": "Please reload the page without ?reload=true later.",
            "processing_time": f"{time.time() - start_time:.2f}s",
            "timeout": f"{timeout:.2f}s",
            "path": full_path,
            "suggestion": "Try again later without ?reload=true",
        }


def create_server_app(prefix, cache_seconds):
    """Create Flask application for server-only mode."""
    import os

    # Get the template folder path relative to this file
    template_folder = os.path.join(
        os.path.dirname(__file__), "..", "templates"
    )
    app = Flask(__name__, template_folder=template_folder)

    # Initialize dispatcher
    dispatcher = ServerDispatcher(cache_seconds)

    @app.route(f"{prefix}/")
    def admin():
        """Admin page showing available targets."""
        paths = []
        try:
            root_path = Path(config.root_dir)
            if root_path.exists():
                for item in root_path.iterdir():
                    if item.is_dir():
                        paths.append(item.name)
        except Exception as e:
            logger.error(f"Error listing paths: {e}")

        return render_template(
            "admin.html", prefix=prefix, paths=paths, version=VERSION
        )

    @app.route(f"{prefix}/scrape_configs/<path:rest_path>")
    def get_scrape_configs(rest_path):
        generated = run_python(
            str(Path(config.root_dir) / (rest_path + ".py")), **request.args
        )
        return generated

    @app.route(f"{prefix}/targets", defaults={"rest_path": ""})
    @app.route(f"{prefix}/targets/", defaults={"rest_path": ""})
    @app.route(f"{prefix}/targets/<path:rest_path>")
    def get_targets(rest_path):
        # Handle hard reload request
        if request.args.get("reload") == "true":
            arg_list = dict(request.args)
            if "reload" in arg_list:
                del arg_list["reload"]

            if arg_list:
                query_string = urlencode(arg_list, doseq=True)
                full_path_without_reload = (
                    f"/targets/{rest_path}?{query_string}"
                )
            else:
                full_path_without_reload = f"/targets/{rest_path}?"

            logger.info(
                f"Hard reload requested for {full_path_without_reload}"
            )
            reload_result = dispatcher.hard_reload(
                rest_path,
                full_path_without_reload,
                timeout=config.hard_reload_timeout_seconds,
                poll_interval=config.hard_reload_poll_interval_seconds,
                **arg_list,
            )
            return jsonify(reload_result)

        if request.args.get("debug") == "true":

            arg_list = dict(request.args)
            if "debug" in arg_list:
                del arg_list["debug"]

            if arg_list:
                query_string = urlencode(arg_list, doseq=True)
                full_path_without_debug = (
                    f"/targets/{rest_path}?{query_string}"
                )
            else:
                full_path_without_debug = f"/targets/{rest_path}?"

            debug_info = dispatcher.get_debug_info(full_path_without_debug)

            # Add debugging information about what paths we're checking
            debug_response = {
                "requested_path": full_path_without_debug,
                "debug_info": debug_info,
            }

            if debug_info:
                return jsonify(debug_response)
            else:
                # No error cache found, check if job is being processed
                is_processing = dispatcher.is_job_processing(
                    full_path_without_debug
                )

                if is_processing:
                    return jsonify(
                        {
                            "status": "processing",
                            "message": (
                                "Job is currently being processed by a "
                                "worker. "
                                "Please wait a moment and try again."
                            ),
                            "suggestion": (
                                "Wait a few seconds and retry with ?debug=true"
                            ),
                        }
                    )
                else:
                    debug_response["status"] = "no_debug_info"
                    debug_response["message"] = (
                        "No error information available yet. "
                        "Please trigger job processing first."
                    )
                    debug_response["suggestion"] = (
                        "Try the request without ?debug=true first to trigger "
                        "job processing, then retry with ?debug=true"
                    )
                    return jsonify(debug_response)

        logger.info(
            "request target path: {}, with parameters: {}".format(
                rest_path,
                request.args,
            )
        )

        l1_dir = l2_dir = ""
        path_splits = rest_path.split("/")
        if len(path_splits) > 0:
            l1_dir = path_splits[0]
        if len(path_splits) > 1:
            l2_dir = path_splits[1]

        with target_path_request_duration_seconds.labels(
            path=rest_path
        ).time():
            try:
                full_path = request.full_path
                targets = dispatcher.get_targets(
                    rest_path, full_path, **request.args
                )
            except CacheNotExist:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="cache-not-exist",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                logger.error("Cache miss, full_path=%s", request.full_path)
                return jsonify({"error": "cache miss"})
            except CacheExpired as e:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="cache-expired",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                logger.error(
                    "Cache expired, full_path=%s, updated_timestamp=%s, "
                    "cache_excepire_seconds=%s",
                    request.full_path,
                    e.updated_timestamp,
                    e.cache_excepire_seconds,
                )
                return jsonify({"error": "cache expired"})
            except Exception as e:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="fail",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                logger.error(
                    "Exception on %s [%s]", request.full_path, request.method
                )
                logger.exception(e)
                return jsonify({"error": str(e)}), 500

        target_path_requests_total.labels(
            path=rest_path,
            status="success",
            l1_dir=l1_dir,
            l2_dir=l2_dir,
        ).inc()
        path_last_generated_targets.labels(path=rest_path).set(len(targets))
        return jsonify(targets)

    # Add Prometheus metrics endpoint
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app, {"/metrics": make_wsgi_app()}
    )

    return app
