import logging
import sys
import click
import waitress

from .mem_perf import start_tracing_thread
from .config import config
from .validate import validate
from .app import create_app


def config_log(level):
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    logging.basicConfig(
        level=level,
        format=(
            "[%(asctime)s] %(thread)d {%(filename)s:%(lineno)d} "
            "%(levelname)s - %(message)s"
        ),
        handlers=[stdout_handler],
    )


@click.group()
@click.option(
    "--log-level",
    default=20,
    help=(
        "Python logging level, default 20, can set from 0 to 50, step 10:"
        " https://docs.python.org/3/library/logging.html"
    ),
)
def main(log_level):
    config_log(log_level)


@main.command(help="Start a HTTP_SD server for Prometheus.")
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.option(
    "--connection-limit", "-c", default=1000, help="Server connection limit"
)
@click.option("--threads", "-t", default=64, help="Server threads")
@click.option(
    "--url_prefix",
    "-r",
    default="",
    help=(
        "The global url prefix, if set to /foo, then /targets will be"
        " available under /foo/targets"
    ),
)
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--cache-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--cache-seconds", "-m", default=300, help="Cache expire seconds"
)
@click.option(
    "--cache-refresh-interval", default=60, help="Cache expire seconds"
)
@click.option(
    "--update-threads",
    default=1024,
    help="Threads to execute user script in the background",
)
@click.option(
    "--enable-tracer",
    "-v",
    is_flag=True,
    help="Enable memory tracer, will print it into logs",
)
@click.option(
    "--sentry-url",
    "-s",
    help=(
        "Using sentry AMP(sentry.io) You need to manually pip install"
        " sentry-sdk"
    ),
)
def serve(
    host,
    port,
    connection_limit,
    threads,
    url_prefix,
    root_dir,
    cache_dir,
    cache_seconds,
    cache_refresh_interval,
    update_threads,
    enable_tracer,
    sentry_url,
):
    if sentry_url:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
        except ImportError:
            print(
                "import sentry_sdk failed, please pip install"
                " 'sentry-sdk[flask]'"
            )
            sys.exit(2)

        sentry_sdk.init(
            dsn=sentry_url,
            integrations=[
                FlaskIntegration(
                    transaction_style="url",
                ),
            ],
        )
        print("sentry sdk initialized!")
    config.root_dir = root_dir

    app = create_app(
        url_prefix,
        cache_dir,
        cache_seconds,
        cache_refresh_interval,
        update_threads,
    )

    if enable_tracer:
        start_tracing_thread()

    waitress.serve(
        app,
        host=host,
        port=port,
        connection_limit=connection_limit,
        threads=threads,
    )


@main.command(help="Run and verify the generators under target directory.")
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--ignore-path",
    "-i",
    multiple=True,
    help="Don't check this dir, starts with the same location as root",
)
def check(root_dir, ignore_path):
    config.root_dir = root_dir.rstrip("/")
    validate(root_dir, ignore_dirs=ignore_path)


@main.command(help="Start a server-only instance (HTTP API + job enqueueing).")
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.option(
    "--connection-limit", "-c", default=1000, help="Server connection limit"
)
@click.option("--threads", "-t", default=64, help="Server threads")
@click.option(
    "--url_prefix",
    "-r",
    default="",
    help=(
        "The global url prefix, if set to /foo, then /targets will be"
        " available under /foo/targets"
    ),
)
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--cache-seconds", "-m", default=300, help="Cache expire seconds"
)
@click.option(
    "--redis-url",
    default="redis://localhost:6379/0",
    help="Redis connection URL",
)
@click.option(
    "--log-level",
    default=20,
    help="Python logging level (0-50)",
)
def server_only(
    host,
    port,
    connection_limit,
    threads,
    url_prefix,
    root_dir,
    cache_seconds,
    redis_url,
    log_level,
):
    # Configure logging
    config_log(log_level)

    from .config import config
    from .redis.server import create_server_app

    # Initialize config
    config.__init__()
    config.root_dir = root_dir
    config.redis_url = redis_url
    config.cache_expire_seconds = cache_seconds

    app = create_server_app(
        url_prefix,
        cache_seconds,
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting server-only instance on {host}:{port}")
    logger.info("Workers must be started separately to process jobs.")

    waitress.serve(
        app,
        host=host,
        port=port,
        connection_limit=connection_limit,
        threads=threads,
    )


@main.command(help="Start a worker-only instance (job processing).")
@click.option(
    "--worker-id",
    default=None,
    help="Unique identifier for this worker (default: auto-generated)",
)
@click.option(
    "--num-workers",
    default=4,
    help="Number of workers to start",
)
@click.option(
    "--redis-url",
    default="redis://localhost:6379/0",
    help="Redis connection URL",
)
@click.option(
    "--cache-seconds", "-m", default=300, help="Cache expire seconds"
)
@click.option(
    "--log-level",
    default=20,
    help="Python logging level (0-50)",
)
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    help="The interface to bind metrics server to",
)
@click.option(
    "--port",
    "-p",
    default=8081,
    help="The port for worker metrics endpoint",
)
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def worker_only(
    worker_id,
    num_workers,
    redis_url,
    cache_seconds,
    log_level,
    host,
    port,
    root_dir,
):
    """Start a worker-only instance that processes jobs from Redis queue."""
    # Configure logging
    config_log(log_level)

    from .config import config
    from .redis.worker import WorkerPool

    # Initialize config
    config.__init__()
    config.root_dir = root_dir
    config.redis_url = redis_url
    config.cache_expire_seconds = cache_seconds

    # Use WorkerPool for both single worker and multiple workers
    num_workers = 1 if worker_id else num_workers
    worker_pool = WorkerPool(
        num_workers,
        first_worker_id=worker_id,
        metrics_port=port,
        metrics_host=host,
    )
    logger = logging.getLogger(__name__)

    if worker_id:
        logger.info(f"Starting single worker: {worker_id}")
    else:
        logger.info(f"Starting worker pool with {num_workers} workers")

    logger.info(
        f"Worker metrics will be available at " f"http://{host}:{port}/metrics"
    )

    worker_pool.start()

    # Set up signal handlers
    import signal

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        worker_pool.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        worker_pool.wait()
    except KeyboardInterrupt:
        # Fallback for any remaining KeyboardInterrupt cases
        logger.info("Received interrupt signal, shutting down...")
        worker_pool.stop()


if __name__ == "__main__":
    main()
