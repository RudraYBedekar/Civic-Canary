from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from .analysis import detect_changes, findings_from_changes
from .browser import BrowserAdapter, UnsafeTargetError
from .models import Finding, NodeTiming, PortalSnapshot, PortalTarget, Run, RunStatus, TriggerType


class CivicCanaryEngine:
    def __init__(self, browser: BrowserAdapter) -> None:
        self.browser = browser

    async def execute(
        self,
        *,
        target: PortalTarget,
        baseline: PortalSnapshot,
        playbook: str,
        trigger_type: TriggerType = TriggerType.MANUAL,
        run_id: str | None = None,
    ) -> tuple[Run, PortalSnapshot, list[Finding]]:
        run = Run(
            run_id=run_id or f"run-{uuid.uuid4().hex[:12]}",
            target_id=target.target_id,
            trigger_type=trigger_type,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        active_node = "capture"
        node_started = time.perf_counter()
        try:
            for attempt in range(2):
                try:
                    current = await self.browser.capture(target, run.run_id)
                    break
                except UnsafeTargetError:
                    raise
                except Exception:
                    if attempt == 1:
                        raise
                    run.retry_count += 1
            run.node_timings.append(self._timing(active_node, node_started))

            active_node = "semantic-diff-and-accessibility"
            node_started = time.perf_counter()
            changes = detect_changes(baseline, current)
            run.node_timings.append(self._timing(active_node, node_started))

            active_node = "impact-map-and-repair-draft"
            node_started = time.perf_counter()
            findings = findings_from_changes(
                changes, run_id=run.run_id, target_id=target.target_id, playbook=playbook
            )
            baseline_key = f"baselines/{target.target_id}.json"
            snapshot_key = f"snapshots/{target.target_id}/{run.run_id}/snapshot.json"
            for finding in findings:
                finding.evidence_keys.extend([baseline_key, snapshot_key])
                source_url = next(
                    (
                        evidence.removeprefix("Observed at ")
                        for evidence in finding.evidence
                        if evidence.startswith("Observed at ")
                    ),
                    None,
                )
                page_index = next(
                    (
                        index
                        for index, item in enumerate(current.pages)
                        if item.url == source_url
                    ),
                    None,
                )
                if page_index is not None:
                    current_page = current.pages[page_index]
                    if page_index < len(baseline.pages):
                        baseline_page = baseline.pages[page_index]
                        if baseline_page.screenshot_key:
                            finding.evidence_keys.append(baseline_page.screenshot_key)
                    if current_page.screenshot_key:
                        finding.evidence_keys.append(current_page.screenshot_key)
            run.node_timings.append(self._timing(active_node, node_started))

            active_node = "decision-gate"
            node_started = time.perf_counter()
            findings = [finding for finding in findings if finding.materiality != "COSMETIC"]
            run.node_timings.append(self._timing(active_node, node_started))
            run.status = RunStatus.SUCCEEDED
            run.summary = (
                "No material changes detected."
                if not findings
                else f"Detected {len(findings)} material finding(s) requiring review."
            )
            return run, current, findings
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_category = type(exc).__name__
            run.summary = str(exc)
            if not run.node_timings or run.node_timings[-1].node != active_node:
                run.node_timings.append(self._timing(active_node, node_started, "FAILED"))
            raise RunExecutionError(run, exc) from exc
        finally:
            run.finished_at = datetime.now(UTC)

    @staticmethod
    def _timing(
        node: str, started: float, status: str = "SUCCEEDED"
    ) -> NodeTiming:
        return NodeTiming(
            node=node,
            duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
            status=status,
        )


class RunExecutionError(RuntimeError):
    def __init__(self, run: Run, cause: Exception) -> None:
        super().__init__(run.summary)
        self.run = run
        self.cause = cause
