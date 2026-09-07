from __future__ import annotations

import hashlib
import re

from .models import (
    DetectedChange,
    Finding,
    Materiality,
    PortalSnapshot,
    Severity,
)


def _fingerprint(*parts: str) -> str:
    normalized = "|".join(re.sub(r"\s+", " ", part).strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode()).hexdigest()[:24]


def detect_changes(baseline: PortalSnapshot, current: PortalSnapshot) -> list[DetectedChange]:
    changes: list[DetectedChange] = []
    baseline_requirements = {
        requirement for page in baseline.pages for requirement in page.requirements
    }
    current_requirements = {
        requirement for page in current.pages for requirement in page.requirements
    }
    for added in sorted(current_requirements - baseline_requirements):
        page = next(page for page in current.pages if added in page.requirements)
        changes.append(
            DetectedChange(
                category="REQUIREMENT",
                current_value=added,
                source_url=page.url,
                evidence=f'New required document: "{added}"',
                confidence=1.0,
                materiality=Materiality.MATERIAL,
                severity=Severity.HIGH,
                fingerprint=_fingerprint(current.target_id, "requirement", added),
            )
        )

    baseline_broken = {
        link.href for page in baseline.pages for link in page.links if link.status >= 400
    }
    for page in current.pages:
        for link in page.links:
            if link.status >= 400 and link.href not in baseline_broken:
                changes.append(
                    DetectedChange(
                        category="BROKEN_LINK",
                        current_value=f"{link.text}: {link.href} returned {link.status}",
                        source_url=page.url,
                        evidence=f'Link "{link.text}" is unavailable (HTTP {link.status}).',
                        confidence=1.0,
                        materiality=Materiality.MATERIAL,
                        severity=Severity.MEDIUM,
                        fingerprint=_fingerprint(current.target_id, "broken-link", link.href),
                    )
                )

    baseline_issues = {
        (issue.rule, issue.selector)
        for page in baseline.pages
        for issue in page.accessibility_issues
    }
    for page in current.pages:
        for issue in page.accessibility_issues:
            if (issue.rule, issue.selector) not in baseline_issues:
                changes.append(
                    DetectedChange(
                        category="ACCESSIBILITY",
                        current_value=issue.description,
                        source_url=page.url,
                        evidence=f"{issue.rule} at {issue.selector}: {issue.description}",
                        confidence=1.0,
                        materiality=Materiality.MATERIAL,
                        severity=issue.severity,
                        fingerprint=_fingerprint(
                            current.target_id, "accessibility", issue.rule, issue.selector
                        ),
                    )
                )

    # Monitor ordinary policy copy as well as explicit data-requirement markers. This
    # is deliberately conservative: only high-signal public-service language becomes
    # actionable, while general layout/navigation copy remains cosmetic.
    high_signal = re.compile(
        r"\b(eligible|eligibility|income|deadline|apply by|must|required|benefit amount|"
        r"proof of|document|residen(?:t|cy)|citizen(?:ship)?)\b",
        re.IGNORECASE,
    )
    for page_index, page in enumerate(current.pages):
        if page_index >= len(baseline.pages):
            continue
        previous = baseline.pages[page_index]
        excluded = set(previous.requirements) | set(page.requirements)
        before = {block for block in previous.semantic_blocks if block not in excluded}
        after = {block for block in page.semantic_blocks if block not in excluded}
        removed = sorted(block for block in before - after if high_signal.search(block))
        added = sorted(block for block in after - before if high_signal.search(block))
        if not removed and not added:
            continue
        previous_value = " | ".join(removed) or None
        current_value = " | ".join(added) or "Relevant policy text was removed."
        changes.append(
            DetectedChange(
                category="CONTENT",
                previous_value=previous_value,
                current_value=current_value,
                source_url=page.url,
                evidence=(
                    f'Previous policy text: "{previous_value or "none"}"; '
                    f'current policy text: "{current_value}".'
                ),
                confidence=0.85,
                materiality=Materiality.NEEDS_REVIEW,
                severity=Severity.MEDIUM,
                fingerprint=_fingerprint(
                    current.target_id,
                    "content",
                    previous_value or "",
                    current_value,
                    page.url,
                ),
            )
        )
    return changes


def map_playbook_section(change: DetectedChange, playbook: str) -> tuple[list[str], str]:
    if change.category == "REQUIREMENT":
        section = "Required documents"
        patch = (
            "Add the following verified item to the Required documents checklist:\n\n"
            f"- {change.current_value}\n\n"
            f"Source evidence: {change.evidence}"
        )
    elif change.category == "BROKEN_LINK":
        section = "Language assistance"
        patch = (
            "Temporarily mark the Spanish portal link as unavailable and direct clients to "
            "staff-assisted language support. Do not substitute an unverified URL.\n\n"
            f"Source evidence: {change.evidence}"
        )
    elif change.category == "ACCESSIBILITY":
        section = "Application support"
        patch = (
            "Flag this form control for accessibility remediation and advise staff to offer "
            "assisted completion until the public page is fixed.\n\n"
            f"Source evidence: {change.evidence}"
        )
    else:
        section = "Eligibility and deadlines"
        patch = (
            "Do not change client-facing guidance automatically. Ask the playbook owner to "
            "compare this policy-language change with the official source and approve exact "
            "wording. Mark the draft NEEDS_REVIEW.\n\n"
            f"Source evidence: {change.evidence}"
        )
    if f"## {section}" not in playbook:
        return ["Needs playbook owner review"], patch
    return [section], patch


def findings_from_changes(
    changes: list[DetectedChange], *, run_id: str, target_id: str, playbook: str
) -> list[Finding]:
    findings: list[Finding] = []
    titles = {
        "REQUIREMENT": "Benefits portal added a required document",
        "BROKEN_LINK": "Spanish guidance link is broken",
        "ACCESSIBILITY": "Application form has a new accessibility barrier",
        "CONTENT": "Material portal content changed",
    }
    for change in changes:
        sections, patch = map_playbook_section(change, playbook)
        findings.append(
            Finding(
                finding_id=f"finding-{change.fingerprint}",
                run_id=run_id,
                target_id=target_id,
                title=titles[change.category],
                category=change.category,
                severity=change.severity,
                materiality=change.materiality,
                evidence=[change.evidence, f"Observed at {change.source_url}"],
                affected_playbook_sections=sections,
                proposed_patch=patch,
            )
        )
    return findings
