#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

aws_profile="${AWS_PROFILE:-civic-canary-admin}"
aws_region="us-east-1"
expected_account="${EXPECTED_AWS_ACCOUNT:-}"
review_digest="${REVIEW_TOKEN_SHA256:-}"

if [[ ! "$expected_account" =~ ^[0-9]{12}$ ]]; then
  echo "Set EXPECTED_AWS_ACCOUNT to the 12-digit AWS account ID you intend to deploy into."
  exit 1
fi

if [[ ! "$review_digest" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Set REVIEW_TOKEN_SHA256 to the 64-character digest from scripts/token_digest.py."
  exit 1
fi

export AWS_PROFILE="$aws_profile"
export CDK_DEFAULT_ACCOUNT="$expected_account"
export CDK_DEFAULT_REGION="$aws_region"

actual_account="$(aws sts get-caller-identity --region "$aws_region" --query Account --output text)"
if [[ "$actual_account" != "$expected_account" ]]; then
  echo "Refusing deployment: expected account $expected_account, received $actual_account."
  exit 1
fi

model_status="$(aws bedrock get-inference-profile \
  --inference-profile-identifier us.anthropic.claude-sonnet-4-20250514-v1:0 \
  --region "$aws_region" --query status --output text)"
if [[ "$model_status" != "ACTIVE" ]]; then
  echo "Configured Bedrock inference profile is not ACTIVE: $model_status"
  exit 1
fi

budget_name="CivicCanaryMonthlyBudget"
budget_spec='{"BudgetName":"CivicCanaryMonthlyBudget","BudgetLimit":{"Amount":"15","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}'
if aws budgets describe-budget \
  --account-id "$expected_account" --budget-name "$budget_name" \
  --region "$aws_region" >/dev/null 2>&1; then
  aws budgets update-budget \
    --account-id "$expected_account" --new-budget "$budget_spec" \
    --region "$aws_region"
else
  aws budgets create-budget \
    --account-id "$expected_account" --budget "$budget_spec" \
    --region "$aws_region"
fi

uv run python scripts/configure_agentcore_target.py --region "$aws_region"
npm --prefix web run build
./scripts/build_lambda.sh
./scripts/build_agentcore.sh
agentcore validate
agentcore package --directory . --runtime CivicCanaryAgent

npx aws-cdk bootstrap "aws://$expected_account/$aws_region"
REVIEW_TOKEN_SHA256="$review_digest" npx aws-cdk deploy \
  CivicCanaryMvp --require-approval never

uv run python scripts/seed_aws.py --region "$aws_region"
agentcore deploy --target default --yes
uv run python scripts/connect_deployed_runtime.py --region "$aws_region"

frontend_url="$(aws cloudformation describe-stacks \
  --stack-name CivicCanaryMvp --region "$aws_region" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue | [0]" \
  --output text)"

echo "Civic Canary deployment completed: $frontend_url"
echo "The budget tracks monthly spend at USD 15. Add an email notification in AWS Budgets."
