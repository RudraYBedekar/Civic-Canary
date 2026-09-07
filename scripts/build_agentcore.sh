#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="$project_root/build/agentcore-runtime"

rm -rf "$output_dir"
mkdir -p "$output_dir/infra" "$output_dir/web/public" "$output_dir/agent/fixtures"
cp -R "$project_root/agent" "$project_root/services" "$output_dir/"
cp -R "$project_root/web/public/portal" "$output_dir/web/public/"
cp "$project_root/web/node_modules/axe-core/axe.min.js" "$output_dir/agent/fixtures/axe.min.js"
cp "$project_root/pyproject.toml" "$output_dir/pyproject.toml"
cp "$project_root/infra/agentcore-runtime-policy.json" "$output_dir/infra/"

echo "Built the AgentCore source bundle at $output_dir"
