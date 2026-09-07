from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
TARGETS_FILE = ROOT / "agentcore" / "aws-targets.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure the default AgentCore deployment target from the active AWS identity"
    )
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    account = boto3.client("sts", region_name=args.region).get_caller_identity()["Account"]
    target = [
        {
            "name": "default",
            "description": "Civic Canary hackathon deployment",
            "account": account,
            "region": args.region,
        }
    ]
    TARGETS_FILE.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")
    print(f"Configured AgentCore target 'default' in {args.region}.")


if __name__ == "__main__":
    main()
