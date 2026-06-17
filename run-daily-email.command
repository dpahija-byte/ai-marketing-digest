#!/bin/zsh
set -e

cd "$(dirname "$0")"

source .venv/bin/activate
python -m ai_marketing_digest run --build-site
