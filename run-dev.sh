#!/usr/bin/env bash
# Run both the pipeline and frontend for local development.
# Usage: ./run-dev.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo "Shutting down..."
  kill "$PIPELINE_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$PIPELINE_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Starting pipeline on :8000 ..."
cd "$ROOT_DIR"
uvicorn pipeline.app:app --host 0.0.0.0 --port 8000 --reload &
PIPELINE_PID=$!

echo "Starting frontend on :3000 ..."
cd "$ROOT_DIR/frontend"
PIPELINE_URL=http://localhost:8000 npm run dev &
FRONTEND_PID=$!

echo ""
echo "Pipeline: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Press Ctrl+C to stop both services."
echo ""

wait
