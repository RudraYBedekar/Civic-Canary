from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from agent.civic_canary.models import Run, RunStatus, TriggerType
from services.observability import log_event
from services.runtime import ScanService
from services.store_factory import default_store


def handler(event, context):
    store = default_store()
    target_id = event.get("target_id", "benefits-demo")
    target = store.get_target(target_id)
    if target is None:
        raise ValueError(f"target not found: {target_id}")
    trigger = TriggerType(event.get("trigger_type", TriggerType.SCHEDULED.value))
    run_id = event.get("run_id") or f"run-scheduled-{uuid.uuid4().hex[:10]}"
    service = ScanService(store)
    queued = store.get_run(run_id)
    running = queued or Run(
        run_id=run_id,
        target_id=target.target_id,
        trigger_type=trigger,
    )
    running.status = RunStatus.RUNNING
    running.started_at = running.started_at or datetime.now(UTC)
    store.put_run(running)
    try:
        if service.agentcore_arn():
            result = service.invoke_agentcore(target, trigger, run_id)
            returned_run = Run.model_validate(result.get("run", {}))
            if returned_run.status == RunStatus.FAILED:
                raise RuntimeError(returned_run.summary or "AgentCore scan failed")
            return result
        run, findings = asyncio.run(service.run_local(target, trigger, run_id))
        return {"run": run.model_dump(mode="json"), "finding_count": len(findings)}
    except Exception as exc:
        existing = store.get_run(run_id) or running
        if existing.status != RunStatus.FAILED:
            existing.status = RunStatus.FAILED
            existing.finished_at = datetime.now(UTC)
            existing.error_category = type(exc).__name__
            existing.summary = str(exc)
            store.put_run(existing)
        log_event(
            "scan_worker_failed",
            run_id=run_id,
            target_id=target.target_id,
            error_category=type(exc).__name__,
        )
        raise
