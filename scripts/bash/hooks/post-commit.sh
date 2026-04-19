#!/usr/bin/env bash
set -euo pipefail

sourcemap walk > /dev/null
sourcemap sync
