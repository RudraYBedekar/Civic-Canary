from __future__ import annotations

import argparse

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover the deployed Civic Canary runtime and connect the control plane"
    )
    parser.add_argument("--name", default="CivicCanaryAgent")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)
    runtimes: list[dict] = []
    next_token: str | None = None
    while True:
        request = {"maxResults": 100}
        if next_token:
            request["nextToken"] = next_token
        response = client.list_agent_runtimes(**request)
        runtimes.extend(response.get("agentRuntimes", []))
        next_token = response.get("nextToken")
        if not next_token:
            break

    matches = [item for item in runtimes if item.get("agentRuntimeName") == args.name]
    if not matches:
        raise SystemExit(f"No AgentCore runtime named {args.name!r} was found.")
    runtime = max(matches, key=lambda item: item["lastUpdatedAt"])
    if runtime.get("status") not in {"READY", "ACTIVE"}:
        raise SystemExit(
            f"Runtime {runtime['agentRuntimeArn']} is not ready: {runtime.get('status')}"
        )

    boto3.client("ssm", region_name=args.region).put_parameter(
        Name="/civic-canary/agent-runtime-arn",
        Value=runtime["agentRuntimeArn"],
        Type="String",
        Overwrite=True,
    )
    print(runtime["agentRuntimeArn"])


if __name__ == "__main__":
    main()
