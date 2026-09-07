from __future__ import annotations

import argparse

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect the control plane to AgentCore Runtime")
    parser.add_argument("runtime_arn")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    if not args.runtime_arn.startswith("arn:aws:bedrock-agentcore:"):
        raise SystemExit("The supplied value is not an AgentCore runtime ARN.")
    boto3.client("ssm", region_name=args.region).put_parameter(
        Name="/civic-canary/agent-runtime-arn",
        Value=args.runtime_arn,
        Type="String",
        Overwrite=True,
    )
    print("Connected the control plane to the AgentCore runtime.")


if __name__ == "__main__":
    main()

