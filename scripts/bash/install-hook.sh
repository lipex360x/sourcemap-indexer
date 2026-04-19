#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_GIT="$(git rev-parse --git-dir)"
HOOK_SRC="$SCRIPT_DIR/hooks/post-commit.sh"
HOOK_DST="$TARGET_GIT/hooks/post-commit"

if [[ ! -f "$HOOK_SRC" ]]; then
    printf "Error: hook source not found: %s\n" "$HOOK_SRC" >&2
    exit 1
fi

chmod +x "$HOOK_SRC"

if [[ -e "$HOOK_DST" && ! -L "$HOOK_DST" ]]; then
    printf "Error: %s already exists and is not a symlink. Remove it manually.\n" "$HOOK_DST" >&2
    exit 1
fi

ln -sf "$HOOK_SRC" "$HOOK_DST"
printf "Installed post-commit hook → %s\n" "$HOOK_DST"
