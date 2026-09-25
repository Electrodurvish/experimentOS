"""
Gunicorn settings loaded automatically from the working directory (/app).

Command-line flags and GUNICORN_CMD_ARGS still override these values.
With several workers, set PROMETHEUS_MULTIPROC_DIR to a writable, per-pod
directory (e.g. an emptyDir) so /metrics aggregates all workers.
"""

import os
import shutil

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
timeout = 30
graceful_timeout = 30
accesslog = "-"


def on_starting(server):
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory, exist_ok=True)


def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)


def worker_exit(server, worker):
    # Deliver buffered Kafka events accepted with 202 before the worker goes away.
    try:
        from apps.events.producer import flush_producer

        flush_producer()
    except Exception:
        pass
