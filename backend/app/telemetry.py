"""Bounded, process-local API telemetry and live host resource sampling."""

import os
import shutil
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter, time

LATENCY_BANDS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000)
MAX_MINUTES = 1440


def _cpu_times():
    if os.name == "nt":
        import ctypes
        from ctypes.wintypes import FILETIME

        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            def value(clock):
                return (clock.dwHighDateTime << 32) | clock.dwLowDateTime

            return value(idle), value(kernel) + value(user)
    elif Path("/proc/stat").is_file():
        with Path("/proc/stat").open(encoding="ascii") as source:
            header, *ticks = source.readline().split()
        if header == "cpu" and len(ticks) >= 8:
            ticks = list(map(int, ticks[:8]))
            return ticks[3] + ticks[4], sum(ticks)
    return None


def _memory():
    if os.name == "nt":
        import ctypes
        from ctypes.wintypes import DWORD

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("size", DWORD),
                ("load", DWORD),
                ("capacity", ctypes.c_ulonglong * 7),
            ]

        status = MemoryStatus()
        status.size = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return float(status.load)
    elif Path("/proc/meminfo").is_file():
        values = {}
        with Path("/proc/meminfo").open(encoding="ascii") as source:
            for line in source:
                name, _, raw = line.partition(":")
                if name in {"MemTotal", "MemAvailable"}:
                    values[name] = int(raw.split()[0])
        total, available = values.get("MemTotal"), values.get("MemAvailable")
        if total and available is not None:
            return round(100 * (total - available) / total, 2)
    return None


def _sample(operation):
    try:
        return operation()
    except (OSError, ValueError):
        return None


@dataclass
class Minute:
    requests: int = 0
    errors: int = 0
    milliseconds: float = 0
    maximum: float = 0
    latency: list[int] = field(default_factory=lambda: [0] * (len(LATENCY_BANDS) + 1))

    def record(self, status, elapsed_ms):
        self.requests += 1
        self.errors += int(status >= 500)
        self.milliseconds += elapsed_ms
        self.maximum = max(self.maximum, elapsed_ms)
        self.latency[bisect_left(LATENCY_BANDS, elapsed_ms)] += 1


class Telemetry:
    def __init__(self, clock=time):
        self._clock = clock
        self.started_at = datetime.fromtimestamp(clock(), timezone.utc)
        self._minutes: dict[int, Minute] = {}
        self._current_minute = None
        self._cpu = _sample(_cpu_times)
        self._lock = Lock()

    def record(self, status, elapsed_ms):
        minute = int(self._clock() // 60)
        with self._lock:
            if minute != self._current_minute:
                self._minutes = {
                    key: sample for key, sample in self._minutes.items()
                    if minute - MAX_MINUTES < key <= minute
                }
                self._current_minute = minute
            sample = self._minutes.get(minute)
            if sample is None:
                sample = self._minutes[minute] = Minute()
            sample.record(status, elapsed_ms)

    def snapshot(self, window):
        now = self._clock()
        minute = int(now // 60)
        current_cpu = _sample(_cpu_times)
        memory = _sample(_memory)
        disk = _sample(lambda: shutil.disk_usage(Path(__file__).resolve().parent))
        cpu = None
        with self._lock:
            if current_cpu is not None:
                if self._cpu is not None:
                    idle = current_cpu[0] - self._cpu[0]
                    elapsed = current_cpu[1] - self._cpu[1]
                    if 0 <= idle <= elapsed and elapsed:
                        cpu = round(100 * (elapsed - idle) / elapsed, 2)
                self._cpu = current_cpu

            rows = []
            requests = errors = 0
            milliseconds = maximum = 0.0
            histogram = [0] * (len(LATENCY_BANDS) + 1)
            for key, sample in sorted(self._minutes.items()):
                if not minute - window < key <= minute:
                    continue
                requests += sample.requests
                errors += sample.errors
                milliseconds += sample.milliseconds
                maximum = max(maximum, sample.maximum)
                histogram = [left + right for left, right in zip(histogram, sample.latency)]
                rows.append({
                    "date": datetime.fromtimestamp(key * 60, timezone.utc),
                    "requests": sample.requests,
                    "errors": sample.errors,
                    "latency_ms": round(sample.milliseconds / sample.requests, 2),
                })

        percentile = None
        if requests:
            rank = (requests * 95 + 99) // 100
            for index, count in enumerate(histogram):
                rank -= count
                if rank <= 0:
                    percentile = min(maximum, LATENCY_BANDS[index]) if index < len(LATENCY_BANDS) else maximum
                    break
        return {
            "sampled_at": datetime.fromtimestamp(now, timezone.utc),
            "window_minutes": window,
            "cpu": cpu,
            "memory": memory,
            "disk": round(100 * disk.used / disk.total, 2) if disk and disk.total else None,
            "requests": requests,
            "errors": errors,
            "latency_ms": round(milliseconds / requests, 2) if requests else None,
            "p95_latency_ms": round(percentile, 2) if percentile is not None else None,
            "buckets": rows,
        }


class ApiTelemetryMiddleware:
    def __init__(self, app, telemetry):
        self._app = app
        self._telemetry = telemetry

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope["type"] != "http" or not path.startswith("/api/v1/")
            or path.startswith("/api/v1/health") or path == "/api/v1/admin/telemetry"):
            await self._app(scope, receive, send)
            return

        started = perf_counter()
        status = 500

        async def observe(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, observe)
        finally:
            self._telemetry.record(status, (perf_counter() - started) * 1000)
