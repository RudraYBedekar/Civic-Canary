from pathlib import Path

import pytest

from agent.civic_canary.analysis import detect_changes
from agent.civic_canary.browser import (
    FixtureBrowserAdapter,
    UnsafeTargetError,
    request_is_allowed,
    validate_target,
)
from agent.civic_canary.engine import CivicCanaryEngine
from agent.civic_canary.models import PortalTarget

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "web" / "public" / "portal"
PLAYBOOK = (ROOT / "agent" / "fixtures" / "benefits-playbook.md").read_text()


@pytest.mark.asyncio
async def test_v1_matches_baseline() -> None:
    browser = FixtureBrowserAdapter(FIXTURES)
    target = PortalTarget(active_version="v1")
    baseline = await browser.capture(target, "baseline")
    run, _, findings = await CivicCanaryEngine(browser).execute(
        target=target, baseline=baseline, playbook=PLAYBOOK
    )
    assert run.status == "SUCCEEDED"
    assert findings == []


@pytest.mark.asyncio
async def test_v2_detects_three_material_regressions() -> None:
    browser = FixtureBrowserAdapter(FIXTURES)
    baseline_target = PortalTarget(active_version="v1")
    baseline = await browser.capture(baseline_target, "baseline")
    current_target = PortalTarget(active_version="v2")
    run, _, findings = await CivicCanaryEngine(browser).execute(
        target=current_target, baseline=baseline, playbook=PLAYBOOK
    )
    assert run.status == "SUCCEEDED"
    assert {finding.category for finding in findings} == {
        "REQUIREMENT",
        "BROKEN_LINK",
        "ACCESSIBILITY",
    }
    assert all(finding.evidence and finding.proposed_patch for finding in findings)
    assert all(finding.affected_playbook_sections for finding in findings)


def test_rejects_non_allowlisted_live_target() -> None:
    target = PortalTarget(
        start_url="https://untrusted.example/apply",
        allowed_hosts=["benefits.example.gov"],
    )
    with pytest.raises(UnsafeTargetError):
        validate_target(target)


def test_browser_policy_blocks_writes_off_host_and_forbidden_journeys() -> None:
    allowed = ["benefits.example.gov"]
    assert request_is_allowed("GET", "https://benefits.example.gov/help", allowed)
    assert not request_is_allowed("POST", "https://benefits.example.gov/apply", allowed)
    assert not request_is_allowed("GET", "https://analytics.example/collect", allowed)
    with pytest.raises(UnsafeTargetError):
        validate_target(
            PortalTarget(
                start_url="https://benefits.example.gov/",
                allowed_hosts=allowed,
                journey_steps=[{"path": "/login", "label": "Sign in"}],
            )
        )


@pytest.mark.asyncio
async def test_high_signal_ordinary_copy_change_requires_review() -> None:
    browser = FixtureBrowserAdapter(FIXTURES)
    target = PortalTarget(active_version="v1")
    baseline = await browser.capture(target, "baseline")
    current = baseline.model_copy(deep=True, update={"run_id": "current"})
    current.pages[0].semantic_blocks = [
        *current.pages[0].semantic_blocks,
        "Applicants must apply by October 1.",
    ]
    changes = detect_changes(baseline, current)
    content = [change for change in changes if change.category == "CONTENT"]
    assert len(content) == 1
    assert content[0].materiality == "NEEDS_REVIEW"
