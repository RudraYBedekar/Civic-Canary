#!/usr/bin/env python3
import os
import re

import aws_cdk as cdk

from infra.civic_canary_stack import CivicCanaryStack

app = cdk.App()
review_token_digest = os.getenv("REVIEW_TOKEN_SHA256", "")
if not re.fullmatch(r"[0-9a-f]{64}", review_token_digest):
    raise ValueError(
        "REVIEW_TOKEN_SHA256 must be the 64-character lowercase digest produced by "
        "scripts/token_digest.py"
    )
CivicCanaryStack(
    app,
    "CivicCanaryMvp",
    review_token_digest=review_token_digest,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
