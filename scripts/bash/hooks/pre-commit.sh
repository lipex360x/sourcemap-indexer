#!/usr/bin/env bash
set -euo pipefail

SCRIPT_REAL="$(readlink "$0" 2>/dev/null || echo "$0")"
ROOT="$(cd "$(dirname "$SCRIPT_REAL")/../../.." && pwd -P)"
VENV="$ROOT/.venv/bin"

staged_py=$(git diff --cached --name-only --diff-filter=d | grep '\.py$' || true)
staged_sh=$(git diff --cached --name-only --diff-filter=d | grep '\.sh$' || true)

if [[ -n "$staged_sh" ]]; then
    printf "→ shellcheck\n"
    echo "$staged_sh" | xargs shellcheck -x
fi

if [[ -n "$staged_py" ]]; then
    printf "→ ruff check\n"
    echo "$staged_py" | xargs "$VENV/ruff" check

    printf "→ ruff format\n"
    echo "$staged_py" | xargs "$VENV/ruff" format --check

    src_py=$(echo "$staged_py" | grep '^src/' | grep -v '/lib/' || true)
    if [[ -n "$src_py" ]]; then
        printf "→ mypy\n"
        echo "$src_py" | xargs "$VENV/mypy" --strict \
            --config-file "$ROOT/pyproject.toml"
    fi

    printf "→ vulture\n"
    "$VENV/vulture" "$ROOT/src/sourcemap_indexer/" "$ROOT/tests/" \
        --min-confidence 80 --exclude "*repository*"

    printf "→ bandit\n"
    echo "$staged_py" | xargs "$VENV/bandit" -r -c "$ROOT/pyproject.toml" -q

    printf "→ pylint C0103\n"
    echo "$staged_py" | xargs "$VENV/pylint" --disable=all --enable=C0103 \
        --rcfile="$ROOT/pyproject.toml"

    printf "→ pytest + coverage\n"
    "$VENV/pytest" -q
fi

printf "✓ pre-commit passed\n"
