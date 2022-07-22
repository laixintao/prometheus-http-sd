# prometheus-http-sd

This is a
[Prometheus HTTP SD](https://prometheus.io/docs/prometheus/latest/http_sd/)
framework.

## Features

- Support static targets json file;
- Support generating target list using Python script;

## Installation

## Usage

First, you need a directory, everything in this directory will be used to
generate targets for prometheus-http-sd.

```shell
$ mkdir targets
```

In this directory:

- Filename that ending with `.json` will be exposed directly
- Filename that ending with `.py` must include a `generate_targets()` function,
  the function will be run, and it must return a `TargetList` (Type helper in
  `prometheus_http_sd.targets.`)
- Filename that starts with `_` will be ignored, so you can have some python
  utils there, for e.g. `_utils/__init__.py` that you can import in you
  `generate_targets()`

Then, you need to tell prometheus-http-sd where it can find your targets
directory by exporting an environment variable:

```shell
$ export PROMETHEUS_HTTP_SD_DIR=/tmp/targets
```

Finally, you can run `prometheus-http-sd serve 0.0.0.0 8080`.

## Using Different Pathes

## Update Your Scripts

If you have changed your script in `targets` directory, you should restart
prometheus-http-sd to make it work. For files target list like `.json`, it will
take effect immediately after you making changes, **there is no need to
restart** prometheus-http-sd, prometheus-http-sd will read the file every time
serving a request.

It is worth noting that restarting is safe because if Prometheus failed to get
the target list via HTTP request, it won't update its current target list to
empty, instead,
[it will keep using the current list](https://prometheus.io/docs/prometheus/latest/http_sd/).

> Prometheus caches target lists. If an error occurs while fetching an updated
> targets list, Prometheus keeps using the current targets list.

For the same reason, if there are 3 scripts under `/targets/mysystem` and only
one failed for a request, prometheus-http-sd will return a HTTP 500 Error for
the whole request instead of returning the partial targets from the other two
scripts.

You can notice this error from stdout logs or `/metrics` from
prometheus-http-sd.

## Best Practice

You can use a git repository to manage your target generator.
