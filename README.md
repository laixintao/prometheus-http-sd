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

## Update Your Scripts

If you have changed your script in `targets` directory, you should restart
prometheus-http-sd to make it work. For files target list like `.json`, it will
take effect immediately after you making changes, **there is no need to
restart** prometheus-http-sd, prometheus-http-sd will read the file every time
serving a request.

## Best Practice

You can use a git repository to manage your target generator.
