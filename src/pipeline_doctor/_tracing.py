"""Tracing shim. The package stays free of telemetry dependencies: an adopting project may replace `traced`
with its own OpenTelemetry decorator (`pipeline_doctor.doctor.traced = my_traced` before use)."""

from __future__ import annotations

import functools


def traced(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper
