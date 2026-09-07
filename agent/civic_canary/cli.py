from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .browser import FixtureBrowserAdapter
from .engine import CivicCanaryEngine
from .models import PortalTarget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "web" / "public" / "portal"
PLAYBOOK = PROJECT_ROOT / "agent" / "fixtures" / "benefits-playbook.md"


async def _scan(version: str) -> dict:
    browser = FixtureBrowserAdapter(FIXTURES)
    target = PortalTarget(active_version="v1")
    baseline = await browser.capture(target, "baseline-v1")
    target.active_version = version
    run, snapshot, findings = await CivicCanaryEngine(browser).execute(
        target=target,
        baseline=baseline,
        playbook=PLAYBOOK.read_text(encoding="utf-8"),
    )
    return {
        "run": run.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Civic Canary deterministic demo scan")
    parser.add_argument("--version", choices=["v1", "v2"], default="v2")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_scan(args.version)), indent=2))


if __name__ == "__main__":
    main()

