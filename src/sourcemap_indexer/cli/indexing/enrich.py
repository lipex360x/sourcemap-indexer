from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console as _Console
from rich.console import Group as _Group
from rich.live import Live as _Live
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn

from sourcemap_indexer.application.enrich import EnrichReport, run_enrich
from sourcemap_indexer.application.sync import SyncReport, run_sync
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
    llm_provider_name,
    logs_dir,
    maps_dir,
)
from sourcemap_indexer.domain.value_objects import _DEFAULT_LAYERS, Language, Layer
from sourcemap_indexer.infra.dotenv import load_dotenv
from sourcemap_indexer.infra.layers_config import load_user_layers
from sourcemap_indexer.infra.llm_client import (
    SYSTEM_PROMPT,
    LlmClient,
    LlmConfig,
    from_environ,
    is_llm_configured,
)
from sourcemap_indexer.infra.llm_provider import LLMProvider, resolve_provider
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Either, Left, right
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


def _load_enrich_context(
    project_root: Path,
) -> Either[str, tuple[frozenset[str], Path | None, str | None]]:
    user_layers_result = load_user_layers(maps_dir(project_root))
    if isinstance(user_layers_result, Left):
        return user_layers_result
    valid_layers = _DEFAULT_LAYERS | user_layers_result.value
    import_result = import_prompt_path()
    if isinstance(import_result, Left):
        return import_result
    import_path = import_result.value
    custom_prompt = (
        import_path.read_text(encoding="utf-8") if import_path and import_path.exists() else None
    )
    return right((valid_layers, import_path, custom_prompt))


def _handle_export_prompt(
    export_llm_prompt: bool,
    output: str | None,
    project_root: Path,
    custom_prompt: str | None,
) -> None:
    if not export_llm_prompt:
        return
    export_path = Path(output) if output else default_prompt_export_path(project_root)
    if export_path.suffix != ".md":
        typer.echo("Error: --output must have a .md extension", err=True)
        raise typer.Exit(1)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(custom_prompt or SYSTEM_PROMPT, encoding="utf-8")
    typer.echo(f"Prompt exported to {export_path}")
    raise typer.Exit(0)


def _create_http_client(
    project_root: Path,
    custom_prompt: str | None,
    valid_layers: frozenset[str],
) -> tuple[LlmClient, LlmConfig]:
    if not is_llm_configured():
        _Console(stderr=True).print(
            _panel(
                "LLM not configured.\n"
                "Set [bold]SOURCEMAP_LLM_URL[/bold] in your environment"
                " or [bold].env[/bold] file.",
                title="Error",
                style="error",
            )
        )
        raise typer.Exit(1)
    config = from_environ()
    llm_log = create_llm_log(logs_dir(project_root))
    client = LlmClient(
        config,
        llm_log=llm_log,
        system_prompt=custom_prompt,
        valid_layers=None if custom_prompt else valid_layers,
    )
    ping_result = client.ping()
    if isinstance(ping_result, Left):
        typer.echo(f"Error: LLM unreachable — {ping_result.error}", err=True)
        typer.echo(f"  Check that your LLM server is running at: {config.url}", err=True)
        raise typer.Exit(1)
    return (client, config)


def _create_provider(
    project_root: Path,
    provider_name: str,
    custom_prompt: str | None,
    valid_layers: frozenset[str],
) -> tuple[LLMProvider, LlmConfig | None]:
    if provider_name == "http":
        client, config = _create_http_client(project_root, custom_prompt, valid_layers)
        return (client, config)
    result = resolve_provider(provider_name)
    if isinstance(result, Left):
        typer.echo(f"Error: unknown LLM provider '{provider_name}'", err=True)
        raise typer.Exit(1)
    llm_log = create_llm_log(logs_dir(project_root))
    return (
        result.value(llm_log=llm_log, system_prompt=custom_prompt, valid_layers=valid_layers),
        None,
    )


def _build_filters(
    layer: str | None,
    language: str | None,
    file: str | None,
    force: bool,
) -> tuple[Layer | None, Language | None, bool]:
    return (
        Layer(layer) if layer else None,
        Language(language) if language else None,
        True if file else force,
    )


