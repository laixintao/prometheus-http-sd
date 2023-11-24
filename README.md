# prometheus-http-sd

This is a
[Prometheus HTTP SD](https://prometheus.io/docs/prometheus/latest/http_sd/)
framework.

[![Test](https://github.com/laixintao/prometheus-http-sd/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/laixintao/prometheus-http-sd/actions/workflows/test.yaml)

<!-- vim-markdown-toc GFM -->

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [The Python Target Generator](#the-python-target-generator)
  - [Python Target Generator Cache and Throttle](#python-target-generator-cache-and-throttle)
  - [Manage prometheus-http-sd by systemd](#manage-prometheus-http-sd-by-systemd)
  - [Admin Page](#admin-page)
  - [Serve under a different root path](#serve-under-a-different-root-path)
  - [Sentry APM](#sentry-apm)
- [Define your targets](#define-your-targets)
  - [Your target generator](#your-target-generator)
  - [The Target Path](#the-target-path)
  - [Overwriting `job_name` labels](#overwriting-job_name-labels)
  - [Check and Validate your Targets](#check-and-validate-your-targets)
  - [Script Dependencies](#script-dependencies)
- [Update Your Scripts](#update-your-scripts)
- [Best Practice](#best-practice)

<!-- vim-markdown-toc -->

## Features

- Support static targets from Json file;
- Support static targets from Yaml file;
- Support generating target list using Python script;
- Support `check` command, to testing the generated target is as expected, and
  counting the targets;
- You can monitoring your target generator via `/metrics`, see
  [metrics](./docs/metrics.txt);
- Admin page to list all target paths;
- Auto reload when generator or targets changed;
- Support managing targets in a hierarchy way;
- Throttle parallel execution and cache the result for Python script;
- Support Sentry APM.

## Installation

```shell
pip install prometheus-http-sd
```

## Usage

First, you need a directory, everything in this directory will be used to
generate targets for prometheus-http-sd.

```shell
$ mkdir targets
```

In this directory, every file is called a target "generator":

- Filename that ending with `.json` will be exposed directly
- Filename that ending with `.yaml` will be exposed directly
- Filename that ending with `.py` must include a `generate_targets()` function,
  the function will be run, and it must return a `TargetList` (Type helper in
  `prometheus_http_sd.targets.`)
- Filename that starts with `_` will be ignored, so you can have some python
  utils there, for e.g. `_utils/__init__.py` that you can import in you
  `generate_targets()`
- Filename that starts with `.` (hidden file in Linux) will also be ignored

Let write our first target generator by yaml, put this into your
`targets/first_target.yaml`:

```yaml
---
- targets:
    - "10.1.1.9:9100"
    - "10.1.1.10:9100"
  labels:
    job: node
    datacenter: nyc
    group: g1
- targets:
    - "10.2.1.9:9100"
    - "10.2.1.10:9100"
  labels:
    job: node
    datacenter: sg
    group: g2
```

If you use json, the data structure is the same, just in Json format.

### The Python Target Generator

Let's put another generator using Python:

Put this into your `targets/by_python.py`:

```python
def generate_targets(**extra_parameters):
  return [{"targets": ["10.1.1.22:2379"], "labels": {"app": "etcd"}}]
```

Then you can run `prometheus-http-sd serve -h 0.0.0.0 -p 8080 /tmp/targets`,
prometheus-http-sd will start to expose targets at: http://0.0.0.0:8080/targets

The `-h` and `-p` is optional, defaults to `127.0.0.1` and `8080`.

```shell
$ prometheus-http-sd serve /tmp/targets # replace this to your target path
[2022-07-24 00:52:03,896] {wasyncore.py:486} INFO - Serving on http://127.0.0.1:8080
```

If you run `curl http://127.0.0.1:8080/targets` you will get:

```shell
{"targets": "10.1.1.22:2379", "labels": {"app": "etcd"}}
```

Finally, you can tell your Prometheus to find targets under
http://127.0.0.1:8080/targets, by adding this into your Prometheus config:

```yaml
scrape_configs:
  - job_name: "etcd"
    http_sd_config:
      url: http://127.0.0.1:8080/targets/
```

The Python target generator also support URL query params. You can check the
params in your `generate_targets()` function.

For example:

```python
def generate_targets(**params):
  cluster = params.get("cluster")
  return [{"targets": ["10.1.1.22:2379"], "labels": {"app": "etcd", "cluster": cluster}}]
```

Then `curl http://127.0.0.1:8080/targets?cluster=us1` you will get:

```shell
{"targets": "10.1.1.22:2379", "labels": {"app": "etcd", "cluster": "us1"}}
```

### Python Target Generator Cache and Throttle

Support you have 10 Prometheus instance request http-sd for targets every
minutes, for Python script target generator, it doesn't make sense that the same
script run 10 times in every minute, instead, it should run only once, and use
this result to respond for 10 Prometheus instances.

prometheus-http-sd has cache and throttle by default, that means:

- At any time there is only one python script running
- The result will be cached for 1minute (This means that every script at max
  will be only running one time per minute, and your target update will delay at
  most 1 minute)

### Manage prometheus-http-sd by systemd

Just put this file under `/lib/systemd/system/http-sd.service` (remember to
change your installation path and root_dir path):

```
# /lib/systemd/system/http-sd.service
[Unit]
Description=Prometheus HTTP SD Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/httpsd_env/bin/prometheus-http-sd serve \
    -h 0.0.0.0                                         \
    -p 8080                                            \
    /opt/httpsd_targets

Restart=always
RestartSec=90

[Install]
WantedBy=multi-user.target
```

### Admin Page

You can open the root path, `http://127.0.0.1:8080/` in this example, and you
will see all of the available paths list in the admin page.

![](./docs/admin1.png)

### Serve under a different root path

If you put prometheus-http-sd behind a reverse proxy like Nginx, like this:

```
location /http_sd/ {
      proxy_pass http://prometheus_http_sd;
}
```

Then you need to tell prometheus_http_sd to serve all HTTP requests under this
path, by using the `--url_prefix /http_sd` cli option, (or `-r /http_sd` for
short).

### Change Certificate

By default, `prometheus-http-sd` has caching capabilities for Python targets to avoid server crashes due to too many queries.
```
    +------------+
    |            |
    |            |
    |            |                  +-----------+
    |  Caller 1  +----+             |           |
    |            |    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    +------------+    |             |           |
                      |             |           |
                      |             |           |
    +------------+    |             |           |                  +----------+
    |            |    |             |           |                  |          |
    |            |    | call at the |           | only single call |          |
    |            |    |  same time  |  Timeout  |    to the back   |          |
    |  Caller 2  +----|------------>+   Cache   +----------------->+ Function |
    |            |    |             |           |                  |          |
    |            |    |             |           |                  |          |
    |            |    |             |           |                  |          |
    +------------+    |             |           |                  +----------+
                      |             |           |
                      |             |           |
    +------------+    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    |  Caller 3  +----+             |           |
    |            |                  +-----------+
    |            |
    |            |
    +------------+
```

To change this behavior, you can use the option `--cache-type` to change the cache behavior.

Also, you can use the option `--cache-opt` to change the variable.
For example:

```bash
prometheus-http-sd serve       \
    -h 0.0.0.0                 \
    -p 8080                    \
    --cache-type="Timeout"     \
    --cache-opt="timeout=360"  \
    /opt/httpsd_targets

```

#### Timeout

This is the default value, It will cache the result or exception from the target function.
* `timeout=<seconds>`:
  function timeout. if exceed, raise TimeoutException (in sec).
* `cache_time=<seconds>`:
  after function return normally, how long should we cache the result (in sec).
* `cache_exception_time=<seconds>`:
  after function return incorrectly, how long should we cache the exception (in sec).
* `name=<str>`:
  prometheus_client metrics prefix
* `garbage_collection_count=<seconds>`:
  garbage collection threshold
* `garbage_collection_interval=<seconds>`:
  the second to avoid collection too often.
* `copy_response=<bool>`:
  if true, use copy.deepcopy on the response from the target function.
    
    
#### None

This is a dummy function if you don't need any cache method.

### Sentry APM

You can use the option `--sentry-url <you-sentry-url>` (or `-s <your-sentry-url>`)
to enable Sentry APM.

The Exception from user's script will be sent to Sentry.

## Define your targets

### Your target generator

Please see the [Usage](#usage) to know how to define your generator.

### The Target Path

prometheus-http-sd support sub-pathes.

For example, if we use `prometheus-http-sd serve gateway`, and the `gateway`
directory's structure is as follows:

```shell
gateway
├── nginx
│   ├── edge.py
│   └── targets.json
└── targets.json
```

Then:

- `/targets/gateway` will return the targets from:
  - `gateway/nginx/edge.py`
  - `gateway/nginx/targets.json`
  - `gateway/targets.json`
- `/targets/gateway/nginx` will return the targets from:
  - `gateway/nginx/edge.py`
  - `gateway/nginx/targets.json`

This is very useful when you use vertical scaling. Say you have 5 Prometheus
instances, and you want each one of them scrape for different targets, then you
can use the sub-path feature of prometheus-http-sd.

For example, in one Prometheus's scrape config:

```yaml
scrape_configs:
  - job_name: "nginx"
    http_sd_config:
      url: http://prometheus-http-sd:8080/targets/nginx

  - job_name: "etcd"
    http_sd_config:
      url: http://prometheus-http-sd:8080/targets/etcd
```

And in another one:

```yaml
scrape_configs:
  - job_name: "nginx"
    http_sd_config:
      url: http://prometheus-http-sd:8080/targets/database

  - job_name: "etcd"
    http_sd_config:
      url: http://prometheus-http-sd:8080/targets/application
```

### Overwriting `job_name` labels

You may want to put all of etcd targets in one generator, including port 2379
for etcd metrics and 9100 for node_exporter metrics of the etcd server. But the
`job_name` setting was based on per URL.

The trick is that, you can overwrite the `job` label in the target labels, like
this:

```yaml
---
- targets:
    - "10.1.1.9:9100"
  labels:
    job: node
    datacenter: nyc
    group: g1
- targets:
    - "10.1.1.9:2379"
  labels:
    job: etcd
    datacenter: nyc
    group: g1
```

### Check and Validate your Targets

You can use `prometheus-http-sd check` command to test your targets dir. It will
run all of you generators, validate the targets, and print the targets count
that each generator generates.

```shell
$ prometheus-http-sd check test/test_generator/root
[2022-08-06 00:50:11,095] {validate.py:16} INFO - Run generator test/test_generator/root/json/target.json, took 0.0011398792266845703s, generated 1 targets.
[2022-08-06 00:50:11,100] {validate.py:16} INFO - Run generator test/test_generator/root/yaml/target.yaml, took 0.0043718814849853516s, generated 2 targets.
[2022-08-06 00:50:11,100] {validate.py:22} INFO - Done! Generated {total_targets} in total.
```

It's a good idea to use `prometheus-http-sd check` in your CI system to validate
your targets generator scripts and target files.

For Python script, `prometheus-http-sd check` command will run
`generate_targets` in each script, without any params. However, you can
overwrite the `check` logic by providing a function called
`test_generate_targets()`(without any function args), then `check` will run
`test_generate_targets` instead. (So you can call `generate_targets(foo="bar")`
to set the test logic of your own.

### Script Dependencies

If you want your scripts to use some other python library, just install them
into the **same virtualenv** that you install prometheus-http-sd, so that
prometheus-http-sd can import them.

## Update Your Scripts

If you want to update your script file or target json file, just upload and
overwrite with your new version, it will take effect immediately after you
making changes, **there is no need to restart** prometheus-http-sd,
prometheus-http-sd will read the file (or reload the python script) every time
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

Also for the same reason, if your script met any error, you should throw out
`Exception` all the way to the top instead of catch it in your script and return
a null `TargetList`, if you return a null `TargetList`, prometheus-http-sd will
think that your script run successfully and empty the target list as well.

You can notice this error from stdout logs or `/metrics` from
prometheus-http-sd.

## Best Practice

You can use a git repository to manage your target generator.
