from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console as _Console
from rich.console import Group as _Group
from rich.live import Live as _Live
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sourcemap_indexer.application.enrich import run_enrich
from sourcemap_indexer.application.sync import run_sync
from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.cli._rendering import _HybridProgressColumn, _panel
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
from sourcemap_indexer.config import (
    default_prompt_export_path,
    import_prompt_path,
    index_yaml_path,
    logs_dir,
)
from sourcemap_indexer.domain.value_objects import Language, Layer
from sourcemap_indexer.infra.dotenv import load_dotenv
from sourcemap_indexer.infra.llm_client import (
    SYSTEM_PROMPT,
    LlmClient,
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
            _panel(
                "LLM not configured.\n"
                "Set [bold]SOURCEMAP_LLM_URL[/bold] in your environment or [bold].env[/bold] file.",
                title="Error",
                style="error",
            )
        )
        raise typer.Exit(1)
    repo = _open_repo(project_root)
    config = from_environ()
    llm_log = create_llm_log(logs_dir(project_root))
    client = LlmClient(config, llm_log=llm_log, system_prompt=custom_prompt)
    ping_result = client.ping()
    if isinstance(ping_result, Left):
        typer.echo(f"Error: LLM unreachable — {ping_result.error}", err=True)
        typer.echo(f"  Check that your LLM server is running at: {config.url}", err=True)
        raise typer.Exit(1)

    layer_val = Layer(layer) if layer else None
    language_val = Language(language) if language else None
    if file:
        force = True

    console = _Console()
    header_parts = [f"[bold]Model[/bold]  {config.model}  [dim]({config.url})[/dim]"]
    if import_path is not None:
        header_parts.append(f"[bold]Prompt[/bold]  {import_path}")
    if message:
        header_parts.append(f"[bold]Instruction[/bold]  {message}")
    header = "\n".join(header_parts)

    index_path = index_yaml_path(project_root)

    prog = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        _HybridProgressColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[file]}[/dim]"),
        refresh_per_second=20,
    )
    task_scan = prog.add_task("Scanning...", total=None, file="")
    task_enrich = prog.add_task("Enriching...", total=None, file="", visible=False)

    with _Live(
        _panel(_Group(header, prog), "Enrich"),
        console=console,
        refresh_per_second=20,
        transient=False,
    ) as live:
        walk_result = run_walk(project_root, index_path, known_files=repo.load_known_files())
        if isinstance(walk_result, Left):
            typer.echo(f"Error: {walk_result.error}", err=True)
            raise typer.Exit(1)

        sync_result = run_sync(index_path, repo)
        pre_sync_report = sync_result.value if not isinstance(sync_result, Left) else None

        prog.update(task_scan, visible=False)
        prog.update(task_enrich, visible=True)

        def _progress(path: str, success: bool, current: int, total: int) -> None:
            prog.update(task_enrich, completed=current, total=total, file=path)

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
        summary_lines = [
            f"[bold]Enriched[/bold]: {report.enriched}   "
            f"[bold]Failed[/bold]: {report.failed}   "
            f"[bold]Skipped[/bold]: {report.skipped}   "
            f"[bold]Elapsed[/bold]: {elapsed:.1f}s"
        ]
        for error in report.errors:
            summary_lines.append(f"[red]![/red] {error}")

        if pre_sync_report is not None and (
            pre_sync_report.inserted or pre_sync_report.updated or pre_sync_report.soft_deleted
        ):
            summary_lines.append(
                f"[bold]Inserted[/bold]: {pre_sync_report.inserted}   "
                f"[bold]Updated[/bold]: {pre_sync_report.updated}   "
                f"[bold]Soft-deleted[/bold]: {pre_sync_report.soft_deleted}"
            )

        panel_style = "warn" if report.failed > 0 else "info"
        live.update(_panel(_Group(header, "\n".join(summary_lines)), "Enrich", style=panel_style))

    from sourcemap_indexer.cli.insights.stats import stats  # noqa: PLC0415

    stats(root=root, files=False, page=1)
