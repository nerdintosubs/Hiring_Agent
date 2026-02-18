from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import Request

logger = logging.getLogger("hiring_agent")


@dataclass
class MetricsSnapshot:
    requests_total: int
    requests_5xx: int
    total_latency_ms: float


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests_total = 0
        self._requests_5xx = 0
        self._total_latency_ms = 0.0
        self._by_route_status: dict[tuple[str, int], int] = {}

    def record(self, *, route: str, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self._requests_total += 1
            if status_code >= 500:
                self._requests_5xx += 1
            self._total_latency_ms += latency_ms
            key = (route, status_code)
            self._by_route_status[key] = self._by_route_status.get(key, 0) + 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                requests_total=self._requests_total,
                requests_5xx=self._requests_5xx,
                total_latency_ms=self._total_latency_ms,
            )

    def to_prometheus(self) -> str:
        snap = self.snapshot()
        avg_latency = (
            snap.total_latency_ms / snap.requests_total if snap.requests_total else 0.0
        )
        lines = [
            "# HELP hiring_agent_requests_total Total HTTP requests",
            "# TYPE hiring_agent_requests_total counter",
            f"hiring_agent_requests_total {snap.requests_total}",
            "# HELP hiring_agent_requests_5xx_total Total 5xx HTTP requests",
            "# TYPE hiring_agent_requests_5xx_total counter",
            f"hiring_agent_requests_5xx_total {snap.requests_5xx}",
            "# HELP hiring_agent_request_avg_latency_ms Average request latency ms",
            "# TYPE hiring_agent_request_avg_latency_ms gauge",
            f"hiring_agent_request_avg_latency_ms {avg_latency:.2f}",
        ]
        with self._lock:
            for (route, status_code), count in sorted(self._by_route_status.items()):
                metric_line = (
                    'hiring_agent_route_requests_total'
                    f'{{route="{route}",status="{status_code}"}} {count}'
                )
                lines.append(
                    metric_line
                )
        return "\n".join(lines) + "\n"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def observe_request(
    request: Request,
    call_next,
    *,
    metrics: MetricsRegistry,
):
    start = time.perf_counter()
    path = request.url.path
    try:
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000.0
        metrics.record(route=path, status_code=response.status_code, latency_ms=latency_ms)
        logger.info(
            "request_complete method=%s path=%s status=%s latency_ms=%.2f",
            request.method,
            path,
            response.status_code,
            latency_ms,
        )
        return response
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000.0
        metrics.record(route=path, status_code=500, latency_ms=latency_ms)
        logger.exception(
            "request_failed method=%s path=%s latency_ms=%.2f",
            request.method,
            path,
            latency_ms,
        )
        raise
