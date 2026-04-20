from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console as _Console
from rich.panel import Panel as _Panel

from sourcemap_indexer.application.enrich import run_enrich
from sourcemap_indexer.cli._shared import (
    _FILE_HELP,
    _LANG_HELP,
    _LANG_VALUES,
    _LAYER_HELP,
    _LAYER_VALUES,
    _open_repo,
    _resolve_root,
    app,
)
from sourcemap_indexer.config import default_prompt_export_path, import_prompt_path, logs_dir
from sourcemap_indexer.domain.value_objects import Language, Layer
from sourcemap_indexer.infra.dotenv import load_dotenv
from sourcemap_indexer.infra.llama_client import (
    SYSTEM_PROMPT,
    LlamaClient,
    from_environ,
    is_llm_configured,
)
from sourcemap_indexer.lib.either import Left
from sourcemap_indexer.lib.llm_log import create_llm_log

_ENRICH_HELP = (
    "Enrich pending files via LLM. --limit N, --force (re-enrich),"
    f" --layer ({_LAYER_VALUES}), --language ({_LANG_VALUES}),"
    " --file PATH (single file), -m INSTRUCTION.\n\n"
    "  Examples:\n"
    "    sourcemap enrich --limit 10\n"
    "    sourcemap enrich --force --file src/app.py\n"
    "    sourcemap enrich --force --layer unknown -m 'write in English'"
)


@app.command(help=_ENRICH_HELP)
def enrich(
    root: str | None = typer.Option(None, help="Project root"),
    limit: int | None = typer.Option(None, "--limit", help="Max items to enrich"),
    force: bool = typer.Option(False, "--force", help="Re-enrich already enriched files"),
    layer: str | None = typer.Option(None, "--layer", help=_LAYER_HELP),
    language: str | None = typer.Option(None, "--language", help=_LANG_HELP),
    message: str | None = typer.Option(None, "-m", help="Extra instruction injected into prompt"),
    file: str | None = typer.Option(None, "--file", help=_FILE_HELP),
    export_llm_prompt: bool = typer.Option(
        False, "--export-llm-prompt", help="Write the active LLM prompt to a .md file"
    ),
    output: str | None = typer.Option(
        None, "--output", help="Destination for --export-llm-prompt (default: maps dir)"
    ),
) -> None:
    project_root = _resolve_root(root)
    load_dotenv(project_root / ".env")

    import_result = import_prompt_path()
    if isinstance(import_result, Left):
        typer.echo(f"Error: {import_result.error}", err=True)
        raise typer.Exit(1)

    import_path = import_result.value
    custom_prompt = (
        import_path.read_text(encoding="utf-8") if import_path and import_path.exists() else None
    )

    if export_llm_prompt:
        export_path = Path(output) if output else default_prompt_export_path(project_root)
        if export_path.suffix != ".md":
            typer.echo("Error: --output must have a .md extension", err=True)
            raise typer.Exit(1)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(custom_prompt or SYSTEM_PROMPT, encoding="utf-8")
        typer.echo(f"Prompt exported to {export_path}")
        raise typer.Exit(0)

    if not is_llm_configured():
        _Console(stderr=True).print(
            _Panel(
                "LLM not configured.\n"
                "Set [bold]SOURCEMAP_LLM_URL[/bold] in your environment or [bold].env[/bold] file.",
                title="Error",
                border_style="red",
                title_align="left",
            )
        )
        raise typer.Exit(1)
    repo = _open_repo(project_root)
    config = from_environ()
    llm_log = create_llm_log(logs_dir(project_root))
    client = LlamaClient(config, llm_log=llm_log, system_prompt=custom_prompt)
    typer.echo(f"Model: {config.model}  ({config.url})")
    if import_path is not None:
        typer.echo(f"Prompt: {import_path}")
    if message:
        typer.echo(f"Instruction: {message}")
    ping_result = client.ping()
    if isinstance(ping_result, Left):
        typer.echo(f"Error: LLM unreachable — {ping_result.error}", err=True)
        typer.echo(f"  Check that your LLM server is running at: {config.url}", err=True)
        raise typer.Exit(1)

    layer_val = Layer(layer) if layer else None
    language_val = Language(language) if language else None
    if file:
        force = True

    def _progress(path: str, success: bool, current: int, total: int) -> None:
        bar_width = 20
        filled = round(current / total * bar_width) if total else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = round(current / total * 100) if total else 0
        pad = len(str(total))
        symbol = "✓" if success else "✗"
        typer.echo(f"  [{current:>{pad}}/{total}] [{bar}] {pct:>3}%  {symbol} {path}")

    started = time.perf_counter()
    enrich_result = run_enrich(
        project_root,
        repo,
        client,
        batch_limit=limit,
        on_progress=_progress,
        force=force,
        layer_filter=layer_val,
        language_filter=language_val,
        extra_instruction=message,
        path_filter=file,
    )
    elapsed = time.perf_counter() - started
    if isinstance(enrich_result, Left):
        typer.echo(f"Error: {enrich_result.error}", err=True)
        raise typer.Exit(1)
    report = enrich_result.value
    typer.echo(
        f"\nEnrich: enriched={report.enriched} failed={report.failed} skipped={report.skipped}"
        f" elapsed={elapsed:.1f}s"
    )
    for error in report.errors:
        typer.echo(f"  ! {error}", err=True)
    typer.echo("")

    from sourcemap_indexer.cli.insights.stats import stats  # noqa: PLC0415

    stats(root=root, files=False, page=1)
