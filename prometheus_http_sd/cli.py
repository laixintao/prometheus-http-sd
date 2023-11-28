import logging
import sys
import click
import waitress

from .mem_perf import start_tracing_thread
from .config import config
from .validate import validate
from .app import create_app
from .sd import py_cache


def config_log(level):
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    logging.basicConfig(
        level=level,
        format=(
            "[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s -"
            " %(message)s"
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
@click.option(
    "--cache-type",
    help='Cache of "py_run" function. Can be None or Timeout.',
    type=click.Choice(["Timeout", "None"]),
    default="Timeout",
)
@click.option(
    "--cache-opt",
    help=(
        "Options pass to the cache object."
        "Input format should be k=v. ex: timeout=1"
    ),
    multiple=True,
    default=[
        "timeout=60",
        "cache_time=60",
        "name=target_generator",
        "garbage_collection_count=100",
    ],
)
def serve(
    host,
    port,
    connection_limit,
    threads,
    url_prefix,
    root_dir,
    enable_tracer,
    sentry_url,
    cache_type,
    cache_opt,
):
    config.root_dir = root_dir
    app = create_app(url_prefix)

    setup_cache(cache_type, cache_opt)

    if enable_tracer:
        start_tracing_thread()

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
            enable_tracing=True,
            integrations=[
                FlaskIntegration(
                    transaction_style="url",
                ),
            ],
        )
        print("sentry sdk initialized!")

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


def setup_cache(cache_type, config_opt):
    kwargs = {}
    for opt in config_opt:
        try:
            key, value = opt.split("=", 1)
        except ValueError:
            print(
                "value format incorrect. required key=value, but get %s" % opt,
                file=sys.stderr,
            )
            sys.exit(127)
        kwargs[key] = value
    py_cache.select_decorator(cache_type, **kwargs)


if __name__ == "__main__":
    main()
