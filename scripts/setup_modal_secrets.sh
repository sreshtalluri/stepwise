#!/bin/bash
# Set up Modal secrets for R2 storage from the .env file.
# Run this once before deploying to Modal.
#
# Usage:
#   bash scripts/setup_modal_secrets.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Source the .env file
set -a
source "$ENV_FILE"
set +a

echo "Creating Modal secret 'stepwise-r2' with R2 credentials..."
modal secret create stepwise-r2 \
    R2_ENDPOINT_URL="$R2_ENDPOINT_URL" \
    R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    R2_BUCKET_NAME="$R2_BUCKET_NAME"

echo "Done! Secret 'stepwise-r2' created successfully."