def _build_enrich_header(
    config: LlmConfig | None,
    import_path: Path | None,
    message: str | None,
    provider_name: str = "http",
) -> str:
    if config is not None:
        connected = "  [green]●[/green] connected"
        parts = [f"[bold]Model[/bold]  {config.model}  [dim]({config.url})[/dim]{connected}"]
    else:
        parts = [f"[bold]Provider[/bold]  {provider_name}"]
    if import_path is not None:
        parts.append(f"[bold]Prompt[/bold]  {import_path}")
    if message:
        parts.append(f"[bold]Instruction[/bold]  {message}")
    return "\n".join(parts)


def _has_sync_changes(report: SyncReport) -> bool:
    return bool(report.inserted or report.updated or report.soft_deleted)


def _build_summary_lines(
    report: EnrichReport,
    elapsed: float,
    pre_sync_report: SyncReport | None,
) -> list[str]:
    lines = [
        f"[bold]Enriched[/bold]: {report.enriched}   "
        f"[bold]Failed[/bold]: {report.failed}   "
        f"[bold]Skipped[/bold]: {report.skipped}   "
        f"[bold]Elapsed[/bold]: {elapsed:.1f}s"
    ]
    for error in report.errors:
        lines.append(f"[red]![/red] {error}")
    if pre_sync_report is not None and _has_sync_changes(pre_sync_report):
        lines.append(
            f"[bold]Inserted[/bold]: {pre_sync_report.inserted}   "
            f"[bold]Updated[/bold]: {pre_sync_report.updated}   "
            f"[bold]Soft-deleted[/bold]: {pre_sync_report.soft_deleted}"
        )
    return lines


def _run_enrich_session(
    project_root: Path,
    repo: SqliteItemRepository,
    client: LLMProvider,
    index_path: Path,
    limit: int | None,
    force: bool,
    layer_val: Layer | None,
    language_val: Language | None,
    message: str | None,
    file: str | None,
    valid_layers: frozenset[str],
    prog: Progress,
    task_scan: TaskID,
    task_enrich: TaskID,
) -> Either[str, tuple[EnrichReport, SyncReport | None, float]]:
    walk_result = run_walk(project_root, index_path, known_files=repo.load_known_files())
    if isinstance(walk_result, Left):
        return walk_result
    sync_result = run_sync(index_path, repo)
    pre_sync_report = sync_result.value if not isinstance(sync_result, Left) else None
    prog.update(task_scan, visible=False)
    prog.update(task_enrich, visible=True, description="Enriching...")

    def _progress(path: str, success: bool, current: int, total: int) -> None:
        if current == 1:
            label = "file" if total == 1 else "files"
            prog.update(task_enrich, description=f"Enriching  {total} {label}")
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
        valid_layers=valid_layers,
    )
    elapsed = time.perf_counter() - started
    if isinstance(enrich_result, Left):
        return enrich_result
    return right((enrich_result.value, pre_sync_report, elapsed))


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
    ctx_result = _load_enrich_context(project_root)
    if isinstance(ctx_result, Left):
        typer.echo(f"Error: {ctx_result.error}", err=True)
        raise typer.Exit(1)
    valid_layers, import_path, custom_prompt = ctx_result.value
    _handle_export_prompt(export_llm_prompt, output, project_root, custom_prompt)
    provider_name = llm_provider_name()
    client, config = _create_provider(project_root, provider_name, custom_prompt, valid_layers)
    repo = _open_repo(project_root)
    layer_val, language_val, force = _build_filters(layer, language, file, force)
    header = _build_enrich_header(config, import_path, message, provider_name)
    index_path = index_yaml_path(project_root)
    prog = Progress(
        SpinnerColumn(finished_text="[green]✓[/green]"),
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
        console=_Console(),
        refresh_per_second=20,
        transient=False,
    ) as live:
        session_result = _run_enrich_session(
            project_root,
            repo,
            client,
            index_path,
            limit,
            force,
            layer_val,
            language_val,
            message,
            file,
            valid_layers,
            prog,
            task_scan,
            task_enrich,
        )
        if isinstance(session_result, Left):
            typer.echo(f"Error: {session_result.error}", err=True)
            raise typer.Exit(1)
        report, pre_sync_report, elapsed = session_result.value
        summary_lines = _build_summary_lines(report, elapsed, pre_sync_report)
        panel_style = "warn" if report.failed > 0 else "info"
        live.update(_panel(_Group(header, "\n".join(summary_lines)), "Enrich", style=panel_style))
    from sourcemap_indexer.cli.insights.stats import stats  # noqa: PLC0415

    stats(root=root, files=False, page=1)
