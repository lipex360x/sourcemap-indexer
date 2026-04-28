from __future__ import annotations

import os
import shutil

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import llm_cli_model, llm_provider_name
from sourcemap_indexer.infra.config.dotenv import load_dotenv
from sourcemap_indexer.infra.llm.llm_client import LlmClient, from_environ, is_llm_configured
from sourcemap_indexer.lib.either import Left


def _check_http() -> bool:
    if not is_llm_configured():
        typer.echo("FAIL:llm-not-configured")
        return False
    config = from_environ()
    typer.echo(f"OK:url={config.url}")
    typer.echo(f"OK:model={config.model}")
    ping_result = LlmClient(config).ping()
    if isinstance(ping_result, Left):
        typer.echo(f"FAIL:http-ping={ping_result.error}")
        return False
    typer.echo("OK:http-ping=ok")
    return True


def _check_cli_provider(provider: str) -> bool:
    binary = "claude" if provider == "claude-cli" else "opencode"
    binary_path = shutil.which(binary)
    if binary_path:
        typer.echo(f"OK:{binary}-binary={binary_path}")
    else:
        typer.echo(f"FAIL:{binary}-not-found")
        return False
    model = llm_cli_model()
    if model:
        typer.echo(f"OK:model={model}")
    return True


@app.command(help="Check LLM provider configuration and connectivity.")
def doctor(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    load_dotenv(project_root / ".env")
    provider = llm_provider_name()
    typer.echo(f"OK:provider={provider}")
    if provider == "http":
        passed = _check_http()
    elif provider in ("claude-cli", "opencode"):
        passed = _check_cli_provider(provider)
    else:
        typer.echo(f"FAIL:unknown-provider={provider}")
        passed = False
    log_enabled = os.environ.get("SOURCEMAP_LLM_LOG") == "1"
    typer.echo(f"OK:llm-log={'enabled' if log_enabled else 'disabled'}")
    if not passed:
        raise typer.Exit(1)
