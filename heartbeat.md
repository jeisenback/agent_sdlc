# Heartbeat / Liveness Design

This document defines the heartbeat and liveness checks used by `agent_sdlc` to monitor provider and adapter health.

## Purpose
- Provide a lightweight liveness probe for long-running agents and adapter connections.

## Heartbeat model
- Interval: default 30s (configurable)
- Probe types:
  - `ping` for providers: a small no-op request or provider-specific health endpoint
  - `connection_check` for DB adapters: simple `SELECT 1` or SQLAlchemy `engine.execute("SELECT 1")`

## Failure handling
- Consecutive failures threshold: 3 (configurable)
- On threshold breach: mark service unhealthy, emit structured log and metric, attempt backoffed reconnects.
- Reconnect policy: exponential backoff with max interval (default 5 minutes).

## Observability
- Emit metrics: `heartbeat.success`, `heartbeat.failure`, `heartbeat.latency_ms` with tags `component=provider|db`, `name=<provider_name>`.

## API (conceptual)
```
class HeartbeatMonitor:
    def start(self): ...
    def stop(self): ...
    def status(self) -> HealthStatus: ...
```
