# Civic Canary AWS Deployment Handoff

This guide is for the teammate responsible for deploying Civic Canary. The application currently
runs locally; its previous experimental AWS resources were removed, so deployment starts clean.

## 1. What this deployment creates

The `CivicCanaryMvp` CDK stack creates:

- three DynamoDB on-demand tables for targets, runs, and findings;
- one encrypted, versioned S3 evidence bucket with 30-day lifecycle rules;
- one FastAPI Lambda and one asynchronous scan Lambda;
- one API Gateway HTTP API that also serves the compiled reviewer UI;
- one daily EventBridge schedule at 9:00 AM `America/New_York`;
- one Secrets Manager secret containing only the reviewer-token SHA-256 digest;
- two SSM parameters for runtime and storage configuration;
- CloudWatch log groups with 14-day retention and X-Ray tracing;
- one managed AgentCore Browser and its least-privilege recording role.

The AgentCore CLI separately deploys the `CivicCanaryAgent` runtime. The runtime ARN is then written
to `/civic-canary/agent-runtime-arn` so the API can invoke it.

The frontend uses API Gateway rather than CloudFront. This avoids the new-account CloudFront
verification restriction while preserving one HTTPS origin for the UI, API, and synthetic portal.

## 2. Cost expectations

For a low-volume hackathon demo, expect approximately **USD 5–15 per month**, depending mainly on
Bedrock model tokens, AgentCore browser/runtime duration, and scan frequency. Lambda, API Gateway,
DynamoDB, S3, CloudWatch, Secrets Manager, and EventBridge usage should be small at demo volume.

The deployment helper creates a `CivicCanaryMonthlyBudget` with a USD 15 monthly limit. A budget is
an alerting control, not a hard spending cap. Add an email subscriber in the AWS Budgets console and
delete the stack when the demo is finished.

## 3. Prerequisites

Install locally:

- AWS CLI v2
- Python 3.13 or 3.14
- `uv`
- Node.js 20, 22, or 24 and npm
- the AgentCore CLI used by this repository

Use an IAM Identity Center permission set or role with permission to create the services listed
above. Do not create long-lived root access keys.

Configure and test a profile:

```bash
aws configure sso --profile civic-canary-admin
aws sso login --profile civic-canary-admin
aws sts get-caller-identity --profile civic-canary-admin --region us-east-1
```

For `SSO start URL`, use the IAM Identity Center portal URL such as
`https://d-xxxxxxxxxx.awsapps.com/start`, not an AWS Console URL.

Export the deployment settings:

```bash
export AWS_PROFILE=civic-canary-admin
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT=YOUR_12_DIGIT_ACCOUNT_ID
```

The deploy script compares the signed-in account with `EXPECTED_AWS_ACCOUNT` and stops before
creating resources if they differ.

## 4. Required AWS readiness checks

### Bedrock model

Civic Canary is pinned to:

```text
us.anthropic.claude-sonnet-4-20250514-v1:0
```

Confirm that the inference profile is active in `us-east-1`:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier us.anthropic.claude-sonnet-4-20250514-v1:0 \
  --profile "$AWS_PROFILE" \
  --region us-east-1
```

The deployment intentionally stops if this model is unavailable; it does not silently substitute a
different model.

### AgentCore quotas

In **Service Quotas → Amazon Bedrock AgentCore**, verify that the account can create at least one
custom Browser and one Runtime in `us-east-1`. New accounts can have a quota of zero. Request quota
increases before deploying if necessary.

You can also confirm that no old resources remain:

```bash
aws bedrock-agentcore-control list-browsers --profile "$AWS_PROFILE" --region us-east-1
aws bedrock-agentcore-control list-agent-runtimes --profile "$AWS_PROFILE" --region us-east-1
```

## 5. Prepare the project

From the repository root:

```bash
uv sync --extra dev --extra infra
npm --prefix web install
```

Run the quality checks before any cloud changes:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check agent services tests scripts infra
npm --prefix web test
npm --prefix web run lint
npm --prefix web run build
```

## 6. Create the reviewer token

Generate a strong token of at least 20 characters and its digest:

```bash
uv run python scripts/token_digest.py
```

The script prints a 64-character SHA-256 digest. Store the plaintext token in a password manager and
export only the digest for deployment:

```bash
export REVIEW_TOKEN_SHA256=PASTE_THE_64_CHARACTER_DIGEST
```

