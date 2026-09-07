#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="$project_root/build/lambda"

rm -rf "$output_dir"
mkdir -p "$output_dir"
uv pip install \
  --cache-dir /private/tmp/civic-canary-uv-cache \
  --python-platform x86_64-manylinux2014 \
  --python-version 3.13 \
  --target "$output_dir" \
  --requirements "$project_root/services/requirements.txt"
cp -R "$project_root/agent" "$project_root/services" "$output_dir/"
mkdir -p "$output_dir/web"
cp -R "$project_root/web/dist" "$output_dir/web/"

echo "Built the Lambda package at $output_dir"
