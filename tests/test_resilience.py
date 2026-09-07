import json
from decimal import Decimal
from pathlib import Path

import pytest
from strands.multiagent.base import Status

from agent.civic_canary.browser import BrowserAdapter, FixtureBrowserAdapter
from agent.civic_canary.engine import RunExecutionError
from agent.civic_canary.models import PortalSnapshot, PortalTarget, TriggerType
from agent.civic_canary.strands_graph import (
    CaptureReview,
    ReviewMemo,
    validated_review_memo,
)
from services import scheduled_handler
from services.runtime import ScanService
from services.storage import InMemoryStore, _dynamo_item

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "web" / "public" / "portal"
PLAYBOOK = (ROOT / "agent" / "fixtures" / "benefits-playbook.md").read_text()


class AlwaysFailBrowser(BrowserAdapter):
    def __init__(self) -> None:
        self.calls = 0

    async def capture(self, target: PortalTarget, run_id: str) -> PortalSnapshot:
        self.calls += 1
        raise TimeoutError("browser session timed out")


@pytest.mark.asyncio
async def test_failed_browser_run_is_retried_and_persisted() -> None:
    target = PortalTarget(active_version="v2")
    baseline = await FixtureBrowserAdapter(FIXTURES).capture(
        target.model_copy(update={"active_version": "v1"}), "baseline"
    )
    store = InMemoryStore(playbook=PLAYBOOK)
    store.put_target(target)
    store.put_baseline(baseline)
    browser = AlwaysFailBrowser()

    with pytest.raises(RunExecutionError):
        await ScanService(store, browser).run_local(
            target, TriggerType.MANUAL, "run-browser-timeout"
        )

    failed = store.get_run("run-browser-timeout")
    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.error_category == "TimeoutError"
    assert failed.retry_count == 1
    assert failed.node_timings[-1].status == "FAILED"
    assert browser.calls == 2


def test_dynamo_serialization_converts_floats_to_decimal() -> None:
    target = PortalTarget()
    item = _dynamo_item(target.model_copy(update={"target_id": "decimal-check"}))
    assert item["target_id"] == "decimal-check"
    assert _dynamo_item(ReviewMemo(summary="ok", quoted_evidence=["proof"])) == {
        "summary": "ok",
        "quoted_evidence": ["proof"],
        "proposed_patches": [],
        "needs_review": False,
    }

    class ConfidenceModel(ReviewMemo):
        confidence: float

    with_confidence = _dynamo_item(
        ConfidenceModel(summary="ok", quoted_evidence=["proof"], confidence=0.95)
    )
    assert with_confidence["confidence"] == Decimal("0.95")


def test_strands_final_node_requires_validated_structured_output() -> None:
    memo = ReviewMemo(summary="Evidence verified", quoted_evidence=["portal quote"])
    graph_result = type(
        "GraphResultDouble",
        (),
        {
            "status": Status.COMPLETED,
            "results": {
                "capture": type(
                    "NodeResultDouble",
                    (),
                    {
                        "status": Status.COMPLETED,
                        "result": type(
                            "AgentResultDouble",
                            (),
                            {
                                "structured_output": CaptureReview(
                                    safe_to_analyze=True,
                                    evidence_scope=["baseline/current snapshots"],
                                )
                            },
                        )(),
                    },
                )(),
                "repair": type(
                    "NodeResultDouble",
                    (),
                    {
                        "status": Status.COMPLETED,
                        "result": type(
                            "AgentResultDouble", (), {"structured_output": memo}
                        )(),
                    },
                )()
            },
        },
    )()
    assert validated_review_memo(graph_result) == memo


def test_agentcore_scan_is_durably_queued_before_async_dispatch(monkeypatch) -> None:
    store = InMemoryStore(playbook=PLAYBOOK)
    target = PortalTarget()
    store.put_target(target)
    calls: list[dict] = []

    class LambdaClient:
        def invoke(self, **kwargs):
            calls.append(kwargs)
            return {"StatusCode": 202}

    monkeypatch.setenv("SCAN_WORKER_FUNCTION_NAME", "civic-canary-worker")
    monkeypatch.setattr(
        "services.runtime.boto3.client", lambda service, **_kwargs: LambdaClient()
    )
    run = ScanService(store).queue_agentcore_scan(
        target, TriggerType.MANUAL, "run-queued"
    )

    assert run.status == "QUEUED"
    assert store.get_run("run-queued").status == "QUEUED"
    assert calls[0]["InvocationType"] == "Event"
    assert json.loads(calls[0]["Payload"])["run_id"] == "run-queued"

    repeated = ScanService(store).queue_agentcore_scan(
        target, TriggerType.MANUAL, "run-queued"
    )
    assert repeated.run_id == "run-queued"
    assert len(calls) == 1


def test_worker_invocation_failure_is_persisted(monkeypatch) -> None:
    store = InMemoryStore(playbook=PLAYBOOK)
    store.put_target(PortalTarget())
    monkeypatch.setattr(scheduled_handler, "default_store", lambda: store)
    monkeypatch.setattr(ScanService, "agentcore_arn", lambda _self: "arn:runtime")

    def fail_invoke(_self, _target, _trigger, _run_id):
        raise TimeoutError("AgentCore timed out")

    monkeypatch.setattr(ScanService, "invoke_agentcore", fail_invoke)
    with pytest.raises(TimeoutError):
        scheduled_handler.handler(
            {
                "run_id": "run-worker-failed",
                "target_id": "benefits-demo",
                "trigger_type": "MANUAL",
            },
            None,
        )
    failed = store.get_run("run-worker-failed")
    assert failed.status == "FAILED"
    assert failed.error_category == "TimeoutError"
