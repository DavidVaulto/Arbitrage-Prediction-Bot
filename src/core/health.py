"""Health check and monitoring endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .types import HealthStatus, Venue


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    version: str
    uptime_seconds: float
    venues: list[HealthStatus]
    system: dict[str, Any]


class MetricsResponse(BaseModel):
    """Metrics response model."""

    timestamp: datetime
    trades: dict[str, int]
    portfolio: dict[str, float]
    risk: dict[str, float]
    discovery: dict[str, int]


class HealthMonitor:
    """Health monitoring service."""

    def __init__(self, app: FastAPI | None = None):
        """Initialize health monitor.
        
        Args:
            app: FastAPI application instance
        """
        self.app = app or FastAPI(title="PM Arbitrage Bot Health")
        self.start_time = datetime.utcnow()
        self.version = "0.1.0"

        # Health status for venues
        self.venue_health: dict[Venue, HealthStatus] = {}

        # System metrics
        self.system_metrics: dict[str, Any] = {}

        # Setup routes
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup health check routes."""

        @self.app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint."""
            return await self.get_health_status()

        @self.app.get("/metrics", response_model=MetricsResponse)
        async def get_metrics():
            """Metrics endpoint."""
            return await self.get_metrics()

        @self.app.get("/ready")
        async def readiness_check():
            """Readiness check endpoint."""
            if await self.is_ready():
                return {"status": "ready"}
            else:
                raise HTTPException(status_code=503, detail="Not ready")

        @self.app.get("/live")
        async def liveness_check():
            """Liveness check endpoint."""
            if await self.is_alive():
                return {"status": "alive"}
            else:
                raise HTTPException(status_code=503, detail="Not alive")

    def get_health_status(self) -> HealthResponse:
        """Get comprehensive health status."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()

        # Simple health check without async
        is_healthy = len(self.venue_health) == 0 or all(
            status.is_healthy for status in self.venue_health.values()
        )

        return HealthResponse(
            status="healthy" if is_healthy else "unhealthy",
            timestamp=datetime.utcnow(),
            version=self.version,
            uptime_seconds=uptime,
            venues=list(self.venue_health.values()),
            system=self.system_metrics,
        )

    async def get_metrics(self) -> MetricsResponse:
        """Get system metrics."""
        return MetricsResponse(
            timestamp=datetime.utcnow(),
            trades=self.system_metrics.get("trades", {}),
            portfolio=self.system_metrics.get("portfolio", {}),
            risk=self.system_metrics.get("risk", {}),
            discovery=self.system_metrics.get("discovery", {}),
        )

    async def is_healthy(self) -> bool:
        """Check if system is healthy."""
        # Check venue health
        for venue_status in self.venue_health.values():
            if not venue_status.is_healthy:
                return False

        # Check system metrics
        if self.system_metrics.get("error_rate", 0) > 0.1:
            return False

        return True

    async def is_ready(self) -> bool:
        """Check if system is ready to accept requests."""
        # Check if all venues are connected
        for venue_status in self.venue_health.values():
            if not venue_status.is_healthy:
                return False

        return True

    async def is_alive(self) -> bool:
        """Check if system is alive."""
        # Simple liveness check
        return True

    def update_venue_health(self, venue: Venue, status: HealthStatus) -> None:
        """Update health status for a venue."""
        self.venue_health[venue] = status

    def update_system_metrics(self, metrics: dict[str, Any]) -> None:
        """Update system metrics."""
        self.system_metrics.update(metrics)

    def get_app(self) -> FastAPI:
        """Get FastAPI application."""
        return self.app


# Global health monitor instance
health_monitor = HealthMonitor()