Do not put the plaintext token or digest in Git, shell scripts, screenshots, or issue trackers. The
plaintext token cannot be recovered from AWS.

## 7. Preview before deployment

Build and synthesize locally:

```bash
npm --prefix web run build
./scripts/build_lambda.sh
./scripts/build_agentcore.sh
uv run --extra infra python -m infra.app
```

Review the infrastructure diff:

```bash
uv run python scripts/configure_agentcore_target.py --region us-east-1
npx aws-cdk diff CivicCanaryMvp
agentcore validate
agentcore deploy --target default --dry-run
```

The `scripts/configure_agentcore_target.py` helper creates the ignored, account-specific
`agentcore/aws-targets.json` from the active identity.

## 8. Deploy

The guarded deployment script performs the model check, creates or updates the USD 15 budget,
configures the AgentCore target, builds packages, bootstraps CDK, deploys the supporting stack,
seeds the synthetic target, deploys the runtime, and connects the runtime ARN:

```bash
./scripts/deploy_aws.sh
```

The script prints the reviewer URL when complete. Keep the terminal output for troubleshooting, but
redact account identifiers before sharing it publicly.

If a step fails, do not repeatedly deploy blindly. Inspect the CloudFormation event first:

```bash
aws cloudformation describe-stack-events \
  --stack-name CivicCanaryMvp \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --max-items 30
```

Common blockers:

- **AgentCore quota error:** request the Browser or Runtime quota, wait for approval, then retry.
- **Bedrock access error:** enable the specified model/inference profile in `us-east-1`.
- **SSO token expired:** run `aws sso login --profile civic-canary-admin` again.
- **Wrong account:** correct `EXPECTED_AWS_ACCOUNT`; never bypass the account guard.
- **`ROLLBACK_COMPLETE`:** delete the failed `CivicCanaryMvp` stack before retrying.

## 9. Verify the deployed MVP

Read the outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name CivicCanaryMvp \
  --profile "$AWS_PROFILE" \
  --region us-east-1 \
  --query 'Stacks[0].Outputs'
```

Then complete this acceptance flow:

1. Open `FrontendUrl` and enter the plaintext reviewer token.
2. Keep portal V1 selected and run a scan; expect no findings.
3. Switch to V2 and run another scan.
4. Confirm findings for the new document, broken Spanish link, and unlabeled field.
5. Inspect evidence and approve one proposed patch.
6. Confirm an `approved/<finding_id>.md` object exists in the evidence bucket.
7. Repeat the scan and confirm open findings are not duplicated.
8. Check CloudWatch/X-Ray using the shared `run_id`.
9. Wait for or temporarily invoke the scheduled worker and confirm a scheduled run appears.

Do not enable a real URL until its exact hostname is added to the target allow-list and its journey
has been reviewed as read-only.

## 10. Cleanup and stop charges

Cleanup is destructive. Resolve the exact runtime and browser IDs before deleting anything, and do
not remove an account-wide `CDKToolkit` stack if other projects use it.

First list the AgentCore resources:

```bash
aws bedrock-agentcore-control list-agent-runtimes \
  --profile "$AWS_PROFILE" --region us-east-1
aws bedrock-agentcore-control list-browsers \
  --profile "$AWS_PROFILE" --region us-east-1
```

Delete the exact Civic Canary runtime and browser using their returned IDs:

```bash
aws bedrock-agentcore-control delete-agent-runtime \
  --agent-runtime-id CIVIC_CANARY_RUNTIME_ID \
  --profile "$AWS_PROFILE" --region us-east-1
aws bedrock-agentcore-control delete-browser \
  --browser-id CIVIC_CANARY_BROWSER_ID \
  --profile "$AWS_PROFILE" --region us-east-1
```

Destroy the application stack and remove its budget:

```bash
npx aws-cdk destroy CivicCanaryMvp
aws budgets delete-budget \
  --account-id "$EXPECTED_AWS_ACCOUNT" \
  --budget-name CivicCanaryMonthlyBudget \
  --profile "$AWS_PROFILE" \
  --region us-east-1
```

Finally verify that no Civic Canary Lambda functions, DynamoDB tables, API Gateway APIs, schedules,
AgentCore resources, evidence buckets, or CloudWatch log groups remain. Billing data can lag, so
charges already incurred may appear after deletion.
