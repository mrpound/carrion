#!/bin/bash
# Shim: carrion is now a uv-managed Python package. This preserves the old
# ./carrion.sh invocation by delegating to the `carrion` console script.
exec uv run --project "$(dirname "$0")" carrion "$@"
